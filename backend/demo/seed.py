"""Idempotent synthetic fixtures using existing domain boundaries, without providers."""

import hashlib
import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.assistant.errors import AssistantFailure, ModelFailure
from backend.app.assistant.model import ModelReply, ModelRequest
from backend.app.assistant.schemas import ConversationCreate, MessageCreate, ModelOutput
from backend.app.assistant.service import AssistantService
from backend.app.config import Settings
from backend.app.identity.context import CurrentUser
from backend.app.identity.demo import DEMO_IDENTITY, LocalDemoVerifier
from backend.app.identity.service import provision_user
from backend.app.ingestion.storage import LocalStorageProvider
from backend.app.insights.evaluation import InsightEvaluation
from backend.app.insights.schemas import InsightQuery, InsightUpdate
from backend.app.insights.service import InsightService
from backend.app.inventory.schemas import EventCreate, EvidenceCorrection, LotCreate
from backend.app.inventory.service import InventoryService
from backend.app.memory.schemas import MemoryCreate
from backend.app.memory.service import MemoryService
from backend.app.purchases.models import Purchase
from backend.app.purchases.repositories import ReceiptRepository
from backend.app.purchases.schemas import (
    CategoryCreate,
    MerchantCreate,
    ProductCreate,
    PurchaseCreate,
    ReceiptCreate,
    ReceiptStatus,
)
from backend.app.purchases.service import PurchaseService
from backend.app.wallet.repository import ensure_pass

MARKER = "Raseed local demo v1 — synthetic seed anchor; not a real purchase."


def key(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, "https://raseed.example.test/local-demo/v1/" + name)


class SeedConversationModel:
    """Seed-time script. Values are resolved by the real tool/grounding services."""

    provider = "LOCAL_DEMO_SEED"
    model = "synthetic-transcript-v1"

    def __init__(self, purchase_id: UUID, *, fail: bool = False) -> None:
        self.purchase_id, self.fail = purchase_id, fail

    def respond(self, request: ModelRequest, *, timeout: float) -> ModelReply:
        if self.fail:
            raise ModelFailure("provider_configuration")
        if not request.feedback:
            return ModelReply(
                ModelOutput.model_validate(
                    {
                        "tool_calls": [
                            {
                                "call_id": "demo-purchase",
                                "name": "get_purchase",
                                "arguments": json.dumps({"purchase_id": str(self.purchase_id)}),
                            }
                        ]
                    }
                )
            )
        return ModelReply(
            ModelOutput.model_validate(
                {
                    "answer": {
                        "kind": "answer",
                        "template": (
                            "Synthetic example: your purchase at {{merchant}} totaled "
                            "{{total}} {{currency}}. These values come from the saved demo "
                            "purchase; this is a prepared conversation, not a live model response."
                        ),
                        "source_call_ids": ["demo-purchase"],
                        "references": [
                            {
                                "name": name,
                                "call_id": "demo-purchase",
                                "pointer": "/data/purchase/" + field,
                            }
                            for name, field in [
                                ("merchant", "merchant_name_raw"),
                                ("total", "grand_total"),
                                ("currency", "currency"),
                            ]
                        ],
                    }
                }
            )
        )


def seed_demo(engine: Engine, settings: Settings, *, as_of: date | None = None) -> dict[str, str]:
    LocalDemoVerifier(settings)  # The CLI and direct callers share fail-closed guards.
    today = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    now = datetime.combine(today, datetime.min.time(), ZoneInfo("Asia/Kolkata")) + timedelta(
        hours=12
    )
    storage = LocalStorageProvider(settings.local_storage_path)
    artifacts: list[str] = []
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 731942013})
            # Service commits release savepoints; the complete fixture commits atomically.
            factory = sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            with factory() as session:
                user = provision_user(session, DEMO_IDENTITY)
                with session.begin():
                    prior = session.scalar(
                        select(Purchase).where(
                            Purchase.user_id == user.id, Purchase.notes == MARKER
                        )
                    )
                    if prior is not None:
                        return {
                            "status": "already seeded",
                            "user_id": str(user.id),
                            "anchor_purchase_id": str(prior.id),
                        }
                anchor = _populate(factory, session, user, now, storage, artifacts)
                return {
                    "status": "seeded",
                    "user_id": str(user.id),
                    "anchor_purchase_id": str(anchor),
                }
    except Exception:
        # Only artifacts created by this failed attempt are removed; no existing files/rows change.
        for reference in artifacts:
            storage.delete_object(reference)
        raise


def _populate(
    factory: sessionmaker[Session],
    session: Session,
    user: CurrentUser,
    now: datetime,
    storage: LocalStorageProvider,
    artifacts: list[str],
) -> UUID:
    purchases = PurchaseService(session, user, clock=lambda: now)
    inventory = InventoryService(session, user, clock=lambda: now)
    today = now.date()
    categories = [
        purchases.create_category(CategoryCreate(name=name, slug=slug, inventory_eligible=eligible))
        for name, slug, eligible in [
            ("Groceries", "demo-groceries", True),
            ("Dining", "demo-dining", False),
            ("Home & living", "demo-home", False),
            ("Books", "demo-books", False),
        ]
    ]
    merchants = [
        purchases.create_merchant(
            MerchantCreate(canonical_name=name, city="Bengaluru", country="IN")
        )
        for name in [
            "Green Basket Market",
            "Filter Coffee House",
            "Everyday Home",
            "Paper Trail Books",
        ]
    ]

    def receipt(name: str, status: ReceiptStatus, lines: list[str]) -> UUID:
        canvas = Image.new("RGB", (720, 480), "white")
        draw = ImageDraw.Draw(canvas)
        draw.multiline_text(
            (30, 30),
            "SYNTHETIC DEMO - NOT A REAL RECEIPT\n\n" + name + "\n\n" + "\n".join(lines),
            fill="black",
            spacing=14,
            font_size=20,
        )
        stream = io.BytesIO()
        canvas.save(stream, format="PNG")
        content = stream.getvalue()
        row = purchases.create_receipt(
            ReceiptCreate(
                original_filename=name + ".png",
                mime_type="image/png",
                file_size=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
                source="LOCAL_DEMO",
            )
        )
        reference = storage.put_object(content, "image/png")
        artifacts.append(reference)
        with session.begin():
            record = ReceiptRepository(session, user).get(row.id)
            record.storage_uri, record.uploaded_at, record.status = reference, now, status
            if status == "PROCESSED":
                record.processed_at = now
            if status in {"FAILED", "NEEDS_REVIEW"}:
                record.failure_code = "demo_example"
                record.failure_message = (
                    "Synthetic "
                    + status.lower().replace("_", " ")
                    + " example. No extraction provider was called."
                )
        return row.id

    foods = [
        ("Whole milk", "l", "2", "60"),
        ("Greek yogurt", "each", "3", "45"),
        ("Basmati rice", "kg", "2", "120"),
        ("Bananas", "kg", "1", "65"),
        ("Rolled oats", "each", "1", "180"),
        ("Fresh spinach", "each", "2", "30"),
    ]
    lines = []
    for name, unit, quantity, price in foods:
        product = purchases.create_product(
            ProductCreate(
                canonical_name=name,
                category_id=categories[0].id,
                unit_type=unit,
                inventory_eligible=True,
            )
        )
        lines.append(
            {
                "raw_name": name,
                "product_id": product.id,
                "category_id": categories[0].id,
                "quantity": quantity,
                "unit": unit,
                "unit_price": price,
                "line_total": str(Decimal(quantity) * Decimal(price)),
            }
        )
    total = sum((Decimal(str(line["line_total"])) for line in lines), Decimal(0))
    original = receipt(
        "Green Basket demo",
        "PROCESSED",
        [f"{name}: {quantity} {unit} at INR {price}" for name, unit, quantity, price in foods]
        + [f"Total INR {total}"],
    )
    anchor = purchases.create_purchase(
        PurchaseCreate.model_validate(
            {
                "receipt_id": original,
                "merchant_id": merchants[0].id,
                "merchant_name_raw": merchants[0].canonical_name,
                "purchase_type": "RETAIL",
                "category_id": categories[0].id,
                "purchased_at": now,
                "currency": "INR",
                "grand_total": total,
                "subtotal": total,
                "tax_total": "0",
                "discount_total": "0",
                "shipping_total": "0",
                "payment_status": "PAID",
                "notes": MARKER,
                "line_items": lines,
                "payments": [{"method": "UPI", "amount": total, "currency": "INR"}],
            }
        )
    )
    rows = [anchor]
    previous_month = today.replace(day=1) - timedelta(days=1)
    older_month = previous_month.replace(day=1) - timedelta(days=1)
    for i in range(23):
        category = (i % 3) + 1
        merchant = merchants[category]
        day = (
            older_month.replace(day=8 + i)
            if i < 3
            else previous_month.replace(day=8 + i)
            if i < 6
            else today - timedelta(days=i - 5)
        )
        amount = ["180.00", "450.00", "1299.00", "260.00", "680.00", "3499.00"][i % 6]
        currency = "USD" if i == 22 else "INR"
        status = ["PAID", "UNPAID", "PARTIALLY_PAID", "UNKNOWN"][i % 4]
        payment = (
            Decimal(amount)
            if status == "PAID"
            else Decimal(amount) / 2
            if status == "PARTIALLY_PAID"
            else None
        )
        rows.append(
            purchases.create_purchase(
                PurchaseCreate.model_validate(
                    {
                        "merchant_id": merchant.id,
                        "merchant_name_raw": merchant.canonical_name,
                        "category_id": categories[category].id,
                        "purchase_type": "RETAIL",
                        "purchased_at": now.replace(year=day.year, month=day.month, day=day.day),
                        "currency": currency,
                        "grand_total": amount,
                        "payment_status": status,
                        "notes": "Synthetic local demo purchase. Not a real transaction.",
                        "line_items": [
                            {
                                "raw_name": [
                                    "",
                                    "Coffee and breakfast",
                                    "Kitchen essentials",
                                    "Weekend reading",
                                ][category],
                                "category_id": categories[category].id,
                                "quantity": "1",
                                "unit": "each",
                                "line_total": None if i == 7 else amount,
                                "unit_price": None if i == 7 else amount,
                            }
                        ],
                        "payments": []
                        if payment is None
                        else [
                            {
                                "method": "CARD",
                                "amount": payment,
                                "currency": currency,
                                "last4": "4242",
                            }
                        ],
                    }
                )
            )
        )
    receipt_states: tuple[ReceiptStatus, ...] = ("UPLOADED", "NEEDS_REVIEW", "FAILED")
    for status in receipt_states:
        receipt(
            "Demo " + status.lower(),
            status,
            ["Synthetic processing state", "No external extraction", status],
        )

    lots = []
    for index, line in enumerate(anchor.line_items):
        lot = inventory.create_lot(
            LotCreate.model_validate(
                {
                    "idempotency_key": key("lot-" + str(index)),
                    "line_item_id": line.id,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "reason": "Synthetic demo pantry enrollment",
                    "expiry": {}
                    if index == 2
                    else {
                        "source": "USER",
                        "date": today + timedelta(days=[0, 2, 60, -1, 90, 3][index]),
                        "confidence": "1",
                    },
                }
            )
        )
        if index in {0, 1, 4}:
            inventory.record_event(
                lot.id,
                EventCreate.model_validate(
                    {
                        "idempotency_key": key("consume-" + str(index)),
                        "expected_version": lot.version,
                        "event_type": "CONSUMED",
                        "quantity": "1",
                        "reason": "Synthetic demo breakfast",
                    }
                ),
            )
        if index == 5:
            inventory.record_expiry_evidence(
                lot.id,
                EvidenceCorrection.model_validate(
                    {
                        "idempotency_key": key("expiry-estimate"),
                        "expected_version": lot.version,
                        "reason": "Synthetic estimate example, not food-safety advice",
                        "expiry": {
                            "source": "MODEL_ESTIMATE",
                            "date": today + timedelta(days=2),
                            "confidence": "0.65",
                        },
                    }
                ),
            )
        lots.append(lot)
    evaluation = InsightEvaluation(factory, user, now, "Asia/Kolkata")
    for lot in lots:
        candidates = evaluation.inventory(lot.id)
        with session.begin():
            InsightService(session, user).record("lot:" + str(lot.id), candidates, now)
    insights = InsightService(session, user, clock=lambda: now)
    for item, status in zip(insights.list(InsightQuery()), ("READ", "DISMISSED"), strict=False):
        insights.update(
            item.id,
            InsightUpdate.model_validate({"status": status, "expected_version": item.version}),
        )

    memory = MemoryService(session, user, clock=lambda: now)
    for data in [
        {
            "type": "PREFERENCE",
            "content": "Synthetic demo preference: I prefer vegetarian meals.",
            "topics": ["food"],
        },
        {
            "type": "HABIT",
            "content": "Synthetic demo habit: I check the pantry before weekend shopping.",
            "topics": ["inventory", "shopping"],
        },
        {
            "type": "GOAL",
            "content": "Synthetic demo goal: buy fewer duplicate household items.",
            "topics": ["goals"],
        },
    ]:
        memory.create(MemoryCreate.model_validate(data))
    for index, title in enumerate(
        [
            "Demo · Grocery purchase evidence",
            "Demo · Bookshop purchase",
            "Demo · Unavailable assistant",
        ]
    ):
        assistant = AssistantService(
            factory, user, SeedConversationModel(rows[index].id, fail=index == 2), clock=lambda: now
        )
        conversation = assistant.create_conversation(ConversationCreate(title=title))
        try:
            assistant.submit_message(
                conversation.id,
                MessageCreate(
                    content="What was the total for this demo purchase?",
                    idempotency_key=key("message-" + str(index)),
                ),
            )
        except AssistantFailure:
            if index != 2:
                raise

    with session.begin():
        for index, status in enumerate(("SYNCED", "PENDING", "RETRY", "FAILED", "SYNCING")):
            wallet = ensure_pass(session, user.id, rows[index].id, now)
            wallet.status = status
            if status == "SYNCED":
                wallet.class_id, wallet.object_id = (
                    "0.local_demo",
                    "0.local_demo_" + rows[index].id.hex,
                )
                wallet.synced_at = now
            if status in {"RETRY", "FAILED"}:
                wallet.last_error_code, wallet.last_error_at = "demo_example", now
                wallet.attempt_count = 1 if status == "RETRY" else 3
            if status == "SYNCING":
                wallet.lease_token, wallet.lease_expires_at = (
                    key("wallet-lease"),
                    now + timedelta(minutes=5),
                )
    return anchor.id
