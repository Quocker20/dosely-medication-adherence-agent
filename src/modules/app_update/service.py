"""APK release metadata: configured download URL and cached SHA-256 (SEC-11)."""

import asyncio
import hashlib
import logging
from pathlib import Path, PurePath

from src.core.config import Settings

logger = logging.getLogger(__name__)

# Bind-mounted outside the Docker image (see docker-compose.yml); src/main.py serves it.
DOWNLOADS_DIR = Path(__file__).resolve().parents[3] / "downloads"

_HASH_CHUNK = 1024 * 1024

# path -> (mtime_ns, size, sha256). One entry per APK filename ever served.
_sha256_cache: dict[Path, tuple[int, int, str]] = {}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_of_apk(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        logger.warning("APK %s not found; update metadata will carry no checksum", path.name)
        return None
    cached = _sha256_cache.get(path)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = _hash_file(path)
    _sha256_cache[path] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


async def apk_sha256(filename: str) -> str | None:
    """SHA-256 of the APK, recomputed only when its mtime or size changes."""
    return await asyncio.to_thread(_sha256_of_apk, DOWNLOADS_DIR / filename)


def apk_filename(settings: Settings) -> str:
    return PurePath(settings.android_latest_apk_filename).name


def download_url(settings: Settings, filename: str) -> str:
    """Absolute URL built from configuration only, never from the request's Host."""
    return f"{settings.android_download_base_url}/downloads/{filename}"
