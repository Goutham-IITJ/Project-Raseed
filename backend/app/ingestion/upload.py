import hashlib
import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from fastapi import Request
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from backend.app.config import Settings
from backend.app.ingestion.errors import UnsupportedReceipt, UploadTooLarge
from backend.app.purchases.errors import DomainError
from backend.app.purchases.schemas import ReceiptCreate


@dataclass(frozen=True)
class Upload:
    filename: str
    mime_type: str
    data: bytes


async def read_upload(request: Request, limit: int) -> Upload:
    size = 0
    too_large = False

    async def bounded_stream() -> AsyncGenerator[bytes, None]:
        nonlocal size, too_large
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit + 64 * 1024:
                too_large = True
                # Starlette closes any spooled files on MultiPartException.
                raise MultiPartException("Upload too large")
            yield chunk

    try:
        parser = MultiPartParser(
            request.headers, bounded_stream(), max_files=1, max_fields=0, max_part_size=1024
        )
        form = await parser.parse()
    except MultiPartException as exc:
        if too_large:
            raise UploadTooLarge from exc
        raise DomainError from exc
    try:
        file = form.get("file")
        if len(form.multi_items()) != 1 or not isinstance(file, UploadFile):
            raise DomainError
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise UploadTooLarge
        return Upload(file.filename or "", file.content_type or "", data)
    finally:
        await form.close()


def validate_upload(upload: Upload, settings: Settings) -> ReceiptCreate:
    data = upload.data
    if len(data) > settings.max_upload_bytes:
        raise UploadTooLarge
    extension = PurePath(upload.filename).suffix.lower()
    allowed = {"image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}, "application/pdf": {".pdf"}}
    if not data or extension not in allowed.get(upload.mime_type, set()):
        raise UnsupportedReceipt
    try:
        if upload.mime_type == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise UnsupportedReceipt
            pdf = PdfReader(BytesIO(data), strict=True)
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= settings.max_pdf_pages:
                raise UnsupportedReceipt
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as picture:
                    expected = "JPEG" if upload.mime_type == "image/jpeg" else "PNG"
                    if picture.format != expected or picture.width * picture.height > 25_000_000:
                        raise UnsupportedReceipt
                    picture.verify()
                # JPEG verification can inspect headers without decoding pixel data.
                with Image.open(BytesIO(data)) as picture:
                    picture.load()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        PdfReadError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise UnsupportedReceipt from exc
    try:
        return ReceiptCreate.model_validate(
            {
                "original_filename": upload.filename,
                "mime_type": upload.mime_type,
                "file_size": len(data),
                "content_hash": hashlib.sha256(data).hexdigest(),
                "source": "USER_UPLOAD",
            }
        )
    except ValidationError as exc:
        raise DomainError from exc
