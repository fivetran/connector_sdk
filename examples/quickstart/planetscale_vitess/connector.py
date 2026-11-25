"""This connector syncs the tables of a PlanetScale (Vitess) database through PlanetScale's VStream gRPC API: an
initial copy of each table followed by incremental row changes, with deletes.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For encoding cursors into the state
import base64

# For checking that the host serves HTTPS in the connection test
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining the fields of the setup form
from fivetran_connector_sdk import form_field

# For returning success or failure from the setup form's connection test
from fivetran_connector_sdk import Test

# For catching MySQL connection failures in the connection test
import pymysql

# For discovering keyspaces, tables, columns and shards
import planetscale_metadata

# For mapping column types to Fivetran types
import value_converter

# For reading row changes from VStream
import vstream_reader

# For the tablet type numbers and the TableCursor message
from vitess_messages import TABLET_TYPE, TableCursor

__REQUIRED_CONFIGURATION_KEYS = ["username", "password", "database", "host"]
__TRUE_VALUES = {"1", "t", "T", "TRUE", "true", "True"}
__FALSE_VALUES = {"0", "f", "F", "FALSE", "false", "False"}
__HTTPS_TIMEOUT_SECONDS = 2
__PING_TIMEOUT_SECONDS = 5
__HTTPS_FAILURE_MESSAGE = (
    'Unable to initialize Connect Session: The database "{database}", hosted at "{host}", is'
    " inaccessible from this process"
)

# Schema discovery is reused between schema() and update() within one process, the way the Java connector keeps
# it in its service session.
__SOURCE_SCHEMA_CACHE = {}


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and the connection test.
    """
    config_form = ConfigurationForm()
    text_fields = [
        ("host", "Database host name", "Hostname to connect to your PlanetScale database", True),
        ("database", "Database name", "Name of your PlanetScale database", True),
        (
            "username",
            "Database username",
            "Username to connect to your PlanetScale database",
            True,
        ),
    ]
    for name, label, description, required in text_fields:
        config_form.add_field(
            form_field.TextField(
                name=name,
                label=label,
                description=description,
                required=required,
                field_type=form_field.TextField.plain_text,
            )
        )
    config_form.add_field(
        form_field.TextField(
            name="password",
            label="Database password",
            description="Password to connect to your PlanetScale database",
            required=True,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="shards",
            label="Comma-separated list of shards to sync",
            description="Leave empty to sync every shard of the database.",
            required=False,
            field_type=form_field.TextField.plain_text,
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="use_replica",
            label="Use Replica?",
            description="Only set to true if your PlanetScale branch has a replica. PlanetScale"
            " Development branches do not have replicas.",
            fields=[form_field.DropdownFieldParam(value=value) for value in ("true", "false")],
        )
    )
    config_form.add_field(
        form_field.DropdownField(
            name="treat_tiny_int_as_boolean",
            label="Treat tinyint(1) as boolean",
            description="Enable this setting to serialize tinyint(1) as boolean values",
            fields=[form_field.DropdownFieldParam(value=value) for value in ("true", "false")],
        )
    )
    config_form.add_test(label="Check connection", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """
    Check the configuration, then that the host serves HTTPS, then that the credentials open a connection to the
    database primary.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
    except ValueError as error:
        return test.failure(f"request did not contain a valid configuration: {error}")
    try:
        # Any HTTP status counts as reachable; only a failure to connect fails this step.
        requests.get(
            "https://" + configuration["host"], timeout=__HTTPS_TIMEOUT_SECONDS, stream=True
        ).close()
    except (requests.RequestException, ValueError):
        return test.failure(
            __HTTPS_FAILURE_MESSAGE.format(
                database=configuration["database"], host=configuration["host"]
            )
        )
    try:
        planetscale_metadata.ping(configuration, __PING_TIMEOUT_SECONDS)
    except (pymysql.MySQLError, OSError) as error:
        return test.failure(str(error))
    return test.success()


def parse_boolean(name: str, value):
    """
    Parse a boolean setting the way the Go connector does; a missing value is false.
    Args:
        name: the configuration key, for the error message.
        value: the configured value.
    Returns:
        The boolean.
    Raises:
        ValueError: if the value is not a recognised boolean spelling.
    """
    if value is None:
        return False
    if value in __TRUE_VALUES:
        return True
    if value in __FALSE_VALUES:
        return False
    raise ValueError(f"{name} is not a boolean")


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or a boolean setting is invalid.
    """
    for key in __REQUIRED_CONFIGURATION_KEYS:
        if configuration.get(key) is None:
            name = "hostname" if key == "host" else key
            raise ValueError(f"{name} not found in configuration")
    parse_boolean("treat_tiny_int_as_boolean", configuration.get("treat_tiny_int_as_boolean"))
    parse_boolean("use_replica", configuration.get("use_replica"))


def source_schema(configuration: dict):
    """
    Return the discovered keyspaces, tables, columns and shards, discovering them once per process.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        The source schema from planetscale_metadata.fetch_source_schema.
    """
    key = (configuration["host"], configuration["database"], configuration["username"])
    if key not in __SOURCE_SCHEMA_CACHE:
        __SOURCE_SCHEMA_CACHE[key] = planetscale_metadata.fetch_source_schema(configuration)
    return __SOURCE_SCHEMA_CACHE[key]


def table_definition(columns: list, treat_tiny_int_as_boolean: bool):
    """
    Build the column types and primary key of a table from its discovered columns.
    Args:
        columns: (column name, column type, is primary key) tuples.
        treat_tiny_int_as_boolean: whether tinyint(1) is written as BOOLEAN.
    Returns:
        A tuple of (column name to schema() column type, column name to Fivetran type, primary key columns).
    """
    schema_columns, data_types, primary_key = {}, {}, []
    for name, column_type, is_primary_key in columns:
        data_type, precision, scale = value_converter.map_column_type(
            column_type, treat_tiny_int_as_boolean
        )
        data_types[name] = data_type
        if data_type == value_converter.DECIMAL:
            schema_columns[name] = {"type": data_type, "precision": precision, "scale": scale}
        else:
            schema_columns[name] = data_type
        if is_primary_key:
            primary_key.append(name)
    return schema_columns, data_types, primary_key


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    validate_configuration(configuration=configuration)
    treat_tiny_int_as_boolean = parse_boolean(
        "treat_tiny_int_as_boolean", configuration.get("treat_tiny_int_as_boolean")
    )
    tables = []
    for keyspace, keyspace_tables in source_schema(configuration)["keyspaces"].items():
        for table_name, columns in keyspace_tables.items():
            schema_columns, _, primary_key = table_definition(columns, treat_tiny_int_as_boolean)
            # Each keyspace is its own schema. A table without a primary key gets none here, so Fivetran adds
            # _fivetran_id as the key, as the Java connector does.
            table = {"schema": keyspace, "table": table_name, "columns": schema_columns}
            if primary_key:
                table["primary_key"] = primary_key
            tables.append(table)
    return tables


def shards_to_sync(configuration: dict, discovered_shards: list):
    """
    Return the configured shards, or every discovered shard when none are configured.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        discovered_shards: the shards found by schema discovery.
    Returns:
        The shard names.
    """
    configured = [shard.strip() for shard in (configuration.get("shards") or "").split(",")]
    configured = [shard for shard in configured if shard]
    return configured or discovered_shards


def shard_state(state: dict, keyspace: str, table_name: str, shard: str):
    """
    Return the state entry of a table shard, creating it. The layout matches PlanetScale's Fivetran connector:
    keyspaces > streams ("<keyspace>:<table>") > shards > {"cursor": base64 TableCursor, error fields}.
    Args:
        state: the connector state.
        keyspace: the keyspace.
        table_name: the table.
        shard: the shard.
    Returns:
        The shard's state dictionary.
    """
    streams = state.setdefault("keyspaces", {}).setdefault(keyspace, {}).setdefault("streams", {})
    shards = streams.setdefault(f"{keyspace}:{table_name}", {}).setdefault("shards", {})
    return shards.setdefault(shard, {})


def load_cursor(entry: dict, keyspace: str, shard: str):
    """
    Decode a shard's saved cursor, or start a new one, which makes VStream begin with an initial copy.
    Args:
        entry: the shard's state dictionary.
        keyspace: the keyspace.
        shard: the shard.
    Returns:
        The TableCursor.
    """
    if "cursor" in entry:
        return TableCursor.FromString(base64.b64decode(entry["cursor"], validate=True))
    return TableCursor(keyspace=keyspace, shard=shard)


def save_cursor(entry: dict, cursor):
    """
    Store a cursor in a shard's state dictionary as padded standard Base64.
    Args:
        entry: the shard's state dictionary.
        cursor: the TableCursor.
    """
    entry["cursor"] = base64.b64encode(cursor.SerializeToString()).decode("ascii")


def row_handler(keyspace: str, table_name: str, primary_key: list):
    """
    Build the callback that writes VStream row changes to the destination.
    Args:
        keyspace: the keyspace, used as the destination schema.
        table_name: the table.
        primary_key: the primary key columns; empty for a table without one.
    Returns:
        A function taking (operation, before, after).
    """

    def keys_of(row: dict):
        return {column: row[column] for column in primary_key} if primary_key else dict(row)

    def on_row(operation: str, before: dict, after: dict):
        if operation == vstream_reader.DELETE:
            # The 'delete' operation is used to mark a row as deleted in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the primary key of the row to delete.
            op.delete(table=table_name, keys=keys_of(before), schema=keyspace)
            return
        if operation == vstream_reader.UPDATE and keys_of(before) != keys_of(after):
            # An update that changes the primary key replaces the row, so the old key is deleted first.
            op.delete(table=table_name, keys=keys_of(before), schema=keyspace)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=table_name, data=after, schema=keyspace)

    return on_row


def cursor_saver(state: dict, entry: dict):
    """
    Build the callback that saves a shard's cursor progress.
    Args:
        state: the connector state.
        entry: the shard's state dictionary.
    Returns:
        A function taking a TableCursor.
    """

    def on_cursor(cursor):
        save_cursor(entry, cursor)

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state)

    return on_cursor


def listener():
    """
    Build the listener a table read reports to: log lines, and a dashboard warning when a table keeps timing out.
    Returns:
        The vstream_reader.Listener.
    """
    return vstream_reader.Listener(
        info=log.info,
        warning=log.warning,
        warning_alert=op.warning,
        record_binlog_expiration=lambda keyspace, table, shard: log.warning(
            f"Binlogs expired for {keyspace}.{table} shard {shard}; starting a new initial copy"
        ),
    )


def sync_table_shard(configuration, state, keyspace, table_name, shard, columns):
    """
    Read one table shard until it has caught up, writing its changes and saving its cursor.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state.
        keyspace: the keyspace.
        table_name: the table.
        shard: the shard.
        columns: the table's discovered columns.
    Raises:
        RuntimeError: if the read fails; the latest cursor and the error are saved to the state first.
    """
    treat_tiny_int_as_boolean = parse_boolean(
        "treat_tiny_int_as_boolean", configuration.get("treat_tiny_int_as_boolean")
    )
    use_replica = parse_boolean("use_replica", configuration.get("use_replica"))
    _, data_types, primary_key = table_definition(columns, treat_tiny_int_as_boolean)
    entry = shard_state(state, keyspace, table_name, shard)
    log.info(f"Syncing {keyspace}.{table_name} shard {shard}")
    result = vstream_reader.read_table(
        client_factory=lambda: vstream_reader.open_client(
            configuration["host"], configuration["username"], configuration["password"]
        ),
        keyspace=keyspace,
        shard=shard,
        table_name=table_name,
        start_cursor=load_cursor(entry, keyspace, shard),
        tablet_type=TABLET_TYPE["REPLICA" if use_replica else "PRIMARY"],
        column_types=data_types,
        on_row=row_handler(keyspace, table_name, primary_key),
        on_cursor=cursor_saver(state, entry),
        listener=listener(),
    )
    if result.cursor is not None:
        save_cursor(entry, result.cursor)
    entry.pop("error_message", None)
    entry.pop("error_code", None)
    if result.binlog_expiration_error is not None:
        entry["error_message"] = result.binlog_expiration_error
    if result.error is not None:
        entry["error_message"] = str(result.error)
        entry["error_code"] = getattr(result.error, "code", None) or getattr(
            result.error.__cause__, "code", "UNKNOWN"
        )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)
    if result.error is not None:
        raise RuntimeError(
            f"Failed to sync {keyspace}.{table_name} shard {shard}: {result.error}"
        ) from result.error


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: QuickStart Examples - PlanetScale Vitess")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    discovered = source_schema(configuration)
    shards = shards_to_sync(configuration, discovered["shards"])
    for keyspace, keyspace_tables in discovered["keyspaces"].items():
        for table_name, columns in keyspace_tables.items():
            for shard in shards:
                sync_table_shard(configuration, state, keyspace, table_name, shard, columns)
    log.info("PlanetScale sync completed")


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema, configuration_form=configuration_form)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
