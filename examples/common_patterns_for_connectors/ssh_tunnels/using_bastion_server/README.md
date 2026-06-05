# SSH Tunnels Using Bastion Server Connector Example


## Connector overview
This example demonstrates how to fetch and upsert data from a private PostgreSQL database server through an SSH tunnel via a bastion host. It establishes an SSH tunnel using `paramiko` and `sshtunnel` to a bastion host which then connects to the database with `psycopg2`, and incrementally syncs rows from `SAMPLE_USERS` based on a `modified_at` timestamp.


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
fivetran init <project-path> --template examples/common_patterns_for_connectors/ssh_tunnels/using_bastion_server
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
The connector includes the following features:
- SSH tunnel to bastion host using `paramiko` and `sshtunnel`.
- Connects to PostgreSQL database using `psycopg2` running on private host via the bastion host.
- Incremental sync based on `modified_at` timestamp column.
- Error handling for SSH and database connection issues.
- Logging for debugging and monitoring.


## Configuration file
The connector reads the `configuration.json` to establish the SSH tunnel and DB connection.

- `bastion_host`: Public DNS/IP of the bastion.
- `bastion_port`: SSH port on bastion (default 22).
- `bastion_user`: SSH user for bastion.
- `bastion_private_key`: Base64‑encoded private key (PEM).
- `bastion_passphrase`: Optional passphrase for the private key.
- `db_host`: Private IP/DNS of PostgreSQL inside the network.
- `db_port`: PostgreSQL port.
- `db_user`: Database user.
- `db_password`: Database password.
- `db_name`: Database name.

```json
{
  "bastion_host": "<YOUR_BASTION_PUBLIC_IP_OR_DNS>",
  "bastion_port": "<YOUR_BASTION_SSH_PORT>",
  "bastion_user": "<YOUR_BASTION_USERNAME>",
  "bastion_private_key": "<YOUR_BASE64_ENCODED_BASTION_PEM>",
  "bastion_passphrase": "<YOUR_BASTION_PASSPHRASE>",
  "private_host": "<YOUR_PRIVATE_DATABASE_HOST>",
  "private_port": "<YOUR_PRIVATE_DATABASE_PORT>",
  "db_user": "<YOUR_DATABASE_USERNAME>",
  "db_password": "<YOUR_DATABASE_PASSWORD>",
  "db_name": "<YOUR_DATABASE_NAME>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following packages, which should be listed in `requirements.txt`:

```
sshtunnel==0.4.0
paramiko==3.5.1
psycopg2-binary==2.9.10
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
- `Bastion host`: `SSH` key‑based authentication with an `RSA` private key. Provide the key as a base64‑encoded PEM string in `bastion_private_key`. If the key is passphrase‑protected, set `bastion_passphrase`.
- `Database`: Username and password for `PostgreSQL`.

You can get the base64‑encoded PEM string by running the following command on macOS or Linux:
```bash
base64 -i /path/to/your/pem/file | pbcopy
```


## Pagination
Pagination is not applicable for this connector as it retrieves data directly from a database table.


## Data handling
The connector fetches data from the `SAMPLE_USERS` table in the PostgreSQL database. It uses an incremental sync strategy based on the `modified_at` timestamp column to ensure that only new or updated records are replicated during each sync. The connector handles the data in following way:
- Establishes an SSH tunnel to the bastion host.
- Connects to the `PostgreSQL` database through the SSH tunnel.
- Executes a SQL query to fetch records from the `SAMPLE_USERS` table where the `modified_at` timestamp is greater than the last synced timestamp.
- Upserts the fetched records into the destination.
- Closes the database connection and SSH tunnel after the sync is complete.


## Error handling
The connector includes error handling mechanisms to manage potential issues during the SSH tunnel establishment, database connection, and data retrieval processes. Common errors handled include:
- SSH connection failures (e.g., incorrect credentials, network issues).
- Database connection errors (e.g., invalid database credentials, unreachable database).
- SQL execution errors (e.g., malformed queries, permission issues).
- Logging of error messages for troubleshooting and debugging purposes.

## Tables created
The connector creates the following table in the destination:

- `SAMPLE_USERS`: Contains user data with fields such as `id`, `name`, and `modified_at`.

The schema of the `SAMPLE_USERS` table is as follows:
```json
{
  "id": "STRING",
  "name": "STRING",
  "modified_at": "UTC_DATETIME"
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
