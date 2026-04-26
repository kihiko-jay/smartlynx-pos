"""
Credential encryption utilities using Fernet symmetric encryption.

This module provides encrypt/decrypt operations for sensitive credential values
stored in the database. The encryption key is managed via SECRET_ENCRYPTION_KEY
in settings (a 32-byte hex string generated via: openssl rand -hex 32).

Example usage:
    if is_encryption_configured():
        encrypted = encrypt_value("my-secret-api-key")
        # Store encrypted value in database
        ...
        plaintext = decrypt_value(encrypted)
"""

import base64
import binascii
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_encryption_configured() -> bool:
    """
    Check if the encryption key is properly configured.
    
    Returns:
        True if SECRET_ENCRYPTION_KEY is set and valid; False otherwise.
    """
    if not settings.SECRET_ENCRYPTION_KEY:
        return False
    try:
        # Attempt to validate the hex string is 64 chars (32 bytes in hex)
        binascii.unhexlify(settings.SECRET_ENCRYPTION_KEY)
        return True
    except (binascii.Error, ValueError):
        return False


def _get_fernet_key() -> bytes:
    """
    Convert the hex SECRET_ENCRYPTION_KEY to Fernet's required base64 key format.
    
    Raises:
        RuntimeError: if SECRET_ENCRYPTION_KEY is not configured or invalid.
        
    Returns:
        32-byte base64-encoded Fernet key.
    """
    if not settings.SECRET_ENCRYPTION_KEY:
        raise RuntimeError(
            "SECRET_ENCRYPTION_KEY is not configured. Cannot encrypt credentials."
        )
    
    try:
        # Convert hex string to raw bytes
        raw = binascii.unhexlify(settings.SECRET_ENCRYPTION_KEY)
        # Encode as URL-safe base64 for Fernet
        fernet_key = base64.urlsafe_b64encode(raw)
        return fernet_key
    except (binascii.Error, ValueError) as e:
        raise RuntimeError(
            f"SECRET_ENCRYPTION_KEY is invalid (must be 64-char hex string): {e}"
        )


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    """
    Encrypt a plaintext string using Fernet symmetric encryption.
    
    Args:
        plaintext: String to encrypt, or None.
        
    Returns:
        Base64-encoded ciphertext, or None if plaintext is None.
        
    Raises:
        RuntimeError: if SECRET_ENCRYPTION_KEY is not configured.
    """
    if plaintext is None:
        return None
    
    fernet_key = _get_fernet_key()
    cipher = Fernet(fernet_key)
    ciphertext = cipher.encrypt(plaintext.encode("utf-8"))
    return ciphertext.decode("utf-8")


def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    """
    Decrypt a ciphertext string using Fernet symmetric encryption.
    
    Args:
        ciphertext: Base64-encoded ciphertext, or None.
        
    Returns:
        Decrypted plaintext string, or None if ciphertext is None.
        
    Raises:
        RuntimeError: if SECRET_ENCRYPTION_KEY is not configured.
        InvalidToken: if ciphertext is corrupted or was encrypted with a different key.
    """
    if ciphertext is None:
        return None
    
    fernet_key = _get_fernet_key()
    cipher = Fernet(fernet_key)
    try:
        plaintext = cipher.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
    except InvalidToken as e:
        logger.error("Failed to decrypt credential (invalid token or wrong key)")
        raise
