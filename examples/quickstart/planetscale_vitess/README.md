# PlanetScale Vitess Connector Example

## Connector overview
This connector replicates tables from a [PlanetScale](https://planetscale.com) database, a MySQL-compatible database built on Vitess, into your destination. It discovers keyspaces, tables, columns and shards over PlanetScale's MySQL endpoint, then reads each table shard through the Vitess VStream gRPC API: first an initial copy of the rows, then the binlog changes after it, including updates and deletes.

Typical use cases include replicating a sharded PlanetScale database for analytics without running a separate change data capture pipeline, and keeping deletes in the destination in step with the source.

The connector follows Fivetran's Java PlanetScale Vitess connector for schema discovery, type mapping, value conversion, the setup form and the connection test, and PlanetScale's Go connector for the state layout, so per-shard cursors use the same encoding.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/planetscale_vitess
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Discovers every keyspace of the database and writes each keyspace to its own destination schema.
- Runs an initial copy of each table shard and resumes an interrupted copy from the last primary key VStream reported.
- Streams inserts, updates and deletes after the copy, and replaces a row whose primary key changed.
- Keeps one cursor per table and shard in the state, in the same layout as PlanetScale's Go connector.
- Reads from the primary or from a replica, and syncs all shards or a configured list.
- Optionally writes `tinyint(1)` columns as `BOOLEAN`.
- Defines a setup form with a connection test that checks HTTPS reachability and then the database credentials.
- Lengthens the read window and backs off when VStream times out, and starts a new initial copy when the source has purged the binlogs a cursor points at.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "host": "<YOUR_PLANETSCALE_HOST>",
  "database": "<YOUR_PLANETSCALE_DATABASE>",
  "username": "<YOUR_PLANETSCALE_USERNAME>",
  "password": "<YOUR_PLANETSCALE_PASSWORD>",
  "shards": "<OPTIONAL_COMMA_SEPARATED_SHARDS>",
  "use_replica": "false",
  "treat_tiny_int_as_boolean": "false"
}
```

- `host` – The PlanetScale host name, for example `aws.connect.psdb.cloud`.
- `database` – The PlanetScale database name.
- `username` – The username of a PlanetScale password.
- `password` – The PlanetScale password.
- `shards` – Optional. A comma-separated list of shards to sync, for example `-80,80-`. Set it to an empty string to sync every shard.
- `use_replica` – `true` to read from a replica, `false` to read from the primary.
- `treat_tiny_int_as_boolean` – `true` to write `tinyint(1)` columns as `BOOLEAN`, `false` to write them as `INT`.

The boolean settings accept the same spellings as Go's `strconv.ParseBool`: `1`, `t`, `T`, `TRUE`, `true`, `True`, `0`, `f`, `F`, `FALSE`, `false` and `False`. The same fields are defined in the setup form (refer to `def configuration_form()`).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The `requirements.txt` file lists the Python libraries the connector needs:

```
grpcio==1.85.3
protobuf==7.36.2
PyMySQL==1.2.4
```

- `grpcio` – Calls the VStream gRPC API.
- `protobuf` – Encodes and decodes the VStream messages and the state cursors.
- `PyMySQL` – Runs schema discovery and the connection test over the MySQL protocol.

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector authenticates with a PlanetScale database password. It sends the username and password as HTTP Basic credentials in the `authorization` header of each VStream call, and uses them to log in over MySQL with TLS for schema discovery. Both connections verify the server certificate.

To create the credentials, do the following:
1. Log in to your PlanetScale account and open the database.
2. Go to **Settings > Passwords** and click **New password**.
3. Select the branch to replicate and a role that can read the data.
4. Make a note of the host name, username and password. You will need to add them to the `configuration.json` file.


## Data handling
Schema discovery runs once per process and is shared by `schema()` and `update()` (refer to `def source_schema(configuration)` and `planetscale_metadata.py`). The connector lists keyspaces with `show vitess_keyspaces`, tables with `show tables`, columns from `information_schema.columns`, and shards with `show vitess_shards`.

`update()` reads every table shard in turn (refer to `def sync_table_shard(configuration, state, keyspace, table_name, shard, columns)`):
1. It asks VStream for the latest position of the shard and stops if the saved cursor is already there.
2. It opens a VStream from the saved cursor. A cursor without a position makes VStream copy the table first.
3. It writes each row change and saves the cursor at each VStream position, and at least every 1,000 rows or 10 minutes during a copy.
4. It repeats until the cursor reaches the latest position.

Row changes are written as follows (refer to `def row_handler(keyspace, table_name, primary_key)`):
- Inserts and updates are written with `op.upsert()`.
- Deletes are written with `op.delete()` and appear in the destination with `_fivetran_deleted` set to `true`.
- An update that changes the primary key deletes the old key and upserts the new row.
- For a table without a primary key, Fivetran adds `_fivetran_id`, a hash of the row, and a delete matches on the whole row. Identical rows therefore collapse into one destination row.

Column types are mapped from the MySQL declaration (refer to `def map_column_type(column_type, treat_tiny_int_as_boolean)` in `value_converter.py`):

| MySQL type | Destination type |
|---|---|
| `tinyint(1)` with `treat_tiny_int_as_boolean` | `BOOLEAN` |
| `tinyint`, `smallint`, `mediumint`, `year`, signed `int` | `INT` |
| `mediumint unsigned` | `STRING` |
| `int unsigned`, `bigint`, `bit` | `LONG` |
| `decimal(p,s)` | `DECIMAL` with the same precision and scale |
| `float`, `double` | `DOUBLE` |
| `date` | `NAIVE_DATE` |
| `datetime` | `NAIVE_DATETIME` |
| `timestamp` | `UTC_DATETIME` |
| `json`, `set`, geometry types | `JSON` |
| `binary`, `varbinary`, `blob` types | `BINARY` |
| `time`, `enum`, text types and others | `STRING` |

Values are converted the way the Java connector converts them (refer to `def convert(field, raw_value, data_type)`). Geometry values are written as GeoJSON, `enum` values given as indexes are mapped to labels, `set` values given as bit masks are mapped to comma-separated labels, and zero `timestamp` values become the Unix epoch.


## Error handling
- Read timeouts – The read window starts at 60 seconds, grows by a factor of 2.8 after each timeout up to one hour, and the connector waits 10 seconds, doubling up to five minutes, after a timeout without progress. After five such timeouts in a row the connector stops reading the shard, keeps its cursor and raises a warning with `op.warning()` (refer to `def handle_timeout(state, progressed, table_name, listener, sleeper)` in `vstream_reader.py`).
- Purged binlogs – When the source has purged the binlogs a cursor points at, the connector resets that shard's cursor and starts a new initial copy.
- Schema changes – When VStream cannot build a replication plan after a schema change, the sync fails with a message asking for a historical re-sync.
- Other errors – The connector saves the shard's latest cursor with `error_message` and `error_code` in the state, checkpoints, and fails the sync. A row that cannot be converted keeps the cursor at the start of the read, so no change is skipped.
- Connection test – The test fails with a description of the problem when the configuration is invalid, the host is unreachable over HTTPS, or the credentials do not open a MySQL connection (refer to `def connection_test(configuration)`).


## Tables created
The connector creates one destination schema per keyspace and one table per source table, named after the source table. Each table has the source columns with the types listed in [Data handling](#data-handling) and the source primary key. A table without a primary key gets `_fivetran_id` as its primary key.

The state stores one cursor per table shard:

```json
{
  "keyspaces": {
    "<keyspace>": {
      "streams": {
        "<keyspace>:<table>": {
          "shards": {
            "<shard>": {"cursor": "<Base64 TableCursor>"}
          }
        }
      }
    }
  }
}
```


## Additional files
- `planetscale_metadata.py` – Discovers keyspaces, tables, columns and shards over PlanetScale's MySQL endpoint, and pings the database for the connection test.
- `vstream_reader.py` – Opens VStream calls and reads a table shard, with the copy, checkpoint, timeout and retry logic.
- `value_converter.py` – Maps MySQL column types to Fivetran types and converts VStream values, including geometry, `enum` and `set`.
- `vitess_messages.py` – Defines the Vitess and PlanetScale protobuf messages the connector uses, built at runtime from Vitess v0.24.1 field numbers so no generated code is needed.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

Note: The connector does not use gRPC compression, while the Java connector uses Snappy, which Python gRPC does not support. Temporal values are truncated to microseconds, `datetime` and `date` values in year 0000 are rejected, and WKB geometry types above 7 are not supported.
