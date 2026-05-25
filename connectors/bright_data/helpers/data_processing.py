"""Utilities for flattening Bright Data scrape results."""

# For serializing nested data structures (lists, dicts) to JSON strings
import json

# For type hints in function signatures
from typing import Any, Dict, List, Set


def flatten_dict(
    data: Any, parent_key: str = "", separator: str = "_", max_depth: int = 10
) -> Dict[str, Any]:
    """
    Flatten nested dictionaries and lists into a single level.

    Args:
        data: The data structure to flatten (dict, list, or primitive).
        parent_key: The parent key prefix for nested keys.
        separator: The separator to use between nested key levels.
        max_depth: Maximum nesting depth to flatten before serializing to JSON.

    Returns:
        A flattened dictionary with all nested keys combined using the separator.
    """
    if max_depth <= 0:
        return {parent_key: json.dumps(data) if data else None}

    items: List[tuple] = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_key = f"{parent_key}{separator}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(flatten_dict(value, new_key, separator, max_depth - 1).items())
            elif isinstance(value, list):
                items.append((new_key, json.dumps(value) if value else "[]"))
            else:
                items.append((new_key, value))
    elif isinstance(data, list):
        return {parent_key: json.dumps(data) if data else "[]"}
    else:
        return {parent_key: data}

    return dict(items)


def collect_all_fields(results: List[Dict[str, Any]]) -> Set[str]:
    """Return the union of keys that appear across processed results.

    Args:
        results: List of processed result dictionaries.

    Returns:
        Set of all unique field names found across all results."""
    all_fields: Set[str] = set()
    for result in results:
        all_fields.update(result.keys())
    return all_fields


def process_scrape_result(result: Any, url: str, result_index: int) -> Dict[str, Any]:
    """
    Flatten an individual scrape result and add metadata columns.

    Primary key fields (url, result_index) are always preserved and never overwritten
    by values from the flattened API response, even if the response contains fields
    with the same names.

    Args:
        result: The scrape result to process (dict or other type).
        url: The URL that was scraped.
        result_index: The index of this result for the given URL.

    Returns:
        A flattened dictionary with metadata fields and primary keys.
    """
    base_fields = {
        "url": url,
        "result_index": result_index,
        "position": result_index + 1,
    }

    if not isinstance(result, dict):
        base_fields["raw_data"] = str(result)
        return base_fields

    flattened = flatten_dict(result)

    # Remove any conflicting fields from flattened data that match primary key names
    # This ensures API response fields like "url" or "result_index" (if present as arrays)
    # don't overwrite our correct primary key values
    # Also check for nested variations (e.g., input.result_index, data.result_index)
    primary_key_fields = {"url", "result_index"}
    for pk_field in primary_key_fields:
        # Remove exact match
        flattened.pop(pk_field, None)
        # Remove any nested variations (e.g., input_result_index, data_result_index)
        keys_to_remove = [
            k
            for k in flattened.keys()
            if k.endswith(f"_{pk_field}") or k.startswith(f"{pk_field}_")
        ]
        for key in keys_to_remove:
            flattened.pop(key, None)

    # Add base_fields after removing conflicts to ensure correct primary keys
    # base_fields is added last to ensure our values (with correct types) always take precedence
    # Since API response doesn't include result_index, we can safely merge
    final_result = {**flattened, **base_fields}

    # Explicitly ensure result_index is always an integer
    # This is a safety check - result_index should already be an int from base_fields
    final_result["result_index"] = int(result_index)
    final_result["position"] = int(result_index + 1)

    return final_result
