"""Content-addressed file storage for uploads and deliverables.

Files are stored under sha256, so the same photograph uploaded twice occupies
one blob. That is not a space optimisation -- it is how a re-order of the same
listing costs nothing to store, and how "did this client already send us this
photo" is answerable with a lookup instead of a diff.

Originals are IMMUTABLE. We never retouch, crop or re-encode a client's
photograph: the whole compliance position rests on the file on the originals
page being the file they sent. Write-once, read-many, no edit path exists.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024


class UploadRejected(ValueError):
    """Raised with a message meant for the customer, not a stack trace."""


@dataclass(frozen=True)
class Stored:
    sha256: str
    bytes: int
    path: Path


# Magic bytes, checked against the real file rather than the declared type.
# A browser's Content-Type is whatever the client says it is; renaming
# invoice.pdf to photo.jpg is a two-second attack and this is the two-line fix.
SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def sniff(head: bytes) -> str | None:
    for magic, mime in SIGNATURES:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF: ISO-BMFF box, brand at offset 8.
    if head[4:8] == b"ftyp" and head[8:12] in (
            b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
        return "image/heic"
    return None


def _size(n: int) -> str:
    """Customer-facing, so it must never read "larger than 0 MB"."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} bytes"


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        # Two levels of fan-out: 256 dirs at each, so no directory ever holds
        # enough entries to make listing it slow.
        return self.root / digest[:2] / digest[2:4] / digest

    def put(self, src: BinaryIO, *, max_bytes: int,
            allowed: frozenset[str]) -> Stored:
        """Stream to a temp file, hashing as we go, and reject the moment the
        size cap is passed rather than after buffering the whole thing. A cap
        enforced after the read is not a cap."""
        tmp = self.root / f".incoming-{id(src):x}"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        total = 0
        head = b""
        try:
            with open(tmp, "wb") as out:
                while True:
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise UploadRejected(
                            f"that file is larger than {_size(max_bytes)}")
                    if not head:
                        head = chunk[:16]
                    h.update(chunk)
                    out.write(chunk)

            if total == 0:
                raise UploadRejected("that file is empty")
            actual = sniff(head)
            if actual is None:
                raise UploadRejected(
                    "that is not a photograph we can read — send JPEG, PNG, "
                    "WebP or HEIC straight off the camera or phone")
            if actual not in allowed:
                raise UploadRejected(f"we cannot use {actual} files")

            digest = h.hexdigest()
            dest = self._path(digest)
            if dest.exists():
                tmp.unlink()                      # already have this exact file
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp), dest)
                dest.chmod(0o444)                 # originals are immutable
            return Stored(sha256=digest, bytes=total, path=dest)
        finally:
            tmp.unlink(missing_ok=True)

    def get(self, digest: str) -> Path:
        p = self._path(digest)
        if not p.is_file():
            raise FileNotFoundError(digest)
        return p

    def put_bytes(self, data: bytes) -> Stored:
        """For deliverables we generated ourselves -- no sniffing, we made them."""
        digest = hashlib.sha256(data).hexdigest()
        dest = self._path(digest)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            dest.chmod(0o444)
        return Stored(sha256=digest, bytes=len(data), path=dest)

    def put_file(self, path: Path) -> Stored:
        h = hashlib.sha256()
        total = 0
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
                total += len(chunk)
        digest = h.hexdigest()
        dest = self._path(digest)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            dest.chmod(0o444)
        return Stored(sha256=digest, bytes=total, path=dest)
