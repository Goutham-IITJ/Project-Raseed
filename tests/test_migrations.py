import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from conftest import migration_config
from sqlalchemy import func, inspect, select, text
from test_purchase_validation import purchase_data, receipt_data

from backend.app.database import Base, make_session_factory
from backend.app.identity.context import VerifiedIdentity
from backend.app.identity.models import User, UserPreference
from backend.app.identity.service import provision_user
from backend.app.inventory.worker import (
    InventoryDispatcher,
    InventoryProcessor,
    LocalInventoryTaskQueue,
)
from backend.app.purchases.models import Category, OutboxEvent, Purchase, Receipt
from backend.app.purchases.schemas import CategoryCreate, PurchaseCreate, ReceiptCreate
from backend.app.purchases.service import PurchaseService

pytestmark = pytest.mark.integration


def test_migration_from_empty_database_and_model_agreement(migrated_engine, database_url):
    config = migration_config(database_url)
    command.downgrade(config, "base")
    assert set(inspect(migrated_engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    inspector = inspect(migrated_engine)
    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "users",
        "user_preferences",
        "receipts",
        "extraction_runs",
        "merchants",
        "categories",
        "products",
        "purchases",
        "line_items",
        "payments",
        "outbox_events",
        "inventory_items",
        "inventory_lots",
        "inventory_events",
    }
    assert any(
        constraint["column_names"] == ["firebase_uid"]
        for constraint in inspector.get_unique_constraints("users")
    )
    with migrated_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    command.upgrade(config, "head")  # Re-running the migration command is safe.


def test_upgrade_from_milestone_one_preserves_identity(migrated_engine, database_url):
    config = migration_config(database_url)
    command.downgrade(config, "0001_identity")
    with make_session_factory(migrated_engine)() as session:
        current = provision_user(session, VerifiedIdentity("migration-existing-user"))
    command.upgrade(config, "head")
    with make_session_factory(migrated_engine)() as session:
        assert session.get(User, current.id).firebase_uid == "migration-existing-user"
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserPreference)
                .where(UserPreference.user_id == current.id)
            )
            == 3
        )
        assert session.scalar(select(func.count()).select_from(Category)) == 0
    columns = {
        column["name"]: column for column in inspect(migrated_engine).get_columns("purchases")
    }
    assert columns["grand_total"]["type"].precision == 20
    assert columns["grand_total"]["type"].scale == 6
    assert columns["purchased_at"]["type"].timezone is True
    assert columns["grand_total"]["nullable"] is False
    assert columns["subtotal"]["nullable"] is True


def test_ingestion_upgrade_preserves_milestone_two_canonical_data(database, database_url):
    factory = make_session_factory(database)
    with factory() as session:
        current = provision_user(session, VerifiedIdentity("existing-m2-user"))
        service = PurchaseService(session, current)
        receipt = service.create_receipt(ReceiptCreate.model_validate(receipt_data()))
        purchase = service.create_purchase(
            PurchaseCreate.model_validate(purchase_data(receipt_id=receipt.id))
        )
    config = migration_config(database_url)
    command.downgrade(config, "0002_purchase_foundation")
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM purchases")) == 1
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 1
    command.upgrade(config, "head")
    with factory() as session:
        assert session.get(Purchase, purchase.id).grand_total == purchase.grand_total
        assert session.get(Receipt, receipt.id).attempt_count == 0
        assert session.get(Receipt, receipt.id).lease_token is None
        event = session.scalars(select(OutboxEvent)).one()
        assert event.purchase_id == purchase.id and event.receipt_id is None


def test_inventory_roundtrip_preserves_purchase_and_requeues_delivery(database, database_url):
    factory = make_session_factory(database)
    with factory() as session:
        owner = provision_user(session, VerifiedIdentity("m4-migration-owner"))
        service = PurchaseService(session, owner)
        category = service.create_category(
            CategoryCreate(
                name="Fixture",
                slug="fixture",
                inventory_eligible=True,
            )
        )
        purchase = service.create_purchase(
            PurchaseCreate.model_validate(
                purchase_data(
                    line_items=[
                        {
                            "raw_name": "Stock",
                            "quantity": "2",
                            "unit": "each",
                            "category_id": category.id,
                        }
                    ],
                )
            )
        )
    dispatcher = InventoryDispatcher(factory, LocalInventoryTaskQueue(InventoryProcessor(factory)))
    assert dispatcher.dispatch_once() == 1
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM inventory_events")) == 1
    config = migration_config(database_url)
    command.downgrade(config, "0003_receipt_ingestion")
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM purchases")) == 1
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 1
        assert connection.scalar(text("SELECT published_at FROM outbox_events")) is None
    command.upgrade(config, "head")
    with factory() as session:
        assert session.get(Purchase, purchase.id).grand_total == purchase.grand_total
        assert session.get(Category, category.id).inventory_eligible is None
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM inventory_events")) == 0


def test_analytics_index_roundtrip_preserves_all_canonical_and_inventory_data(
    database, database_url
):
    factory = make_session_factory(database)
    with factory() as session:
        owner = provision_user(session, VerifiedIdentity("m5-migration-owner"))
        service = PurchaseService(session, owner)
        category = service.create_category(
            CategoryCreate(name="Fixture", slug="fixture", inventory_eligible=True)
        )
        service.create_purchase(
            PurchaseCreate.model_validate(
                purchase_data(
                    category_id=category.id,
                    payment_status="PAID",
                    payments=[{"method": "CASH", "amount": "0.30", "currency": "INR"}],
                    line_items=[
                        {
                            "raw_name": "Fixture stock",
                            "category_id": category.id,
                            "quantity": "2",
                            "unit": "each",
                            "line_total": "0.30",
                        }
                    ],
                )
            )
        )
    dispatcher = InventoryDispatcher(factory, LocalInventoryTaskQueue(InventoryProcessor(factory)))
    assert dispatcher.dispatch_once() == 1

    def records():
        # Fixed test table names; the fixture has already verified a disposable database.
        tables = (
            "users",
            "user_preferences",
            "categories",
            "purchases",
            "line_items",
            "payments",
            "inventory_items",
            "inventory_lots",
            "inventory_events",
            "outbox_events",
        )
        with database.connect() as connection:
            return {
                table: list(
                    connection.scalars(
                        text(f"SELECT row_to_json(record)::text FROM {table} record ORDER BY id")
                    )
                )
                for table in tables
            }

    before = records()
    config = migration_config(database_url)
    command.downgrade(config, "0004_inventory")
    assert records() == before
    assert "ix_line_items_product" in {
        row["name"] for row in inspect(database).get_indexes("line_items")
    }
    assert "ix_purchases_user_currency_purchased" not in {
        row["name"] for row in inspect(database).get_indexes("purchases")
    }
    command.upgrade(config, "head")
    assert records() == before
    assert "ix_line_items_product_purchase" in {
        row["name"] for row in inspect(database).get_indexes("line_items")
    }
    assert "ix_purchases_user_currency_purchased" in {
        row["name"] for row in inspect(database).get_indexes("purchases")
    }
