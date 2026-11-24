"""
company.validators — Phase 2.

Logo uploads must be real PNG or JPG images, at most 2 MB.
Both the file extension and the actual image content are checked so a
renamed non-image (or a different image format) cannot be uploaded.
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024
MAX_LOGO_SIZE_LABEL = "2 MB"
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_LOGO_FORMATS = {"PNG", "JPEG"}


def validate_logo_file(uploaded_file) -> None:
    """
    Validate an uploaded logo.

    Raises ``django.core.exceptions.ValidationError`` with a field-friendly
    message when the file is not a PNG/JPG, is larger than 2 MB, or is not a
    real image. The caller stores the file only after this passes.
    """
    if uploaded_file.size > MAX_LOGO_SIZE_BYTES:
        raise ValidationError(
            f"Logo must be {MAX_LOGO_SIZE_LABEL} or smaller."
        )

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_LOGO_EXTENSIONS:
        raise ValidationError("Logo must be a PNG or JPG image.")

    image_format = None
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image_format = image.format
            image.verify()

        # verify() checks the header; load() ensures the image data is real
        # and not a truncated or corrupted file.
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ValidationError("Upload a valid PNG or JPG image.") from exc
    except Image.DecompressionBombError as exc:
        raise ValidationError("Upload a valid PNG or JPG image.") from exc
    finally:
        uploaded_file.seek(0)

    if image_format not in ALLOWED_LOGO_FORMATS:
        raise ValidationError("Logo must be a PNG or JPG image.")
