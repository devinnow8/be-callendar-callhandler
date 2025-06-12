from cryptography.fernet import Fernet
import os
import base64
from src.core.config import settings


def encrypt_data(data):
    if not data:
        raise ValueError("Empty credentials dictionary provided")

    # Get encryption key from environment or generate one
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("Encryption key not found")

    try:
        # Create Fernet instance for encryption
        f = Fernet(key)

        # Convert creds dict to string and encrypt
        creds_str = str(data).encode()
        encrypted_creds = f.encrypt(creds_str)

        # Convert to base64 string for storage
        return base64.b64encode(encrypted_creds).decode()

    except Exception as e:
        raise ValueError(f"Failed to encrypt data: {str(e)}")


def decrypt_data(encrypted_data):
    # Get encryption key from environment or generate one
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("Encryption key not found")

    f = Fernet(key)
    # Decode base64 string back to bytes
    try:
        encrypted_bytes = base64.b64decode(encrypted_data)
        decrypted_str = f.decrypt(encrypted_bytes).decode()
        # Convert string representation of dict back to dict
        return decrypted_str
    except Exception as e:
        raise ValueError(f"Failed to decrypt data: {str(e)}")
