from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Forbidden, NotFound
from requests.exceptions import ConnectionError, Timeout

from backend.app.ingestion.errors import StorageUnavailable
from backend.app.ingestion.storage import CloudStorageProvider, LocalStorageProvider


def test_local_private_store_retrieve_delete(tmp_path):
    provider = LocalStorageProvider(tmp_path / "private")
    reference = provider.put_object(b"receipt", "image/png")
    assert reference.startswith("local://") and str(tmp_path) not in reference
    assert provider.get_object(reference) == b"receipt"
    other = provider.put_object(b"receipt", "image/png")
    assert other != reference
    provider.delete_object(reference)
    provider.delete_object(reference)
    with pytest.raises(StorageUnavailable):
        provider.get_object(reference)
    assert provider.get_object(other) == b"receipt"


@pytest.mark.parametrize(
    "reference",
    [
        "../secrets",
        "local://../secrets",
        "file:///etc/passwd",
        "https://public.test/file",
        "local://" + "a" * 32 + "/../outside",
    ],
)
def test_local_references_cannot_escape_private_root(tmp_path, reference):
    provider = LocalStorageProvider(tmp_path)
    with pytest.raises(StorageUnavailable):
        provider.get_object(reference)
    with pytest.raises(StorageUnavailable):
        provider.delete_object(reference)


def cloud_provider():
    blob = Mock()
    blob.download_as_bytes.return_value = b"receipt"
    bucket = Mock()
    bucket.blob.return_value = blob
    bucket.iam_configuration = SimpleNamespace(
        uniform_bucket_level_access_enabled=True, public_access_prevention="enforced"
    )
    client = Mock()
    client.bucket.return_value = bucket
    return CloudStorageProvider("private-bucket", client=client), bucket, blob


def test_gcs_private_operations_use_no_public_acl_and_disable_hidden_retries():
    provider, bucket, blob = cloud_provider()
    reference = provider.put_object(b"receipt", "application/pdf")
    assert reference.startswith("gs://private-bucket/receipts/")
    blob.upload_from_string.assert_called_once_with(
        b"receipt", content_type="application/pdf", if_generation_match=0, timeout=30, retry=None
    )
    assert provider.get_object(reference) == b"receipt"
    provider.delete_object(reference)
    blob.delete.assert_called_once_with(timeout=30, retry=None)
    assert bucket.reload.call_count == 3
    assert not blob.make_public.called and not blob.generate_signed_url.called


@pytest.mark.parametrize("uniform,prevention", [(False, "enforced"), (True, "inherited")])
def test_gcs_fails_closed_for_unverified_private_bucket(uniform, prevention):
    provider, bucket, blob = cloud_provider()
    bucket.iam_configuration.uniform_bucket_level_access_enabled = uniform
    bucket.iam_configuration.public_access_prevention = prevention
    with pytest.raises(StorageUnavailable):
        provider.put_object(b"receipt", "image/png")
    assert not blob.upload_from_string.called


def test_gcs_rejects_foreign_bucket_and_hides_sdk_errors():
    provider, _, blob = cloud_provider()
    with pytest.raises(StorageUnavailable):
        provider.get_object("gs://someone-else/receipts/" + "a" * 32)
    blob.upload_from_string.side_effect = Forbidden("sensitive")
    with pytest.raises(StorageUnavailable):
        provider.put_object(b"receipt", "image/png")
    blob.delete.side_effect = NotFound("missing")
    provider.delete_object("gs://private-bucket/receipts/" + "a" * 32)


def test_gcs_emulator_override_fails_closed(monkeypatch):
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://127.0.0.1:4443")
    provider, bucket, _ = cloud_provider()
    with pytest.raises(StorageUnavailable):
        provider.put_object(b"receipt", "image/png")
    bucket.reload.assert_not_called()


@pytest.mark.parametrize(
    "failure", [ConnectionError("secret"), Timeout("secret"), ValueError("ADC")]
)
@pytest.mark.parametrize("operation", ["put", "get", "delete"])
def test_gcs_transport_and_configuration_failures_stay_safe(failure, operation):
    provider, bucket, _ = cloud_provider()
    bucket.reload.side_effect = failure
    with pytest.raises(StorageUnavailable):
        if operation == "put":
            provider.put_object(b"receipt", "image/png")
        else:
            getattr(provider, operation + "_object")("gs://private-bucket/receipts/" + "a" * 32)
