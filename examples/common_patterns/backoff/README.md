# Connector SDK Backoff Strategies Connector Example

## Connector overview

This connector demonstrates retry and backoff handling for a paginated REST API endpoint using the Fivetran Connector SDK. It uses [fivetran-api-playground](https://pypi.org/project/fivetran-api-playground/) as the mock source.

The connector supports these retry strategies through the `backoff_strategy` field in `configuration.json`:

- `fixed`: waits the same number of seconds before every retry.
- `linear`: increases the wait time by a fixed amount on each retry.
- `exponential`: doubles the wait time on each retry.
- `exponential_with_cap`: uses exponential growth but limits the maximum wait time.
- `exponential_with_jitter`: uses a randomized exponential wait to reduce synchronized retries.
- `retry_after`: honors the source API's `Retry-After` header when present and falls back to capped exponential backoff.

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
fivetran init <project-path> --template examples/common_patterns/backoff
```

`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

To run this example with visible rate limiting behavior in `fivetran-api-playground`, start the source API with:

```bash
playground start --rate-limit --capacity 1
```

## Features

- Configurable backoff strategy (`backoff_strategy`).
- Retries network and timeout exceptions.
- Retries HTTP `429` (rate limit).
- Retries HTTP `5xx` server errors.
- Non-retry behavior for HTTP `4xx` client errors (except `429`).
- Frequent checkpointing for safe resume behavior.

## Configuration file

Use `configuration.json`:

```json
{
  "backoff_strategy": "<YOUR_BACKOFF_STRATEGY>"
}
```

Fields:

- `backoff_strategy`: one of `fixed`, `linear`, `exponential`, `exponential_with_cap`, `exponential_with_jitter`, `retry_after`.

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This example does not require `requirements.txt`.

> Note: [Some packages](https://fivetran.com/docs/connector-sdk/technical-reference#preinstalledpackages) are pre-installed in the Connector SDK runtime environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`. 

## Authentication

No authentication is required for this endpoint in `fivetran-api-playground`.

## Pagination

Pagination uses the `next_page_url` value returned by each response page.

Behavior:

1. Request first page with query params (`updated_since`, sort order, `per_page`).
2. Upsert current page items.
3. Move to `next_page_url` when present.
4. Stop when page has no data or no `next_page_url`.

Refer to the `sync_items` and `get_api_response` functions in `connector.py`.

## Data handling

- Destination table: `USER`
- Primary key: `id`
- State key: `last_updated_at`
- Checkpointing after every page.
- Checkpointing after each checkpoint interval.

Refer to the `schema` and `sync_items` functions in `connector.py`.

## Error handling

Retry logic is applied with a max retry cap:

- `__MAX_RETRIES = 5`
- `__REQUEST_TIMEOUT_SECONDS = 10`

Retry handling is centralized in `retry_or_raise`, which computes the delay, sleeps before the next attempt, and raises when retries are exhausted or when a response is non-retryable.

Backoff behavior by category:

- `429`: retries using the configured strategy. When the strategy is `retry_after`, `retry_or_raise` reads the `Retry-After` header before computing the delay.
- `5xx`: retries using configured strategy.
- Request exceptions (connection/timeouts): retries using configured strategy.
- Non-`429` `4xx`: fails immediately as non-retryable.

Refer to the `validate_configuration`, `compute_delay`, `retry_or_raise`, and `get_api_response` functions in `connector.py`.

## Tables created

- `USER`

Columns:

- `id`
- `name`
- `email`
- `address`
- `company`
- `job`
- `updatedAt`
- `createdAt`

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
