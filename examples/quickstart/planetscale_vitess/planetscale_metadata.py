"""Discovers keyspaces, tables, columns and shards through PlanetScale's MySQL endpoint, used by connector.py."""

# For verifying the TLS certificate and host name of the MySQL endpoint
import ssl

# For connecting to PlanetScale over the MySQL protocol
import pymysql

__CONNECT_TIMEOUT_SECONDS = 5
__METADATA_READ_TIMEOUT_SECONDS = 120
__COLUMN_QUERY = (
    "select column_name, column_type, column_key from information_schema.columns"
    " where table_name=%s AND table_schema=%s order by ordinal_position"
)


def connect(configuration: dict, timeout_seconds: int = __METADATA_READ_TIMEOUT_SECONDS):
    """
    Open a TLS connection to the primary of the configured database, verifying the certificate and host name.
    Args:
        configuration: the connector configuration.
        timeout_seconds: the read and write timeout of the connection.
    Returns:
        The pymysql connection.
    """
    return pymysql.connect(
        host=configuration["host"],
        user=configuration["username"],
        password=configuration["password"],
        database=configuration["database"] + "@primary",
        ssl=ssl.create_default_context(),
        connect_timeout=__CONNECT_TIMEOUT_SECONDS,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
    )


def first_column(connection, query: str, parameters=None):
    """
    Run a query and return its first column.
    Args:
        connection: the pymysql connection.
        query: the SQL text.
        parameters: the query parameters, if any.
    Returns:
        The values of the first column.
    """
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        return [row[0] for row in cursor.fetchall()]


def fetch_keyspaces(connection, database: str):
    """
    List the keyspaces whose names contain the database name, without the "<database>/" prefix.
    Args:
        connection: the pymysql connection.
        database: the configured database.
    Returns:
        The sorted keyspace names.
    """
    prefix = database + "/"
    names = first_column(connection, "show vitess_keyspaces like %s", ("%" + database + "%",))
    return sorted(name[len(prefix) :] if name.startswith(prefix) else name for name in names)


def fetch_shards(connection, database: str):
    """
    List the shards of the database, e.g. "-80" and "80-" for "<database>/-80" and "<database>/80-".
    Args:
        connection: the pymysql connection.
        database: the configured database.
    Returns:
        The sorted shard names.
    """
    shards = []
    for name in first_column(connection, "show vitess_shards like %s", (database + "/%",)):
        owner, separator, shard = name.partition("/")
        if separator and owner == database:
            shards.append(shard)
    return sorted(shards)


def fetch_columns(connection, keyspace: str, table_name: str):
    """
    List a table's columns with their declarations and whether they are part of the primary key.
    Args:
        connection: the pymysql connection.
        keyspace: the keyspace.
        table_name: the table.
    Returns:
        A list of (column name, column type, is primary key) tuples in ordinal order.
    """
    with connection.cursor() as cursor:
        cursor.execute(__COLUMN_QUERY, (table_name, keyspace))
        return [
            (name, column_type, str(column_key).upper() == "PRI")
            for name, column_type, column_key in cursor.fetchall()
        ]


def fetch_source_schema(configuration: dict):
    """
    Discover every keyspace, table and column, and the shards of the database.
    Every table is listed, including Vitess's internal online-DDL tables: PlanetScale's connector filters them
    first and then adds every table back while reading columns, and this keeps the same table list.
    Args:
        configuration: the connector configuration.
    Returns:
        A dictionary with "keyspaces" (keyspace to table to column list) and "shards".
    """
    database = configuration["database"]
    connection = connect(configuration)
    try:
        keyspaces = {}
        for keyspace in fetch_keyspaces(connection, database):
            quoted_keyspace = "`" + keyspace.replace("`", "``") + "`"
            tables = sorted(first_column(connection, f"show tables from {quoted_keyspace}"))
            keyspaces[keyspace] = {
                table: fetch_columns(connection, keyspace, table) for table in tables
            }
        return {"keyspaces": keyspaces, "shards": fetch_shards(connection, database)}
    finally:
        connection.close()


def ping(configuration: dict, timeout_seconds: int):
    """
    Confirm that the credentials open a working connection to the database primary.
    Args:
        configuration: the connector configuration.
        timeout_seconds: the connect, read and write timeout.
    """
    connection = connect(configuration, timeout_seconds)
    try:
        connection.ping(reconnect=False)
    finally:
        connection.close()
