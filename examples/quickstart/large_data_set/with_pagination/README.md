# Large Dataset with Pagination Connector Example

## Connector overview
This connector demonstrates how to handle large paginated datasets from an API using the Fivetran Connector SDK. It connects to the public [PokéAPI](https://pokeapi.co/) and iteratively fetches Pokémon records in batches using offset-based pagination.

It’s useful for:
- Building connectors for public APIs with large datasets.
- Learning how to manage pagination and state checkpointing.
- Syncing data from a JSON array into a structured destination table.

Each page contains 100 Pokémon records, and the connector continues fetching until no more pages remain.


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
fivetran init <project-path> --template examples/quickstart/large_data_set/with_pagination
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Connects to a public REST API.
- Uses offset-based pagination (offset, limit).
- Converts API results into a `pandas.DataFrame`.
- Sync rows to Fivetran using `op.upsert()`.
- Uses `op.checkpoint()` to persist the current pagination offset across syncs.


## Configuration file
The connector does not require any configuration parameters.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:
```
pandas==2.2.3
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector does not authenticate as it accesses a public API.


## Pagination
Pagination is handled using the PokéAPI’s `offset` and `limit` parameters.
- Each page retrieves up to 100 records.
- The `next` field from the API response is used to determine whether more pages remain.
- The offset is stored in the connector state after each page is processed.


## Data handling
- Each Pokémon record contains:
  - `name`: the name of the Pokémon.
  - `url`: the URL to fetch full Pokémon details (not expanded in this example).
- Data is upserted into the `POKEMONS` table row by row.
- The connector uses pandas to build and iterate over tabular rows.


## Error handling
- The connector raises an error if the API request fails or the response cannot be parsed.
- All sync progress is checkpointed after each page via` op.checkpoint(state)` to allow safe resumption.


## Tables Created
The connector creates a `POKEMONS` table:

```json
{
  "table": "pokemons",
  "primary_key": [],
  "columns": {
    "name": "STRING",
    "url": "STRING"
  }
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.