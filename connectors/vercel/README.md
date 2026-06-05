# Vercel Connector Example

## Connector overview
This connector demonstrates how to fetch deployment data from [Vercel](https://vercel.com/) and upsert it into your destination using the Fivetran Connector SDK. The custom connector synchronizes deployment records from your personal Vercel account and implements pagination handling to efficiently process large datasets with incremental synchronization using timestamps.

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
fivetran init <project-path> --template connectors/vercel
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- Synchronizes deployments from Vercel's API `/v6/deployments` endpoint
- Supports both personal account and team resource access
- Implements pagination handling for large datasets with configurable limit 
- Incremental synchronization using timestamp-based state management 
- Comprehensive error handling with retry logic for API requests

## Configuration file
The configuration keys required for your connector are as follows:

```json
{
  "api_token": "<YOUR_VERCEL_API_TOKEN>",
  "team_id": "<YOUR_OPTIONAL_TEAM_ID>"
}
```

### Configuration parameters

- `api_token` (required): Your Vercel access token for API authentication
- `team_id` (optional): Team identifier to access team resources instead of a personal account. If not provided, the connector accesses your personal account resources.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
The connector uses the `requests` library for HTTP communication, which is pre-installed in the Fivetran environment.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
The connector uses Vercel access tokens for authentication. To obtain your API token:

1. Go to your [Vercel account settings](https://vercel.com/account/tokens).
2. Click **Create Token**.
3. Enter a descriptive name for the token.
4. Choose the appropriate scope.
5. Select an expiration date.
6. Make a note of the generated token. You will use it as the `api_token` in your connector's configuration.

## Team access
By default, the connector accesses resources from your personal Vercel account. To access deployments owned by a team:

1. Find your Team ID by navigating to your team settings in the Vercel dashboard or use the Vercel CLI.
2. Add the `team_id` parameter to the connector's `configuration.json` file.
3. Ensure your API token has the necessary permissions to access the team's resources.

When `team_id` is provided, the connector appends `?teamId=[teamID]` to the API endpoint URL to access team resources instead of personal account resources.

## Pagination
The connector implements Vercel's timestamp-based pagination system as described in the API documentation. It processes data in configurable batches and uses the `next` timestamp from the pagination response to fetch subsequent pages.

## Data handling
The connector processes data from the `/v6/deployments` endpoint which contains deployment records with status, timing, and build information. All nested JSON structures are flattened to create optimal table schemas for your destination. 

## Error handling
The connector implements comprehensive error handling strategies:
- 30-second HTTP timeout handling
- Rate limiting detection with exponential backoff
- Specific exception handling for different request failures
- Graceful error logging without exposing sensitive information
- Retry logic for transient errors

## Tables created
The connector creates the `DEPLOYMENT` table, which uses `uid` as the primary key. The table contains deployment records with status, timing, and build information flattened from the `/v6/deployments` endpoint. It includes flattened projectSettings data if available.

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.