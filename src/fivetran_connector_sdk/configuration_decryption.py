import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from fivetran_connector_sdk.constants import ROOT_LOCATION, CONFIG_ENCRYPTION_KEY_FILE, ENCRYPTED_VALUE_PREFIX, UTF_8

NONCE_LENGTH_BYTES = 12
KEY_SIZE_BYTES = 32  # AES-256


def _key_file_path() -> str:
    return os.path.join(os.path.expanduser("~"), ROOT_LOCATION, CONFIG_ENCRYPTION_KEY_FILE)


def _load_key() -> bytes:
    """Loads the persisted encryption key, raising a clear error if it does not exist.

    Mirrors ConfigurationEncryption.loadExistingKey() in the Java tester: this is a read-only
    path used when decrypting configuration.json, and never creates a key.
    """
    key_path = _key_file_path()
    if not os.path.exists(key_path):
        raise ValueError(
            f"configuration.json contains encrypted values but the encryption key was not found at "
            f"{key_path}; re-run 'fivetran configuration' to regenerate configuration.json"
        )

    try:
        with open(key_path, "r", encoding=UTF_8) as f:
            key = base64.b64decode(f.read().strip())
    except (OSError, ValueError) as e:
        raise ValueError(
            f"failed to read the encryption key at {key_path}; re-run 'fivetran configuration' to "
            f"regenerate configuration.json"
        ) from e

    if len(key) != KEY_SIZE_BYTES:
        raise ValueError(
            f"invalid key length: expected {KEY_SIZE_BYTES} bytes, got {len(key)}"
        )
    return key


def _decrypt_value(value: str | None, field_name: str, key: bytes) -> str | None:
    """Decrypts value if it carries ENCRYPTED_VALUE_PREFIX; otherwise returns it unchanged."""
    if value is None or not value.startswith(ENCRYPTED_VALUE_PREFIX):
        return value

    try:
        combined = base64.b64decode(value[len(ENCRYPTED_VALUE_PREFIX):])
        if len(combined) < NONCE_LENGTH_BYTES:
            raise ValueError("ciphertext shorter than nonce length")
        nonce, ciphertext = combined[:NONCE_LENGTH_BYTES], combined[NONCE_LENGTH_BYTES:]
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, field_name.encode(UTF_8))
        return plaintext.decode(UTF_8)
    except (ValueError, InvalidTag) as e:
        raise ValueError(
            f"failed to decrypt configuration field '{field_name}'; the value contains the "
            f"'{ENCRYPTED_VALUE_PREFIX}' prefix, so Fivetran attempted to decrypt it, but the encryption key "
            f"is missing or invalid, or the encrypted value is corrupted. Re-run "
            f"'fivetran configuration' to regenerate configuration.json."
        ) from e


def decrypt_configuration_values(configuration: dict) -> dict:
    """Decrypts every password field in configuration that carries ENCRYPTED_VALUE_PREFIX.

    Mirrors ConfigurationEncryption.decryptConfigurationValues() in the Java tester: the key is
    loaded lazily, only if at least one value in configuration is encrypted.
    """
    if not any(isinstance(value, str) and value.startswith(ENCRYPTED_VALUE_PREFIX)
               for value in configuration.values()):
        return configuration

    key = _load_key()
    return {field_name: _decrypt_value(value, field_name, key) for field_name, value in configuration.items()}
