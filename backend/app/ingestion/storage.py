"""Private backend-only access: no public URLs and no HTTP static-file mount."""

import os
import re
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from google.api_core.exceptions import GoogleAPIError, NotFound
from google.auth.exceptions import GoogleAuthError
from google.cloud import storage

from backend.app.ingestion.errors import StorageUnavailable


class ObjectStorage(Protocol):
    def put_object(self, data: bytes, mime_type: str) -> str: ...
    def get_object(self, reference: str) -> bytes: ...
    def delete_object(self, reference: str) -> None: ...


class LocalStorageProvider:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, reference: str) -> Path:
        if not re.fullmatch(r"local://[0-9a-f]{32}", reference):
            raise StorageUnavailable
        path = self.root / reference.removeprefix("local://")
        if path.is_symlink() or path.resolve().parent != self.root:
            raise StorageUnavailable
        return path

    def put_object(self, data: bytes, mime_type: str) -> str:
        reference = f"local://{uuid4().hex}"
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self._path(reference)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise StorageUnavailable from exc
        return reference

    def get_object(self, reference: str) -> bytes:
        try:
            return self._path(reference).read_bytes()
        except OSError as exc:
            raise StorageUnavailable from exc

    def delete_object(self, reference: str) -> None:
        try:
            self._path(reference).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageUnavailable from exc


class Blob(Protocol):
    def upload_from_string(
        self,
        data: bytes,
        *,
        content_type: str,
        if_generation_match: int,
        timeout: int,
        retry: None,
    ) -> None: ...
    def download_as_bytes(self, *, timeout: int, retry: None) -> bytes: ...
    def delete(self, *, timeout: int, retry: None) -> None: ...


class IAMConfiguration(Protocol):
    uniform_bucket_level_access_enabled: bool
    public_access_prevention: str


class Bucket(Protocol):
    iam_configuration: IAMConfiguration

    def reload(self, *, timeout: int, retry: None) -> None: ...
    def blob(self, name: str) -> Blob: ...


class GCSClient(Protocol):
    def bucket(self, name: str) -> Bucket: ...


class CloudStorageProvider:
    """GCS with ADC, immutable random keys, and enforced private bucket policy."""

    def __init__(self, bucket_name: str, *, client: GCSClient | None = None) -> None:
        self._bucket_name = bucket_name
        self._client = client

    def _bucket(self) -> Bucket:
        if not self._bucket_name:
            raise StorageUnavailable
        if self._client is None:
            self._client = cast(GCSClient, storage.Client())
        bucket = self._client.bucket(self._bucket_name)
        bucket.reload(timeout=30, retry=None)
        iam = bucket.iam_configuration
        if (
            not iam.uniform_bucket_level_access_enabled
            or iam.public_access_prevention != "enforced"
        ):
            raise StorageUnavailable
        return bucket

    def _key(self, reference: str) -> str:
        prefix = f"gs://{self._bucket_name}/receipts/"
        if not reference.startswith(prefix) or not re.fullmatch(
            r"[0-9a-f]{32}", reference.removeprefix(prefix)
        ):
            raise StorageUnavailable
        return "receipts/" + reference.removeprefix(prefix)

    def put_object(self, data: bytes, mime_type: str) -> str:
        reference = f"gs://{self._bucket_name}/receipts/{uuid4().hex}"
        try:
            self._bucket().blob(self._key(reference)).upload_from_string(
                data,
                content_type=mime_type,
                if_generation_match=0,
                timeout=30,
                retry=None,
            )
        except (GoogleAPIError, GoogleAuthError) as exc:
            raise StorageUnavailable from exc
        return reference

    def get_object(self, reference: str) -> bytes:
        key = self._key(reference)
        try:
            return self._bucket().blob(key).download_as_bytes(timeout=30, retry=None)
        except (GoogleAPIError, GoogleAuthError) as exc:
            raise StorageUnavailable from exc

    def delete_object(self, reference: str) -> None:
        key = self._key(reference)
        try:
            self._bucket().blob(key).delete(timeout=30, retry=None)
        except NotFound:
            return
        except (GoogleAPIError, GoogleAuthError) as exc:
            raise StorageUnavailable from exc
