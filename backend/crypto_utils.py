import base64
import hashlib
import re
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from key_manager import get_role_key, get_token_salt

def encrypt_data(data: str, role: str) -> str:
    if data is None: return None
    key = get_role_key(role)
    if not key: raise ValueError(f"No encryption key found for role: {role}")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, str(data).encode('utf-8'), None)
    return base64.b64encode(nonce + ct).decode('utf-8')

def decrypt_data(encrypted_b64: str, role: str) -> str:
    if encrypted_b64 is None: return None
    key = get_role_key(role)
    if not key: return "[DECRYPTION_ERROR: No key available for role]"
    try:
        payload = base64.b64decode(encrypted_b64)
        if len(payload) < 13: return "[DECRYPTION_ERROR: Invalid Payload Length]"
        nonce, ct = payload[:12], payload[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode('utf-8')
    except (InvalidTag, ValueError, IndexError):
        return "[DECRYPTION_ERROR: Invalid Key or Corrupt Data]"

def tokenize_data(data: str) -> str:
    if data is None: return None
    salt = get_token_salt()
    if not salt: raise ValueError("Tokenization salt is not available.")
    token = hashlib.sha256(f"{data}{salt}".encode()).hexdigest()
    return f"TOK-{token[:16].upper()}"

