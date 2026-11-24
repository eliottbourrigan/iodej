"""Enregistrement des photos uploadées : redressées, réduites, converties en WebP."""
import uuid

from fastapi import UploadFile
from PIL import Image, ImageOps

from . import config

MAX_SIDE = 1000


class InvalidImage(ValueError):
    pass


async def save_upload(upload: UploadFile | None) -> str | None:
    """Retourne le nom du fichier enregistré, ou None si aucun fichier."""
    if upload is None or not upload.filename:
        return None
    data = await upload.read()
    if not data:
        return None
    from io import BytesIO

    try:
        img = Image.open(BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise InvalidImage("Ce fichier n'est pas une image valide.") from exc
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    name = f"{uuid.uuid4().hex}.webp"
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    img.save(config.UPLOAD_DIR / name, "WEBP", quality=82, method=4)
    return name


def delete(name: str | None) -> None:
    if not name:
        return
    path = (config.UPLOAD_DIR / name).resolve()
    if path.parent == config.UPLOAD_DIR.resolve() and path.exists():
        path.unlink()
