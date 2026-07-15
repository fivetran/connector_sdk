# Marketstack Stock Data Connector Example

## Connector overview
This connector demonstrates how to implement a cursor-based sync strategy using the Fivetran Connector SDK. It connects to the [Marketstack API](https://marketstack.com/documentation), retrieves historical stock price data for a predefined list of tickers, and upserts the results into a table named `TICKERS_PRICE`.
The connector tracks sync progress using a cursor-based state mechanism (`date_from`, `date_to`, and `ticker_offset`) to support resumable and incremental syncing. It is ideal for learning how to handle paginated, stateful data pipelines with external APIs.


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
fivetran init <project-path> --template examples/common_patterns/cursors/marketstack
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to the [Marketstack API](https://marketstack.com/documentation) to fetch EOD stock data.
- Supports cursor-based incremental syncing using `date_from`, `date_to`, and `ticker_offset`.
- Fetches paginated results with offset handling (limit, offset).
- Provides robust error handling and logging for debugging failed syncs.
- Uses `schema()` and `update()` functions to define and execute the sync contract.
- Logs a summary of fetched data including ticker coverage and date range.


## Configuration file
The connector requires the following configuration parameters: 

```
{
    "apiKey": "<YOUR_MARKETSTACK_API_KEY>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:

```
requests
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
This connector uses a simple API key authentication mechanism. Your API key must be included as a query parameter in every request to the Marketstack API.

The API key is retrieved from the `configuration.json` file and passed as the `access_key` parameter in the request:
Example:
`GET /v1/eod?access_key=<YOUR_API_KEY>

You can obtain a free API key by signing up at [marketstack.com](https://marketstack.com/). Make sure your key is valid and has sufficient permissions for the endpoints being accessed.


## Pagination
Pagination is handled through the `limit` and `offset` parameters. The connector fetches up to 1000 records per request and continues retrieving data until the response contains no additional records.
The `offset` is incremented internally within the `get_ticker_price()` method, which accumulates all pages for a ticker before proceeding to the next.


## Data handling
The connector performs the following operations:
- State initialization: Initializes the cursor state with a date window (`start_cursor`, `end_cursor`) and a `ticker_offset`.
- Data fetching:
  - Iterates over a fixed set of tickers (`AAPL`, `MSFT`, `GOOG`, `INTC`). 
  - For each ticker, fetches all records in a date window using paginated requests. 
- Upserting: Syncs each record using `op.upsert()` into the `TICKERS_PRICE` table.
- Checkpointing: Saves the updated state using `op.checkpoint()` to resume from the correct ticker and date on the next run.


## Error handling
- HTTP errors are caught via `requests.exceptions.RequestException`.
- JSON parsing errors and missing keys are logged with descriptive RuntimeError messages.
- Unexpected exceptions are caught in `update()` and re-raised with full stack trace logs.
- A data summary is logged after each sync for auditing purposes.


## Tables created
The connector creates the `TICKERS_PRICE` table:

```
{
  "table": "tickers_price",
  "primary_key": ["symbol", "date"],
  "columns": {
     // Note: Columns are dynamically inferred from the Marketstack response. 
  }
}
```


## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.