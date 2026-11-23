"""Turns Omni API payloads into destination rows, used by connector.py.

Omni's API hands back a file path to raw YAML map for each model. View files declare the warehouse
table behind a view plus its dimensions and measures; topic files declare the join graph analysts
query through. Files that are neither (Omni's "model" and "relationships" specials) are ignored.
Document records from the documents endpoint are flattened into rows here as well.
"""

# For finding the "Reference this view as" comment at the top of a view file
import re

# For parsing document timestamps
from datetime import datetime

# For parsing the YAML documents Omni returns for each model
import yaml

# Omni writes the canonical reference name for a view as a leading comment, which accounts for
# schema prefixing and view renames.
__VIEW_REFERENCE_COMMENT = re.compile(r"#\s*Reference this view as\s+(\S+)")
__VIEW_REFERENCE_COMMENT_SCAN_LINES = 5
__YAML_SUFFIXES = (".yaml", ".yml")
__KIND_SUFFIXES = (".view", ".topic")
# Omni appends a kind before the suffix on some generated views, e.g. sales_teams.query.view.
__QUERY_INFIX = ".query"
__VIEWS_FOLDER = "views"


def parse_model(model_id: str, files: dict, view_names: dict):
    """
    Parse one model's YAML files into rows for the views, dimension, measure, topic and
    topic_join tables. A file that is empty or malformed is skipped rather than failing the sync.
    Args:
        model_id: the model the files belong to.
        files: file path to raw YAML, as returned by the model YAML endpoint.
        view_names: Omni's file path to view name mapping, as returned by the same endpoint.
    Returns:
        A dictionary of destination table name to the list of rows parsed for it.
    """
    rows = {"views": [], "dimension": [], "measure": [], "topic": [], "topic_join": []}
    for file_path, raw_yaml in files.items():
        if is_kind_file(file_path, ".view"):
            parse_view(model_id, file_path, raw_yaml, view_names, rows)
        elif is_kind_file(file_path, ".topic"):
            parse_topic(model_id, file_path, raw_yaml, rows)
    return rows


def is_kind_file(file_path: str, kind_suffix: str):
    """
    Check whether a file holds a view or a topic. The API names files with a bare suffix,
    optionally under folders, e.g. "AI Cost/spend.view"; the suffix followed by .yaml is also
    accepted because Omni's Git integration writes that layout.
    Args:
        file_path: the file path from the model YAML response.
        kind_suffix: ".view" or ".topic".
    Returns:
        True when the file is of that kind.
    """
    normalized = file_path.replace("\\", "/")
    return normalized.endswith(kind_suffix) or (kind_suffix + ".") in normalized


def parse_view(model_id: str, file_path: str, raw_yaml: str, view_names: dict, rows: dict):
    """
    Add the view row and its dimension and measure rows for one view file.
    Args:
        model_id: the model the file belongs to.
        file_path: the view file path.
        raw_yaml: the view file content.
        view_names: Omni's file path to view name mapping.
        rows: the table name to rows dictionary being built.
    """
    document = load_yaml(raw_yaml)
    if document is None:
        return
    view_name = resolve_view_name(file_path, raw_yaml, view_names)
    rows["views"].append(
        {
            "model_id": model_id,
            "view_name": view_name,
            "schema_name": text(document.get("schema")),
            "table_name": text(document.get("table_name")),
            "label": text(document.get("label")),
            "description": text(document.get("description")),
            "file_path": file_path,
        }
    )
    for field_name, raw_field in as_map(document.get("dimensions")).items():
        field = as_map(raw_field)
        rows["dimension"].append(
            {
                "model_id": model_id,
                "view_name": view_name,
                "field_name": field_name,
                "label": text(field.get("label")),
                "sql": text(field.get("sql")),
                "format": text(field.get("format")),
                "description": text(field.get("description")),
                "is_primary_key": field.get("primary_key") is True,
            }
        )
    for measure_name, raw_measure in as_map(document.get("measures")).items():
        measure = as_map(raw_measure)
        rows["measure"].append(
            {
                "model_id": model_id,
                "view_name": view_name,
                "measure_name": measure_name,
                "label": text(measure.get("label")),
                "aggregate_type": text(measure.get("aggregate_type")),
                "sql": text(measure.get("sql")),
                "description": text(measure.get("description")),
            }
        )


def parse_topic(model_id: str, file_path: str, raw_yaml: str, rows: dict):
    """
    Add the topic row and its flattened join edges for one topic file.
    Args:
        model_id: the model the file belongs to.
        file_path: the topic file path.
        raw_yaml: the topic file content.
        rows: the table name to rows dictionary being built.
    """
    document = load_yaml(raw_yaml)
    if document is None:
        return
    topic_name = strip_suffixes(file_name(file_path))
    base_view = text(document.get("base_view"))
    rows["topic"].append(
        {
            "model_id": model_id,
            "topic_name": topic_name,
            "base_view": base_view,
            "label": text(document.get("label")),
            "group_label": text(document.get("group_label")),
            "description": text(document.get("description")),
            "ai_context": text(document.get("ai_context")),
            "file_path": file_path,
        }
    )
    joins = as_map(document.get("joins"))
    if joins and base_view is not None:
        collect_joins(model_id, topic_name, base_view, joins, set(), rows["topic_join"])


def collect_joins(model_id, topic_name, from_view, joins, visited_edges, join_rows):
    """
    Walk a topic's nested join tree depth-first, adding one row per distinct edge. The visited
    edge set both removes repeated edges and stops cycles from recursing forever.
    Args:
        model_id: the model the topic belongs to.
        topic_name: the topic being flattened.
        from_view: the view the joins in this subtree start from.
        joins: the nested joins mapping under from_view.
        visited_edges: (from_view, to_view) pairs already added for this topic.
        join_rows: the topic_join rows being built.
    """
    for to_view, children in joins.items():
        edge = (from_view, to_view)
        if edge in visited_edges:
            continue
        visited_edges.add(edge)
        join_rows.append(
            {
                "model_id": model_id,
                "topic_name": topic_name,
                "from_view": from_view,
                "to_view": to_view,
            }
        )
        nested = as_map(children)
        if nested:
            collect_joins(model_id, topic_name, to_view, nested, visited_edges, join_rows)


def resolve_view_name(file_path: str, raw_yaml: str, view_names: dict):
    """
    Resolve the name a view is referenced by. Omni's own mapping wins because it already accounts
    for folder prefixes and suffixes the path only hints at: "EXPORTS/cm_metrics.view" maps to
    exports__cm_metrics and "sales_teams.query.view" to sales_teams. The reference comment and the
    path are fallbacks for the Git integration layout, which ships no mapping.
    Args:
        file_path: the view file path.
        raw_yaml: the view file content.
        view_names: Omni's file path to view name mapping.
    Returns:
        The view name.
    """
    mapped = text(view_names.get(file_path))
    if mapped is not None:
        return mapped
    for line in raw_yaml.splitlines()[:__VIEW_REFERENCE_COMMENT_SCAN_LINES]:
        match = __VIEW_REFERENCE_COMMENT.search(line)
        if match:
            return match.group(1)
    # Fall back to the path, qualifying with the parent folder the way Omni itself qualifies
    # foldered views, so views of the same name in different folders stay distinct.
    normalized = file_path.replace("\\", "/")
    name = strip_suffixes(file_name(normalized))
    parent, separator, _ = normalized.rpartition("/")
    if separator and parent:
        parent_name = normalize_name_segment(parent.rpartition("/")[2])
        if parent_name and parent_name != __VIEWS_FOLDER:
            return f"{parent_name}__{name}"
    return name


def normalize_name_segment(segment: str):
    """
    Lower-case a path segment and replace anything that is not a letter or digit with an
    underscore.
    Args:
        segment: one folder name.
    Returns:
        The normalized name.
    """
    return "".join(character if character.isalnum() else "_" for character in segment.lower())


def file_name(file_path: str):
    """
    Return the last segment of a file path.
    Args:
        file_path: the file path, with either slash style.
    Returns:
        The file name.
    """
    return file_path.replace("\\", "/").rpartition("/")[2]


def strip_suffixes(name: str):
    """
    Remove the YAML, kind and query suffixes from a file name, e.g. "orders.view.yaml" to "orders".
    Args:
        name: the file name.
    Returns:
        The bare view or topic name.
    """
    for suffixes in (__YAML_SUFFIXES, __KIND_SUFFIXES, (__QUERY_INFIX,)):
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
    return name


def load_yaml(raw_yaml: str):
    """
    Parse a YAML document with the safe loader, which builds only plain scalars, lists and maps.
    A document carrying a language-specific class tag therefore counts as malformed.
    Args:
        raw_yaml: the file content.
    Returns:
        The document as a dictionary, or None when the file is empty, malformed or not a mapping.
    """
    try:
        loaded = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return None
    return as_map(loaded) if isinstance(loaded, dict) else None


def as_map(value):
    """
    Return a YAML mapping with string keys, dropping entries whose key or value is null.
    Args:
        value: a parsed YAML value.
    Returns:
        The mapping, or an empty dictionary when value is not a mapping.
    """
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if key is not None and item is not None}


def text(value):
    """
    Render a parsed YAML or JSON scalar as stripped text, treating missing and blank values as None.
    Booleans render as true or false, the way they are written in YAML.
    Args:
        value: the scalar.
    Returns:
        The text, or None.
    """
    if value is None:
        return None
    rendered = str(value).lower() if isinstance(value, bool) else str(value)
    return rendered.strip() or None


def document_row(record: dict):
    """
    Map one record of the documents endpoint to a document row, flattening the nested owner and
    folder objects. visits and last_viewed_at are the usage signals; folder_path places the
    document in the organisation's hierarchy.
    Args:
        record: a raw document record.
    Returns:
        The row, or None when the record has no identifier to key on.
    """
    document_id = json_text(record, "identifier")
    if document_id is None:
        return None
    owner = record.get("owner")
    folder = record.get("folder")
    return {
        "id": document_id,
        "name": json_text(record, "name"),
        "description": json_text(record, "description"),
        "url": json_text(record, "url"),
        "scope": json_text(record, "scope"),
        "connection_id": json_text(record, "connectionId"),
        "owner_id": json_text(owner, "id"),
        "owner_name": json_text(owner, "name"),
        "folder_id": json_text(folder, "id"),
        "folder_name": json_text(folder, "name"),
        "folder_path": json_text(folder, "path"),
        "has_dashboard": json_bool(record, "hasDashboard"),
        "has_app": json_bool(record, "hasApp"),
        "visits": json_integer(record, "visits"),
        "last_viewed_at": json_timestamp(record, "lastViewedAt"),
        "updated_at": json_timestamp(record, "updatedAt"),
        # Omni's own deleted flag, distinct from Fivetran's soft-delete bookkeeping.
        "is_deleted": json_bool(record, "deleted"),
    }


def json_text(node, field: str):
    """
    Return a stripped string field of a JSON object, treating non-string and blank values as None.
    Args:
        node: a JSON object, or None.
        field: the field name.
    Returns:
        The stripped string, or None.
    """
    value = node.get(field) if isinstance(node, dict) else None
    if not isinstance(value, str):
        return None
    return value.strip() or None


def json_bool(node: dict, field: str):
    """
    Return a JSON field as a boolean, treating a missing or unrecognised value as False.
    Args:
        node: a JSON object.
        field: the field name.
    Returns:
        The boolean.
    """
    value = node.get(field)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def json_integer(node: dict, field: str):
    """
    Return a numeric JSON field as an integer.
    Args:
        node: a JSON object.
        field: the field name.
    Returns:
        The integer, or None when the value is missing or not a number.
    """
    value = node.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def json_timestamp(node: dict, field: str):
    """
    Return an ISO 8601 timestamp field unchanged when it parses and carries a UTC offset. A
    timestamp Omni formats unexpectedly becomes None rather than dropping the whole document.
    Args:
        node: a JSON object.
        field: the field name.
    Returns:
        The timestamp string, or None.
    """
    value = json_text(node, field)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None
