import pytest
from pydantic import ValidationError

from backend.app.identity.schemas import PreferencePatch


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"currency": None},
        {"timezone": None},
        {"locale": None},
        {"currency": "usd"},
        {"currency": "ZZZ"},
        {"currency": 10},
        {"timezone": "Mars/Olympus"},
        {"timezone": "../UTC"},
        {"locale": "not-a-locale"},
        {"locale": "en_US"},
        {"user_id": "another-user"},
        {"firebase_uid": "another-user"},
        {"budget": "1000"},
    ],
)
def test_invalid_or_unauthorized_preference_fields(body):
    with pytest.raises(ValidationError):
        PreferencePatch.model_validate(body)


def test_locale_normalization_and_partial_update():
    patch = PreferencePatch(locale="en-us")
    assert patch.model_dump(exclude_unset=True) == {"locale": "en-US"}
