import os
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import firebase_admin
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError
from google.auth.exceptions import GoogleAuthError

from backend.app.config import configured
from backend.app.identity.context import (
    InvalidToken,
    VerificationUnavailable,
    VerifiedIdentity,
)


class FirebaseTokenVerifier:
    """The only production token adapter. No decoding-only or emulator fallback."""

    def __init__(self, project_id: str, credentials_path: Path | None = None) -> None:
        self._project_id = project_id
        self._credentials_path = credentials_path
        self._app: Any = None
        self._lock = Lock()

    def _get_app(self) -> Any:
        if not configured(self._project_id) or os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
            raise VerificationUnavailable("Firebase project configuration is required")
        with self._lock:
            if self._app is None:
                # An explicit local key takes precedence; None preserves managed/default ADC.
                credential = None
                if self._credentials_path is not None:
                    try:
                        credential = credentials.Certificate(str(self._credentials_path))
                    except (OSError, ValueError, TypeError, AttributeError) as exc:
                        # The SDK also assumes parsed JSON is an object with typed fields.
                        raise VerificationUnavailable from exc
                # An adapter owns its app; no dependence on an implicitly configured default app.
                self._app = firebase_admin.initialize_app(
                    credential=credential,
                    options={"projectId": self._project_id},
                    name=f"raseed-{uuid4()}",
                )
        return self._app

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            claims = auth.verify_id_token(token, app=self._get_app(), check_revoked=True)
        except (
            auth.InvalidIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
        ) as exc:
            raise InvalidToken from exc
        except (FirebaseError, GoogleAuthError, OSError, ValueError) as exc:
            raise VerificationUnavailable from exc

        uid = claims.get("uid")
        if not isinstance(uid, str) or not uid.strip() or len(uid) > 128:
            raise InvalidToken
        email = claims.get("email")
        name = claims.get("name")
        return VerifiedIdentity(
            firebase_uid=uid,
            email=email if isinstance(email, str) else None,
            display_name=name if isinstance(name, str) else None,
        )

    def close(self) -> None:
        if self._app is not None:
            firebase_admin.delete_app(self._app)
            self._app = None
