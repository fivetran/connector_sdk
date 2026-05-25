"""Schema and fields management utilities."""

# For working with file paths in a cross-platform way
from pathlib import Path

# For type hints in function signatures
from typing import Set

# For reading and writing YAML files (fields.yaml schema documentation)
import yaml

# For logging connector operations and warnings
from fivetran_connector_sdk import Logging as log

FIELDS_FILE = Path("fields.yaml")
TABLES_KEY = "tables"


def _load_existing_tables() -> dict:
    """Load existing fields.yaml file if it exists.

    Returns:
        Dictionary with 'tables' key containing existing table definitions, or empty structure if file doesn't exist or is invalid.
    """
    if not FIELDS_FILE.exists():
        return {TABLES_KEY: {}}

    try:
        with FIELDS_FILE.open("r", encoding="utf-8") as yaml_file:
            data = yaml.safe_load(yaml_file) or {}
    except (IOError, yaml.YAMLError) as exc:
        log.warning(f"Warning: Could not read existing fields.yaml: {str(exc)}")
        return {TABLES_KEY: {}}

    tables = data.get(TABLES_KEY, {})
    if not isinstance(tables, dict):
        log.warning("Warning: Unexpected fields.yaml structure. Resetting tables section.")
        tables = {}
    return {TABLES_KEY: tables}


def _default_description(table_name: str) -> str:
    """Generate default table description.

    Args:
        table_name: Name of the table to generate description for.

    Returns:
        Default description string for the table."""
    return (
        f"Dynamically created table '{table_name}' from Bright Data scrape results. "
        "Fields are inferred from the API response structure."
    )


def update_fields_yaml(fields: Set[str], table_name: str) -> None:
    """
    Update fields.yaml with discovered fields from Bright Data scrape results.

    Documents all fields found in the API responses for reference.
    Merges with existing table entries to preserve other tables.

    Args:
        fields: Set of field names discovered from results
        table_name: Name of the table these fields belong to
    """
    sorted_fields = sorted(list(fields))

    fields_data = _load_existing_tables()
    tables = fields_data.setdefault(TABLES_KEY, {})
    table_entry = tables.setdefault(
        table_name,
        {
            "description": _default_description(table_name),
            "fields": [],
        },
    )

    table_entry["description"] = table_entry.get("description", _default_description(table_name))
    table_entry["fields"] = sorted_fields

    try:
        with FIELDS_FILE.open("w", encoding="utf-8") as yaml_file:
            yaml.safe_dump(
                fields_data,
                yaml_file,
                default_flow_style=False,
                sort_keys=True,
                allow_unicode=True,
            )
        log.info(f"Updated fields.yaml with {len(fields)} fields for table '{table_name}'")
    except (IOError, yaml.YAMLError) as exc:
        log.info(f"Warning: Could not update fields.yaml: {str(exc)}")
