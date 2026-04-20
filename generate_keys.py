import os
import base64


def generate_key() -> str:

    key_bytes = os.urandom(32)
    return base64.urlsafe_b64encode(key_bytes).decode('utf-8')

if __name__ == "__main__":
    roles = ["doctor", "admin", "analyst", "staff", "researcher"]
    
    print("Please copy the following lines into your .env file:\n")
    
    for role in roles:
        key = generate_key()
        print(f"ENCRYPTION_KEY_{role.upper()}={key}")