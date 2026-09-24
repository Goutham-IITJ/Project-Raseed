from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.identity.context import CurrentUser, VerifiedIdentity
from backend.app.identity.models import User, UserPreference
from backend.app.identity.schemas import Preferences


class ProvisioningRepository:
    """Bootstrap exception: accepts only the verified external identity capability."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def provision(self, identity: VerifiedIdentity) -> CurrentUser:
        defaults = Preferences().model_dump()
        user_id = self._session.scalar(
            insert(User)
            .values(
                id=uuid4(),
                firebase_uid=identity.firebase_uid,
                email=identity.email,
                display_name=identity.display_name,
                **defaults,
            )
            .on_conflict_do_nothing(index_elements=[User.firebase_uid])
            .returning(User.id)
        )
        if user_id is not None:
            self._session.execute(
                insert(UserPreference),
                [
                    {"id": uuid4(), "user_id": user_id, "key": key, "value": value}
                    for key, value in defaults.items()
                ],
            )
        else:
            # READ COMMITTED gives this statement a fresh snapshot after conflict resolution.
            user_id = self._session.execute(
                select(User.id).where(User.firebase_uid == identity.firebase_uid)
            ).scalar_one()
        return CurrentUser(id=user_id, firebase_uid=identity.firebase_uid)


class UserRepository:
    def __init__(self, session: Session, current_user: CurrentUser) -> None:
        self._session = session
        self._current_user = current_user

    def get(self, *, for_update: bool = False) -> User:
        statement = select(User).where(User.id == self._current_user.id)
        if for_update:
            statement = statement.with_for_update()
        return self._session.execute(statement).scalar_one()


class PreferencesRepository:
    def __init__(self, session: Session, current_user: CurrentUser) -> None:
        self._session = session
        self._current_user = current_user

    def get(self) -> Preferences:
        rows = self._session.execute(
            select(UserPreference.key, UserPreference.value).where(
                UserPreference.user_id == self._current_user.id
            )
        ).all()
        values = {key: value for key, value in rows}
        if set(values) != {"currency", "timezone", "locale"}:
            raise RuntimeError("Provisioned preferences are incomplete")
        return Preferences.model_validate(values)

    def update(self, changes: dict[str, str]) -> None:
        for key, value in changes.items():
            preference = self._session.execute(
                select(UserPreference).where(
                    UserPreference.user_id == self._current_user.id,
                    UserPreference.key == key,
                )
            ).scalar_one()
            preference.value = value
