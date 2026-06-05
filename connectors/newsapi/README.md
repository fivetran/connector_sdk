# News API Connector Example

## Connector overview
This connector demonstrates how to use the [News API](https://newsapi.org/) with the Fivetran Connector SDK to retrieve and sync articles related to specific topics. You can configure multiple topics, each of which will be queried and synced into a single table `ARTICLE`.

This connector supports:
- Time-windowed incremental syncs using `occurredAfter` and `occurredBefore`.
- Topic-based filtering of news articles.
- Pagination with `page` and `pageSize` to handle large result sets.
- Safe handling of nested and optional fields.

This example uses the [News API's /v2/everything](https://newsapi.org/docs/endpoints/everything) endpoint and assumes an active API key (free or paid).


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
fivetran init <project-path> --template connectors/newsapi
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Syncs articles per topic into a shared table.
- Uses date-based incremental replication via `occurredAfter` and `occurredBefore`.
- Handles paginated responses (`page`, `pageSize`).
- Converts nested structures into flat key-value pairs.
- Uses `op.upsert()` and `op.checkpoint()` to track state and emit records.


## Configuration file
The connector requires the following configuration parameters:

```json
{
    "API_KEY": "<your_api_key from newsAPI>",
    "pageSize": "100",
    "topic": "[\"Artificial Intelligence\", \"Michigan\", \"Taylor Swift\"]"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python packages:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The connector uses a Bearer token for authentication.


## Pagination
Pagination is implemented using the News API's `page` and `pageSize` parameters. It continues until:
- All pages are retrieved.
- Or the temporary dev limit of 100 results is reached.


## Data handling
Each article contains fields such as:
- source.name
- publishedAt
- author
- title
- description
- content
- url 

The connector flattens nested dictionaries and handles missing or optional values gracefully.


## Error handling
- HTTP errors are raised via `raise_for_status()`.
- Sync failures are logged with full stack traces.
- Missing config values (`topic`, `API_KEY`) raise explicit `ValueError`.
- Paginated state is checkpointed after each page and topic sync.


## Tables created
The connector creates an `ARTICLE` table:

```json
{
  "table": "article",
  "primary_key": ["source", "published_at"],
  "columns": {
    "source": "STRING",
    "published_at": "UTC_DATETIME"
  }
}

```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.