# Bitbucket Files Connector Example

## Connector overview
This connector syncs a single [Bitbucket Cloud](https://bitbucket.org) repository from the Bitbucket Cloud REST API (v2.0) into your destination: the repository's metadata, the file listing of its default branch, and each file's raw content. File content is replicated as unstructured files in the destination's file stage rather than stored in a column, so code and documentation can be parsed, embedded and searched downstream.

Every sync re-reads the repository's current state. Files removed from the repository, including the old path of a renamed file, are marked deleted in the destination.

Because file content is replicated as unstructured files, this connector requires a destination that supports file upload, such as Snowflake, BigQuery or Databricks (Unity Catalog).


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
fivetran init <project-path> --template examples/quickstart/bitbucket_files
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Syncs one repository's metadata and every file on its default branch.
- Streams each file's raw bytes to the destination's file stage with `FileUpload`, and records the staged path in `_fivetran_file_path`.
- Filters files server-side: files only (no directories), at most 1 MB each, optionally narrowed by an include path glob.
- Marks files removed from the repository as deleted, using a deferred truncate that applies only after a successful sync.
- Defines a setup form with a connection test.
- Retries rate limits, server errors and dropped connections with exponential backoff.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "workspace": "<YOUR_BITBUCKET_WORKSPACE>",
  "repository_slug": "<YOUR_BITBUCKET_REPOSITORY_SLUG>",
  "email": "<YOUR_ATLASSIAN_ACCOUNT_EMAIL>",
  "api_token": "<YOUR_ATLASSIAN_API_TOKEN>",
  "include_path_pattern": "<OPTIONAL_INCLUDE_PATH_GLOB>"
}
```

- `workspace` – The Bitbucket workspace ID. If you access it at `https://bitbucket.org/my-team`, the workspace is `my-team`.
- `repository_slug` – The slug of the repository to sync. If you access it at `https://bitbucket.org/my-team/my-repo`, the repository is `my-repo`.
- `email` – The email of the Atlassian account that owns the API token.
- `api_token` – An Atlassian API token.
- `include_path_pattern` – Optional. Only files whose path matches this Bitbucket glob, for example `*.py`, are synced. Leave it blank to sync all files.

The same fields are defined in the setup form (refer to `def configuration_form()`).

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Authentication
The connector authenticates with HTTP Basic, using the Atlassian account email as the username and an Atlassian API token as the password (refer to `def create_session()` in `bitbucket_api.py`).

To set up authentication:

1. Sign in to your Atlassian account and create an API token with read access to Bitbucket repositories.
2. Provide the account email as `email` and the token as `api_token` in the `configuration.json` file, or in the setup form.
3. Ensure the account can read the repository you configure.

The setup form's connection test fetches the configured repository once and reports an authentication failure, a repository that is not found, or an unreachable Bitbucket (refer to `def connection_test()`).


## Pagination
The file listing is paginated with Bitbucket's `next` field, an absolute URL to the following page that already carries the query parameters. The connector requests pages of 100 entries up to a directory depth of 100 and follows `next` until a page has none (refer to `def file_pages()` in `bitbucket_api.py`). Each page is processed before the next one is requested, so the listing is never held in memory.


## Data handling
- The repository row flattens `mainbranch.name` into `default_branch`, and renames the API's `language` to `main_language` because `LANGUAGE` is a reserved SQL keyword (refer to `def repository_row()`).
- Each file row is stamped with the owning repository's `uuid`, flattens `commit.hash` into `commit_hash`, and sets `file_id` to the path and `modified_at` to the sync start time, as a stable per-file id and modified-at cursor for document-parsing pipelines (refer to `def repository_file_row()`).
- Each file's bytes are read from the raw `/src` endpoint and streamed into the file stage together with its row (refer to `def upsert_file()`). The file's repository path is used as its staged path.
- The state stays empty, because every sync re-reads the repository's current state. The connector checkpoints every 100 files and at the end of the sync.

Deletions are reconciled with a deferred truncate (refer to `def sync_files()`). Before the first file is upserted, the connector calls `op.truncate("repository_file", deferred=True)`. When the sync completes successfully, every file row that was not upserted in this sync is marked `_fivetran_deleted = true`. If the sync fails, nothing is marked deleted. The `repository` table is not truncated.


## Error handling
- Unfetchable file content – If a file's content cannot be fetched after retries, the file is skipped and the sync continues. Its row is still upserted with the same `_fivetran_file_path`, so the bytes staged by an earlier sync stay in place (refer to `def upsert_file()`). A failure while the bytes are being uploaded fails the sync.
- Transient errors – HTTP 429 and 5xx responses, connection errors and timeouts are retried up to three attempts with exponential backoff from 2 seconds (refer to `def get()` in `bitbucket_api.py`).
- Permanent errors – Any other 4xx response, such as a rejected token, fails on the first attempt.
- Missing default branch – A repository without a default branch fails the sync with a message asking for at least one commit on the default branch (refer to `def sync_repository()`).


## Tables created
The connector creates the following tables (refer to `def schema()`). Columns whose types are not declared in `schema()` are inferred from the data.

| Table | Primary key | Columns | Grain |
| --- | --- | --- | --- |
| `repository` | `uuid` | `name`, `full_name`, `slug`, `description`, `is_private` (BOOLEAN), `size` (LONG), `created_on` (UTC_DATETIME), `updated_on` (UTC_DATETIME), `main_language`, `default_branch` | One row for the configured repository. |
| `repository_file` | `repository_uuid`, `path` | `type`, `size` (LONG), `mimetype`, `file_id`, `modified_at` (UTC_DATETIME), `commit_hash`, `_fivetran_file_path` | One row per file on the default branch. `_fivetran_file_path` points to the file's bytes in the destination's file stage. |


## Additional files
- `bitbucket_api.py` – Calls the Bitbucket Cloud REST API: builds the request URLs and the file filter, follows pagination, opens streaming content requests, and retries transient failures.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
