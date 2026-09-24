import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from babel import Locale, UnknownLocaleError
from babel.core import get_global
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    firebase_uid: str
    email: str | None
    display_name: str | None
    currency: str
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime


class Preferences(BaseModel):
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    locale: str = "en-IN"


class PreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    currency: str | None = None
    timezone: str | None = None
    locale: str | None = None

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str:
        if value is None or not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Currency must be an uppercase three-letter code")
        if value not in get_global("all_currencies"):
            raise ValueError("Unknown currency")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str:
        if value is None or len(value) > 100:
            raise ValueError("Timezone must be an IANA name")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        return value

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str:
        if value is None or not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,4}){0,2}", value):
            raise ValueError("Locale must be a language[-Script][-REGION] tag")
        try:
            return str(Locale.parse(value, sep="-")).replace("_", "-")
        except (UnknownLocaleError, ValueError) as exc:
            raise ValueError("Unknown locale") from exc

    @model_validator(mode="after")
    def nonempty(self) -> "PreferencePatch":
        if not self.model_fields_set:
            raise ValueError("Supply at least one preference")
        return self


class UserResponse(BaseModel):
    data: UserView


class PreferencesResponse(BaseModel):
    data: Preferences
