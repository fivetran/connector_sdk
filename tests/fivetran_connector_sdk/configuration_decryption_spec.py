import base64
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
sys.modules.pop("fivetran_connector_sdk.configuration_decryption", None)
sys.modules.pop("fivetran_connector_sdk", None)

from fivetran_connector_sdk.configuration_decryption import (
    decrypt_configuration_values,
    _decrypt_value,
    _load_key,
)
from fivetran_connector_sdk.constants import ENCRYPTED_VALUE_PREFIX, UTF_8

NONCE_LENGTH_BYTES = 12


def _generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def _write_key_file(directory: str, key: bytes) -> str:
    key_path = os.path.join(directory, "config_encryption_key")
    with open(key_path, "w", encoding=UTF_8) as f:
        f.write(base64.b64encode(key).decode(UTF_8))
    return key_path


def _encrypt(key: bytes, field_name: str, plaintext: str) -> str:
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(UTF_8), field_name.encode(UTF_8))
    return ENCRYPTED_VALUE_PREFIX + base64.b64encode(nonce + ciphertext).decode(UTF_8)


class TestConfigEncryption(unittest.TestCase):

    def test_decrypt_configuration_values_returns_unchanged_when_no_encrypted_values(self):
        configuration = {"host": "db.example.com", "port": "5432"}

        with patch("fivetran_connector_sdk.configuration_decryption._load_key") as mock_load_key:
            result = decrypt_configuration_values(configuration)

        self.assertEqual(result, configuration)
        mock_load_key.assert_not_called()

    def test_decrypt_configuration_values_raises_when_key_file_missing(self):
        configuration = {"password": f"{ENCRYPTED_VALUE_PREFIX}anything"}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "fivetran_connector_sdk.configuration_decryption._key_file_path",
                return_value=os.path.join(tmpdir, "config_encryption_key"),
            ):
                with self.assertRaises(ValueError) as context:
                    decrypt_configuration_values(configuration)

        self.assertIn("configuration.json contains encrypted values", str(context.exception))

    def test_decrypt_configuration_values_decrypts_only_encrypted_fields(self):
        key = _generate_key()

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = _write_key_file(tmpdir, key)
            configuration = {
                "host": "db.example.com",
                "password": _encrypt(key, "password", "s3cr3t"),
            }

            with patch(
                "fivetran_connector_sdk.configuration_decryption._key_file_path",
                return_value=key_path,
            ):
                result = decrypt_configuration_values(configuration)

        self.assertEqual(result["host"], "db.example.com")
        self.assertEqual(result["password"], "s3cr3t")

    def test_load_key_raises_when_key_file_corrupted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "config_encryption_key")
            with open(key_path, "w", encoding=UTF_8) as f:
                f.write("not-valid-base64!!")

            with patch(
                "fivetran_connector_sdk.configuration_decryption._key_file_path",
                return_value=key_path,
            ):
                with self.assertRaises(ValueError) as context:
                    _load_key()

        self.assertIn("failed to read the encryption key", str(context.exception))

    def test_load_key_raises_when_key_has_invalid_length(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "config_encryption_key")
            # Write a key that's too short (16 bytes instead of 32)
            invalid_key = os.urandom(16)
            with open(key_path, "w", encoding=UTF_8) as f:
                f.write(base64.b64encode(invalid_key).decode(UTF_8))

            with patch(
                "fivetran_connector_sdk.configuration_decryption._key_file_path",
                return_value=key_path,
            ):
                with self.assertRaises(ValueError) as context:
                    _load_key()

        self.assertIn("invalid key length", str(context.exception))
        self.assertIn("expected 32 bytes", str(context.exception))

    def test_decrypt_value_returns_value_unchanged_when_no_prefix(self):
        key = _generate_key()

        result = _decrypt_value("plaintext-value", "password", key)

        self.assertEqual(result, "plaintext-value")

    def test_decrypt_value_returns_none_when_value_is_none(self):
        key = _generate_key()

        result = _decrypt_value(None, "password", key)

        self.assertIsNone(result)

    def test_decrypt_value_round_trips_with_matching_field_name(self):
        key = _generate_key()
        encrypted = _encrypt(key, "password", "s3cr3t")

        result = _decrypt_value(encrypted, "password", key)

        self.assertEqual(result, "s3cr3t")

    def test_decrypt_value_raises_when_field_name_does_not_match(self):
        key = _generate_key()
        encrypted = _encrypt(key, "password", "s3cr3t")

        with self.assertRaises(ValueError) as context:
            _decrypt_value(encrypted, "other_field", key)

        self.assertIn(
            "failed to decrypt configuration field 'other_field'", str(context.exception)
        )

    def test_decrypt_value_raises_when_ciphertext_corrupted(self):
        key = _generate_key()
        encrypted = _encrypt(key, "password", "s3cr3t")
        # Flip one data character well before any base64 padding, so the payload stays parseable
        # but its decoded bytes differ, causing GCM tag verification to fail. Appending garbage
        # after the padding would not work here: base64.b64decode() stops at the padding and
        # silently ignores anything after it, so the ciphertext would decode unchanged.
        body = encrypted[len(ENCRYPTED_VALUE_PREFIX) :]
        index = len(body) - 6
        flipped_char = "A" if body[index] != "A" else "B"
        corrupted = ENCRYPTED_VALUE_PREFIX + body[:index] + flipped_char + body[index + 1 :]

        with self.assertRaises(ValueError) as context:
            _decrypt_value(corrupted, "password", key)

        self.assertIn("failed to decrypt configuration field 'password'", str(context.exception))

    def test_decrypt_value_raises_when_key_does_not_match(self):
        key = _generate_key()
        other_key = _generate_key()
        encrypted = _encrypt(key, "password", "s3cr3t")

        with self.assertRaises(ValueError) as context:
            _decrypt_value(encrypted, "password", other_key)

        self.assertIn("failed to decrypt configuration field 'password'", str(context.exception))

    def test_decrypt_value_raises_when_ciphertext_shorter_than_nonce_length(self):
        key = _generate_key()
        truncated_ciphertext = ENCRYPTED_VALUE_PREFIX + base64.b64encode(b"too_short").decode(
            UTF_8
        )

        with self.assertRaises(ValueError) as context:
            _decrypt_value(truncated_ciphertext, "password", key)

        self.assertIn("failed to decrypt configuration field 'password'", str(context.exception))


if __name__ == "__main__":
    unittest.main()
