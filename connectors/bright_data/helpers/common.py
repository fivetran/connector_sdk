"""Shared constants and utilities for Bright Data helpers."""

# For type hints in function signatures
from typing import Any

# For type hints when working with HTTP responses
from requests import Response


BRIGHT_DATA_BASE_URL = "https://api.brightdata.com"
DEFAULT_TIMEOUT_SECONDS = 120
RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def parse_response_payload(response: Response) -> Any:
    """Return JSON payload when available, otherwise raw text."""
    try:
        return response.json()
    except ValueError:
        return response.text


def extract_error_detail(response: Response) -> str:
    """Extract error detail from a failed Bright Data response."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            # Check for validation_errors array (400 Bad Request)
            if "validation_errors" in payload and isinstance(payload["validation_errors"], list):
                errors = ", ".join(str(err) for err in payload["validation_errors"])
                return f"Validation errors: {errors}"
        return str(payload)
    except ValueError:
        return response.text
