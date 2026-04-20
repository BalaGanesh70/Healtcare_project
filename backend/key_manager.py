import os
import base64
import json
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv, set_key, get_key

ROLES = ["doctor", "admin", "analyst", "staff", "researcher"]
DOTENV_PATH = Path(__file__).resolve().parent.parent / '.env'

key_store: Dict[str, any] = { "ROLE_KEYS": {}, "TOKEN_SALT": None }

def load_keys_from_env():
    print("--- Loading encryption keys and salt from .env... ---")
    load_dotenv(dotenv_path=DOTENV_PATH)
    for role in ROLES:
        env_var_name = f"ENCRYPTION_KEY_{role.upper()}"
        key_b64 = os.getenv(env_var_name)
        if not key_b64:
            raise ValueError(f"FATAL: Encryption key '{env_var_name}' not found in .env file.")
        try:
            key_store["ROLE_KEYS"][role] = base64.urlsafe_b64decode(key_b64)
        except Exception as e:
            raise ValueError(f"FATAL: Invalid Base64 key for {env_var_name}. Error: {e}")
    token_salt = os.getenv("TOKENIZATION_SALT")
    if not token_salt:
        raise ValueError("FATAL: TOKENIZATION_SALT is not set in environment.")
    key_store["TOKEN_SALT"] = token_salt
    print("--- Key loading complete. ---")

def get_role_key(role: str) -> Optional[bytes]:
    return key_store["ROLE_KEYS"].get(role)

def get_token_salt() -> str:
    return key_store["TOKEN_SALT"]

def generate_new_key_string() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8')

def generate_new_salt_string() -> str:
    return os.urandom(16).hex()

def check_and_rotate_keys():
    now = datetime.now(timezone.utc)
    rotation_interval = timedelta(hours=24)
    
    last_rotation_str = get_key(DOTENV_PATH, "LAST_KEY_ROTATION_TIMESTAMP")
    
    if last_rotation_str:
        try:
            last_rotation_time = datetime.fromisoformat(last_rotation_str.strip('"'))
            if last_rotation_time.tzinfo is None:
                last_rotation_time = last_rotation_time.replace(tzinfo=timezone.utc)
            
            if now - last_rotation_time < rotation_interval:
                print(f"  - Next key rotation is scheduled after: {last_rotation_time + rotation_interval}")
                return
        except (ValueError, TypeError):
            print("  - WARNING: Could not parse LAST_KEY_ROTATION_TIMESTAMP. Forcing key rotation.")
    else:
        print("  - No previous rotation timestamp found. Forcing key rotation.")

    print(f"--- INITIATING KEY AND SALT ROTATION (Timestamp: {now.isoformat()}) ---")

    for role in ROLES:
        key_name = f"ENCRYPTION_KEY_{role.upper()}"
        new_key = generate_new_key_string()
        set_key(DOTENV_PATH, key_name, new_key)
        print(f"  - Rotated key for: {role}")

    set_key(DOTENV_PATH, "TOKENIZATION_SALT", generate_new_salt_string())
    print("  - Rotated TOKENIZATION_SALT.")
    
    set_key(DOTENV_PATH, "LAST_KEY_ROTATION_TIMESTAMP", now.isoformat())
    print("  - Updated LAST_KEY_ROTATION_TIMESTAMP in .env file.")

    try:
        load_keys_from_env()
        print("--- KEY & SALT ROTATION COMPLETE: New credentials are active. ---")
    except Exception as e:
        print(f"--- CRITICAL ERROR during key/salt reload after rotation: {e} ---")