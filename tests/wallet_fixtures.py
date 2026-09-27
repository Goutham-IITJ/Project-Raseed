from collections import deque

from m7_fixtures import NOW

from backend.app.config import Settings
from backend.app.wallet.google import GoogleWalletProvider
from backend.app.wallet.provider import WalletFailure
from backend.app.wallet.schemas import WalletCreate
from backend.app.wallet.service import WalletService
from backend.app.wallet.worker import LocalWalletTaskQueue, WalletDispatcher, WalletProcessor


def wallet_settings(**changes):
    return Settings(
        _env_file=None,
        wallet_issuer_id="123456789",
        wallet_service_account_email="wallet@test-project.iam.gserviceaccount.com",
        wallet_origins=["https://raseed.example"],
        **changes,
    )


class FakeWallet:
    def __init__(self, *failures):
        self.failures = deque(failures)
        self.calls = []
        self.objects = {}
        self.links = []
        self.link_failure = None
        self.before_sync = None
        self.before_link = None
        self.configured = True

    def identifiers(self, purchase_id):
        if not self.configured:
            raise WalletFailure("wallet_configuration")
        return GoogleWalletProvider(wallet_settings()).identifiers(purchase_id)

    def sync(self, projection):
        self.calls.append(projection)
        if self.before_sync:
            self.before_sync()
        if self.failures:
            raise self.failures.popleft()
        self.objects[projection.object_id] = projection

    def save_link(self, class_id, object_id, now):
        if self.before_link:
            self.before_link()
        if self.link_failure:
            raise self.link_failure
        self.links.append((class_id, object_id, now))
        return "https://pay.google.com/gp/v/save/fake.signed.token"


def ensure(env, purchase, provider=None, user=None, now=NOW):
    with env.factory() as session:
        return WalletService(
            session, user or env.alice, provider or FakeWallet(), clock=lambda: now
        ).create(WalletCreate(purchase_id=purchase.id))


def worker(env, provider=None, clock=lambda: NOW):
    fake = provider or FakeWallet()
    processor = WalletProcessor(env.factory, fake, clock=clock)
    dispatcher = WalletDispatcher(env.factory, LocalWalletTaskQueue(processor), clock=clock)
    return processor, dispatcher, fake
