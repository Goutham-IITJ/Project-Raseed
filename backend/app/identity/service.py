from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser, VerifiedIdentity
from backend.app.identity.repositories import (
    PreferencesRepository,
    ProvisioningRepository,
    UserRepository,
)
from backend.app.identity.schemas import PreferencePatch, Preferences, UserView


def provision_user(session: Session, identity: VerifiedIdentity) -> CurrentUser:
    with session.begin():
        return ProvisioningRepository(session).provision(identity)


class UserService:
    def __init__(self, session: Session, current_user: CurrentUser) -> None:
        self._session = session
        self._users = UserRepository(session, current_user)
        self._preferences = PreferencesRepository(session, current_user)

    def get_user(self) -> UserView:
        with self._session.begin():
            return UserView.model_validate(self._users.get())

    def get_preferences(self) -> Preferences:
        with self._session.begin():
            return self._preferences.get()

    def patch_preferences(self, patch: PreferencePatch) -> Preferences:
        changes: dict[str, str] = patch.model_dump(exclude_unset=True)
        with self._session.begin():
            user = self._users.get(for_update=True)
            self._preferences.update(changes)
            for key, value in changes.items():
                setattr(user, key, value)
            self._session.flush()
            preferences = self._preferences.get()
        # The commit completes before the API can send a successful response.
        return preferences
