"""Crypto helpers for cube protocols."""

from __future__ import annotations

from typing import Iterable, List

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class AesEcb:
    """AES-128 ECB helper for block operations."""

    def __init__(self, key: Iterable[int]) -> None:
        key_bytes = bytes(int(b) & 0xFF for b in key)
        self._cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())

    def decrypt_block(self, block: Iterable[int]) -> List[int]:
        decryptor = self._cipher.decryptor()
        data = bytes(int(b) & 0xFF for b in block)
        return list(decryptor.update(data) + decryptor.finalize())

    def encrypt_block(self, block: Iterable[int]) -> List[int]:
        encryptor = self._cipher.encryptor()
        data = bytes(int(b) & 0xFF for b in block)
        return list(encryptor.update(data) + encryptor.finalize())

    def decrypt(self, data: Iterable[int]) -> List[int]:
        """Decrypt a buffer (length must be a multiple of 16)."""
        decryptor = self._cipher.decryptor()
        raw = bytes(int(b) & 0xFF for b in data)
        return list(decryptor.update(raw) + decryptor.finalize())

    def encrypt(self, data: Iterable[int]) -> List[int]:
        """Encrypt a buffer (length must be a multiple of 16)."""
        encryptor = self._cipher.encryptor()
        raw = bytes(int(b) & 0xFF for b in data)
        return list(encryptor.update(raw) + encryptor.finalize())
