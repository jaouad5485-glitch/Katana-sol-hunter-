"""Encrypted wallet key storage."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyManager:
    """Stores wallet secrets encrypted at rest with AES-256-GCM."""

    def __init__(self, key_path: str, encryption_key: str) -> None:
        self._path = Path(key_path)
        key_bytes = encryption_key.encode()[:32].ljust(32, b"0")
        self._aes = AESGCM(key_bytes)

    def encrypt_and_store(self, wallet_payload: dict[str, str]) -> None:
        """Encrypt a wallet payload and write it to disk."""
        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, json.dumps(wallet_payload).encode(), None)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode()}))

    def load(self) -> dict[str, str]:
        """Decrypt and return the stored wallet payload."""
        data = json.loads(self._path.read_text())
        nonce = base64.b64decode(data["nonce"])
        ciphertext = base64.b64decode(data["ciphertext"])
        return json.loads(self._aes.decrypt(nonce, ciphertext, None).decode())
