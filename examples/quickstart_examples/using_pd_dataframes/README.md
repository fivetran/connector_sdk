# DataFrame Connector with NaN Handling Example

## Connector overview
This connector demonstrates how to work with pandas DataFrames when ingesting data from an API and syncing it to multiple tables using the Fivetran Connector SDK. It highlights key practices such as:
- Converting `NaN` values to `None` (null), which is required for compatibility with Fivetran’s destination infrastructure.
- Structuring data into multiple destination tables (`PROFILE`, `LOCATION`, `LOGIN`, and `TABLE_WITH_NAN`).
- Handling checkpointing with a state object.
- Fetching and processing real-time user data from the [RandomUser API](https://randomuser.me/).


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
fivetran init <project-path> --template examples/quickstart_examples/using_pd_dataframes
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Syncs user profile, location, and login data into separate tables.
- Demonstrates three methods for iterating over DataFrames.
- Handles and replaces `NaN` values with `None` using multiple approaches.
- Stores sync state and uses it for incremental updates.
- Uses `requests` to call the RandomUser API.
- Generates dummy data with random NaN values for the table_with_nan table.


## Configuration file
The connector does not require any configuration parameters.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector requires the following Python dependencies:
```
pandas==2.2.3
numpy==2.2.3
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Not Applicable - the RandomUser API is public.


## Pagination
Not applicable - the connector fetches 2 new records per run and simulates multiple iterations locally.


## Data handling
- Data is organized into four tables:
  - `PROFILE`
  - `LOCATION`
  - `LOGIN`
  - `TABLE_WITH_NAN`
- Each DataFrame is handled with its own `upsert()` method.
- Three methods are shown for dealing with NaN values:
  - `.replace(np.nan, None)`
  - `.where(pd.notnull(...), None)`
  - `.fillna(np.nan).replace([np.nan], [None])`
- DataFrames are converted to records (list of dictionaries) for syncing.


## Error handling
- API errors are raised if the request to `https://randomuser.me/api/` fails.
- Missing or null fields are handled safely.
- All `NaN` values are converted to `None` before upsert.
- State is checkpointed after every batch or record to ensure resumable syncs.


## Tables Created
The connector creates following four table:

`PROFILE`:

```json
{
  "table": "profile",
  "primary_key": ["id"]
}
```

`LOCATION`:

```json
{
  "table": "location",
  "primary_key": ["profileId"]
}
```

`LOGIN`:

```json
{
  "table": "login",
  "primary_key": ["profileId"]
}
```

`TABLE_WITH_NAN`:

```json
{
  "table": "table_with_nan",
  "primary_key": ["id"]
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.