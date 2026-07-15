# Large Dataset Without Pagination Connector Example

## Connector overview
This connector demonstrates how to handle large dataset responses from an API that does not support traditional pagination. It connects to the public [PokéAPI](https://pokeapi.co/) and retrieves up to 100,000 Pokémon in a single request, then divides the data into smaller, manageable batches for processing and upserting into the destination.

This pattern is helpful when:
- The API returns a large dataset in a single payload.
- You want to avoid memory issues by processing the data in chunks.
- No `next` or `offset` parameter is available in the response to paginate externally.

Note: For APIs with proper pagination support, use offset or cursor-based pagination patterns instead for more reliable and scalable syncs.


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
fivetran init <project-path> --template examples/quickstart/large_data_set/without_pagination
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Connects to a public REST API.
- Requests a single large response with up to `100000` records.
- Splits the dataset into manageable `BATCH_SIZE` chunks (default: 100).
- Processes each batch using `pandas.DataFrame.iterrows()`.
- Upserts each row using `op.upsert()`.
- Stores sync progress using `op.checkpoint()` after each batch.


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
This API example does not support real pagination, so the connector handles large responses using batching.
- The connector sends one large request to the API.
- The data is received as a single response (`results` list).
- The results are processed using manual slicing into smaller `DataFrame` chunks.


## Data handling
- Each Pokémon record contains:
  - `name`: the name of the Pokémon.
  - `url`: the URL to fetch full Pokémon details (not expanded in this example).
- Data is upserted into the `POKEMONS` table row by row.
- The connector uses pandas to build and iterate over tabular rows.


## Error handling
- If the API request fails, `requests.get()` raises an exception.
- JSON parsing is done safely with `response.json()`.
- Any unhandled exceptions halt the sync and are surfaced in the logs.
- Sync progress is checkpointed after each batch using `op.checkpoint(state)`.


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