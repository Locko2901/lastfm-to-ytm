"""Teleporter: encrypted export/import of entire configuration."""

from __future__ import annotations

import json
import logging
import os
import struct
import time
from pathlib import Path

from src.config import CACHE_DIR, CONFIG_DIR

from .env import BROWSER_JSON_FILE, ENV_FILE

logger = logging.getLogger(__name__)

TELEPORTER_VERSION = 1
_FORMAT_VERSION = 0x01

# KDF identifiers
_KDF_ARGON2ID = 0x01

# Argon2id defaults (128 MiB memory, 3 iterations, 4 threads)
_ARGON2_MEMORY_KIB = 131_072  # 128 MiB
_ARGON2_ITERATIONS = 3
_ARGON2_PARALLELISM = 4
_ARGON2_KEY_LEN = 32  # 256-bit key for AES-256-GCM

MIN_PASSWORD_LENGTH = 8

# Magic bytes to identify teleporter files
_MAGIC = b"TPRT"

# Header struct: version(B) + kdf_id(B) + mem(I) + iters(I) + parallelism(I) = 14 bytes
_HEADER_STRUCT = struct.Struct(">BB III")
_SALT_LEN = 16
_NONCE_LEN = 12  # AES-GCM standard nonce

_CONFIG_FILES: list[tuple[str, Path]] = [
    ("env", ENV_FILE),
    ("browser_json", BROWSER_JSON_FILE),
    ("search_overrides", CONFIG_DIR / "search_overrides.json"),
    ("tag_overrides", CONFIG_DIR / "tag_overrides.json"),
    ("custom_playlists", CONFIG_DIR / "custom_playlists.json"),
]

_CACHE_FILES: dict[str, Path] = {
    "search_cache": CACHE_DIR / ".search_cache.json",
    "tag_cache": CACHE_DIR / ".tag_cache.json",
    "playlist_cache": CACHE_DIR / ".playlist_cache.json",
    "theme_overrides": CACHE_DIR / ".theme_overrides.json",
}


def _derive_key_argon2(password: str, salt: bytes, *, memory_kib: int, iterations: int, parallelism: int) -> bytes:
    """Derive a 256-bit key using Argon2id."""
    from argon2.low_level import Type, hash_secret_raw

    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=iterations,
        memory_cost=memory_kib,
        parallelism=parallelism,
        hash_len=_ARGON2_KEY_LEN,
        type=Type.ID,
    )


def _encrypt_aes_gcm(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes, bytes]:
    """Encrypt with AES-256-GCM. Returns (nonce, ciphertext, tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct_with_tag[: len(ct_with_tag) - 16], ct_with_tag[len(ct_with_tag) - 16 :]


def _decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes) -> bytes:
    """Decrypt AES-256-GCM. Raises on auth failure."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext + tag, aad)


def _decrypt_payload(data: bytes, password: str) -> bytes:
    """Decrypt a teleporter file."""
    magic_len = len(_MAGIC)
    if len(data) < magic_len or data[:magic_len] != _MAGIC:
        raise ValueError("Not a teleporter file")

    header_len = _HEADER_STRUCT.size
    aad_len = magic_len + header_len
    min_len = aad_len + _SALT_LEN + _NONCE_LEN + 16
    if len(data) < min_len:
        raise ValueError("Invalid teleporter file: too short")

    header = data[magic_len : magic_len + header_len]
    _ver, kdf_id, mem_kib, iters, par = _HEADER_STRUCT.unpack(header)
    if _ver != _FORMAT_VERSION:
        raise ValueError("Unsupported teleporter version")
    if kdf_id != _KDF_ARGON2ID:
        raise ValueError(f"Unsupported KDF (id={kdf_id})")

    aad = data[:aad_len]
    offset = aad_len
    salt = data[offset : offset + _SALT_LEN]
    offset += _SALT_LEN
    nonce = data[offset : offset + _NONCE_LEN]
    offset += _NONCE_LEN
    ct_and_tag = data[offset:]

    if len(ct_and_tag) < 16:
        raise ValueError("Invalid teleporter file: truncated")

    ciphertext = ct_and_tag[:-16]
    tag = ct_and_tag[-16:]

    key = _derive_key_argon2(password, salt, memory_kib=mem_kib, iterations=iters, parallelism=par)
    try:
        return _decrypt_aes_gcm(key, nonce, ciphertext, tag, aad=aad)
    except Exception:
        raise ValueError("Wrong password or corrupted file") from None


def export_config(password: str, *, cache_keys: list[str] | None = None) -> bytes:
    """Collect all config files, encrypt with password, return bytes."""
    bundle: dict = {
        "_teleporter_meta": {
            "version": TELEPORTER_VERSION,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "files": {},
    }

    file_list = list(_CONFIG_FILES)
    file_list.extend((key, _CACHE_FILES[key]) for key in cache_keys or [] if key in _CACHE_FILES)

    for key, path in file_list:
        if path.exists():
            try:
                bundle["files"][key] = path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Teleporter: could not read %s", path)

    plaintext = json.dumps(bundle, ensure_ascii=False).encode("utf-8")

    salt = os.urandom(_SALT_LEN)
    key = _derive_key_argon2(
        password,
        salt,
        memory_kib=_ARGON2_MEMORY_KIB,
        iterations=_ARGON2_ITERATIONS,
        parallelism=_ARGON2_PARALLELISM,
    )

    header = _HEADER_STRUCT.pack(
        _FORMAT_VERSION,
        _KDF_ARGON2ID,
        _ARGON2_MEMORY_KIB,
        _ARGON2_ITERATIONS,
        _ARGON2_PARALLELISM,
    )

    aad = _MAGIC + header
    nonce, ciphertext, tag = _encrypt_aes_gcm(key, plaintext, aad=aad)

    return _MAGIC + header + salt + nonce + ciphertext + tag


def import_config(data: bytes, password: str) -> dict:
    """Decrypt and restore config files. Returns summary dict."""
    plaintext = _decrypt_payload(data, password)
    bundle = json.loads(plaintext.decode("utf-8"))

    meta = bundle.get("_teleporter_meta", {})
    version = meta.get("version", 0)
    if version > TELEPORTER_VERSION:
        raise ValueError(f"Unsupported teleporter version {version}")

    files = bundle.get("files", {})
    restored = []
    skipped = []

    all_known_files = list(_CONFIG_FILES) + list(_CACHE_FILES.items())
    for key, path in all_known_files:
        if key not in files:
            skipped.append(key)
            continue

        content = files[key]

        if path.suffix == ".json":
            try:
                json.loads(content)
            except (json.JSONDecodeError, TypeError):
                skipped.append(key)
                logger.warning("Teleporter: skipping %s – invalid JSON", key)
                continue

        path.parent.mkdir(parents=True, exist_ok=True)

        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
            restored.append(key)
        except OSError:
            logger.error("Teleporter: failed to write %s", path)
            skipped.append(key)
            if tmp.exists():
                tmp.unlink()

    return {
        "restored": restored,
        "skipped": skipped,
        "exported_at": meta.get("exported_at"),
    }


def preview_config(data: bytes, password: str) -> dict:
    """Decrypt and return a summary without applying changes."""
    plaintext = _decrypt_payload(data, password)
    bundle = json.loads(plaintext.decode("utf-8"))
    meta = bundle.get("_teleporter_meta", {})
    files = bundle.get("files", {})

    file_labels = {
        "env": ".env",
        "browser_json": "browser.json",
        "search_overrides": "search_overrides.json",
        "tag_overrides": "tag_overrides.json",
        "custom_playlists": "custom_playlists.json",
        "search_cache": "search_cache.json",
        "tag_cache": "tag_cache.json",
        "playlist_cache": "playlist_cache.json",
        "theme_overrides": "theme_overrides.json",
    }

    included = []
    for key in files:
        label = file_labels.get(key, key)
        included.append(label)

    return {
        "version": meta.get("version"),
        "exported_at": meta.get("exported_at"),
        "files": included,
        "file_count": len(included),
    }
