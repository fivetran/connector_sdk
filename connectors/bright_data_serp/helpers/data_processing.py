"""Utility helpers for transforming Bright Data SERP responses."""

from typing import Any, Dict, Iterable, Set

from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op


def flatten_dict(data: dict, parent_key: str = "", sep: str = "_") -> dict:
    """
    Flatten a nested dictionary into a single depth dictionary.

    Nested keys are concatenated using the provided separator.
    """
    items: dict = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.update(flatten_dict(value, new_key, sep=sep))
        else:
            items[new_key] = value
    return items


def collect_all_fields(results: Iterable[dict]) -> set:
    """Collect the union of keys across all result dictionaries."""
    fields: set = set()
    for result in results:
        fields.update(result.keys())
    return fields


def process_search_result(result: Any, query: str, result_index: int) -> dict:
    """
    Transform a raw search result into a flattened dictionary suitable for upsert.

    Primary key fields (query, result_index) are always preserved and never overwritten
    by values from the flattened API response.
    """
    base_fields: dict = {
        "query": query,
        "result_index": result_index,
        "position": result_index + 1,
    }

    if not isinstance(result, dict):
        base_fields["raw_response"] = str(result)
        return base_fields

    flattened = flatten_dict(result)

    for pk_field in ("query", "result_index"):
        flattened.pop(pk_field, None)

    final_result = {**flattened, **base_fields}
    final_result["result_index"] = int(result_index)
    final_result["position"] = int(result_index + 1)

    return final_result


def process_and_upsert_results(processed_results: list, all_fields: set, table_name: str) -> None:
    """Validate primary keys and upsert processed search result records."""
    primary_keys = {"query": str, "result_index": int}
    primary_key_errors = []

    for result in processed_results:
        for pk, pk_type in primary_keys.items():
            if pk not in result:
                primary_key_errors.append(f"Primary key '{pk}' missing from result")
                result[pk] = pk_type() if pk_type == str else 0
            elif not isinstance(result[pk], pk_type):
                try:
                    if pk_type == str:
                        result[pk] = str(result[pk])
                    elif pk_type == int:
                        current_value = result[pk]
                        if isinstance(current_value, str):
                            cleaned = current_value.strip().strip("[]\"'")
                            result[pk] = int(cleaned) if cleaned.isdigit() else 0
                        else:
                            result[pk] = int(current_value)
                except (ValueError, TypeError):
                    primary_key_errors.append(
                        f"Could not convert primary key '{pk}' to {pk_type.__name__}"
                    )
                    result[pk] = pk_type() if pk_type == str else 0

        row = {field: result.get(field) for field in all_fields}
        op.upsert(table=table_name, data=row)

    if primary_key_errors:
        unique_errors = list(set(primary_key_errors))
        log.warning(
            f"Primary key validation issues: {', '.join(unique_errors[:3])}"
            f"{' (and more)' if len(unique_errors) > 3 else ''}"
        )
