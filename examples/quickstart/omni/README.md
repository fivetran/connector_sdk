# Omni Connector Example

## Connector overview
This connector syncs the semantic layer of [Omni](https://omni.co), a business intelligence platform, from the Omni REST API into your destination. It replicates the shared model with its views, dimensions, measures, topics and topic join graph, plus the workbooks, dashboards and apps built on top of it.

Typical use cases include auditing how warehouse tables are exposed to analysts, tracking which dashboards are actually used, and giving AI agents the semantic definitions and `ai_context` guidance that Omni authors maintain.

Omni serves its semantic model as YAML documents over JSON: `GET /api/v1/models` lists the models and `GET /api/v1/models/{id}/yaml` returns a map of file path to raw YAML. The connector parses that YAML into rows, and reads documents from `GET /api/v1/documents`.


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
fivetran init <project-path> --template examples/quickstart/omni
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Syncs only the shared semantic model. Omni's model list is dominated by per-query and per-workbook models; a real instance returned 83,864 models of which exactly one was shared, so filtering on `modelKind=SHARED` keeps a sync to a handful of API calls.
- Parses view and topic YAML files into seven tables, including the SQL behind each dimension and measure and the `ai_context` of each topic.
- Flattens each topic's nested join tree into one row per view-to-view edge.
- Marks rows deleted when the definition disappears from Omni, using a deferred truncate that applies only after a successful sync.
- Defines a setup form with a fail-fast connection test.
- Retries rate limits, server errors and dropped connections with exponential backoff.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "base_url": "<YOUR_OMNI_URL>",
  "api_token": "<YOUR_OMNI_ORGANIZATION_API_KEY>"
}
```

- `base_url` – The host you sign in to Omni with, for example `acme.omniapp.co`. The scheme is optional and defaults to `https://`, and a custom domain works too. The connector appends `/api` when it is missing.
- `api_token` – An Omni Organization API key or Personal Access Token.

The same two fields are defined in the setup form (refer to `def configuration_form()`).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the `PyYAML` package to parse the YAML documents that Omni returns for each model.

```
PyYAML==6.0.2
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Omni authenticates every API request with a bearer token (refer to `def create_client()` in `omni_api.py`). Both an Organization API key and a Personal Access Token are accepted. An Organization API key is recommended, because a Personal Access Token inherits its creator's permissions and models that user cannot see would be silently missing from the synced metadata.

To set up authentication:

1. In Omni, go to Settings > API access > Organization keys.
2. Create a new organization key and copy it.
3. Provide the key as `api_token` in the `configuration.json` file, or in the setup form.

The setup form's connection test lists the shared models with a single attempt and a 10 second timeout, so a wrong URL or a blocked host is reported in seconds rather than after the sync retry budget (refer to `def connection_test()`).


## Pagination
The models and documents endpoints use cursor pagination: each page carries `pageInfo.nextCursor`, which is sent back as the `cursor` parameter until it is absent (refer to `def record_pages()` in `omni_api.py`). Each page is processed and checkpointed before the next one is requested, so the connector never holds a full listing in memory.

The model YAML endpoint is not paginated and returns the whole model in a single response. For scale, a large real instance produced 2,412 views, 60,341 dimensions, 3,354 measures, 103 topics and 353 join edges from its shared model, plus 1,275 documents.


## Data handling
Omni returns the model and the documents as full listings rather than a change feed, so every sync re-reads everything and the state stays empty (refer to `def update()`).

- Views are named by Omni's own `viewNames` mapping, which already accounts for folder prefixes, for example `EXPORTS/cm_metrics.view` becomes `exports__cm_metrics`. The `# Reference this view as` comment and the file path are fallbacks for the Git integration layout, which ships no mapping (refer to `def resolve_view_name()` in `omni_model_parser.py`).
- Files that are neither views nor topics, such as Omni's `model` and `relationships` specials, are skipped. A single empty or malformed YAML file is skipped rather than failing the sync, and YAML is loaded with the safe loader, so a document carrying a class tag counts as malformed.
- Document records are flattened, with the nested `owner` and `folder` objects becoming `owner_*` and `folder_*` columns (refer to `def document_row()` in `omni_model_parser.py`).

Deletions are reconciled with a deferred truncate (refer to `def upsert_row()`). Before the first row of each table in a sync, the connector calls `op.truncate(table, deferred=True)`. When the sync completes successfully, every row of that table that was not upserted in this sync is marked `_fivetran_deleted = true`, which is how a view, dimension, measure, topic, join or document removed in Omni gets marked deleted downstream. If the sync fails, nothing is marked deleted.

A table that receives no rows in a sync is not truncated, and the connector logs a warning instead. A listing that comes back empty without failing, for example because a token loses sight of the shared model, would otherwise mark the entire semantic layer deleted.


## Error handling
- Rate limits and transient server errors – HTTP 429 and 5xx responses are retried up to five attempts in total. When Omni sends `Retry-After`, the connector waits that long; otherwise the wait doubles from 2 seconds. Both are capped at 60 seconds (refer to `def get_json()` and `def retry_wait_seconds()` in `omni_api.py`).
- Dropped connections – Connection errors and timeouts are retried on the same budget.
- Permanent failures – A rejected token, a missing model or any other 4xx response fails on the first attempt, because retrying cannot fix it.
- Bounded error messages – Error bodies are truncated to 512 characters before they become exception messages, since a gateway can answer with a full HTML page (refer to `def summarize()` in `omni_api.py`).
- Unrecognised responses – A page without a known record list fails the sync rather than being treated as empty, so a change in the API's response shape cannot quietly mark every row deleted (refer to `def records()` in `omni_api.py`).


## Tables created
The connector creates the following tables (refer to `def schema()`). Columns whose types are not declared in `schema()` are inferred from the data.

| Table | Primary key | Columns | Grain |
| --- | --- | --- | --- |
| `model` | `id` | `name`, `connection_id` | One row per Omni model. |
| `views` | `model_id`, `view_name` | `schema_name`, `table_name`, `label`, `description`, `file_path` | One row per view, with the warehouse table it maps onto. Named `views` because `VIEW` is a restricted identifier on some destinations. |
| `dimension` | `model_id`, `view_name`, `field_name` | `label`, `sql`, `format`, `description`, `is_primary_key` (BOOLEAN) | One row per groupable field on a view. |
| `measure` | `model_id`, `view_name`, `measure_name` | `label`, `aggregate_type`, `sql`, `description` | One row per aggregation on a view. |
| `topic` | `model_id`, `topic_name` | `base_view`, `label`, `group_label`, `description`, `ai_context`, `file_path` | One row per topic. |
| `topic_join` | `model_id`, `topic_name`, `from_view`, `to_view` | none | One row per view-to-view join edge. |
| `document` | `id` | `name`, `description`, `url`, `scope`, `connection_id`, `owner_id`, `owner_name`, `folder_id`, `folder_name`, `folder_path`, `has_dashboard` (BOOLEAN), `has_app` (BOOLEAN), `visits` (INT), `last_viewed_at` (UTC_DATETIME), `updated_at` (UTC_DATETIME), `is_deleted` (BOOLEAN) | One row per workbook, dashboard or app. `is_deleted` is Omni's own flag, separate from `_fivetran_deleted`. |


## Additional files
- `omni_api.py` – Calls the Omni REST API: builds the API root from the Omni URL, follows cursor pagination, and retries transient failures.
- `omni_model_parser.py` – Parses Omni's view and topic YAML files into rows for the semantic layer tables and flattens document records.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
