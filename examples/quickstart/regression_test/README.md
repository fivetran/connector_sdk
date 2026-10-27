# Regression Test Connector Examples

## Connector overview
These examples show how to use record and replay regression testing with the Fivetran Connector SDK. You record a connector run against a live source once, and then replay the recording without calling the source to confirm that code changes don't alter the data your connector delivers.

Both examples read customers from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/) with page-number pagination. They differ only in how you start the record and replay runs:

| Example | How you run it |
|---------|----------------|
| [`cli_example`](cli_example) | With the `fivetran debug --record` and `fivetran debug --replay` commands. |
| [`ide_example`](ide_example) | From an IDE or a script, by passing `record=` and `replay=` to `connector.debug()`. |

Regression testing is in Private Preview. Please contact your Fivetran representative to request access.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- A `fivetran-connector-sdk` version that includes regression testing (the `action` decorator and the `--record` and `--replay` options)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

Start the API Playground in a separate terminal. It serves `http://127.0.0.1:5001`:

```bash
pip install fivetran-api-playground
playground start
```

To initialize a new Connector SDK project using one of these examples as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/regression_test/cli_example
```

For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).


## Features
- Marks the functions that read from the source with the `@action` decorator.
- Records the `@action` calls, the starting state, and the output of a run with `--record`.
- Limits the size of a recording with `--max-records`, which counts the `upsert`, `update`, `delete`, and `truncate` operations. The default is 100.
- Replays a recording with `--replay`, which returns the recorded results and doesn't call the source.
- Compares the replay `state.json` and `warehouse.db` with the recorded ones to detect regressions.
- Uses `match` to identify a call by selected arguments, so secrets and other unwanted arguments aren't saved.


## Using `@action` with `match`
During a replay, the connector finds the recorded result of a call by the `@action` name and the call's arguments. `fetch_customers_page` uses `match` to say which arguments count:

```python
@action("customers_page", match=lambda page, updated_since: {"page": page, "updated_since": updated_since})
def fetch_customers_page(page: int, updated_since: str = None):
```

`match` must accept the same arguments as the decorated function and return a dictionary. Here it returns `page` and `updated_since`, which together identify one page of one query. Use `match` to leave out arguments that change on every run or that you don't want in the recording, such as a secret. For example, suppose `fetch_customers_page` also took a `request_id` that changes on every run and an `api_key`:

```python
@action(
    "customers_page",
    match=lambda page, updated_since, request_id, api_key: {"page": page, "updated_since": updated_since},
)
def fetch_customers_page(page: int, updated_since: str, request_id: str, api_key: str):
    ...
```

`match` returns only `page` and `updated_since`, so:

- The fixture stores only those two values for the call. `request_id` and `api_key` aren't saved.
- During a replay, a call with the same `page` and `updated_since` finds the recorded page, even though `request_id` is different.

If you don't set `match`, as in `@action("customers_page")`, every argument is part of the call identity. Use that form only when all arguments have the same values on every run. If an argument changes on every run, such as a timestamp or a request ID, the replay can't find the recorded call and fails.

`match` doesn't work with functions that accept `*args` or `**kwargs`. The arguments and results must be JSON-serializable.


## How regression testing works
1. `@action` marks the function that reads from the source.
2. A record run calls the source and saves the run in `fixtures/<scenario>/`:
   - `record_start/` holds the starting `state.json` and `warehouse.db`. It's a snapshot of the `files` folder taken just before the run.
   - `record_data/fixture.jsonl` holds each `@action` call, one per line, with its name, arguments, and result.
   - `record_end/` holds the `state.json` and `warehouse.db` that the run produced. A replay is compared with them.

   > NOTE: A record run saves the arguments of every `@action` call in the fixture. If you don't set `match`, all arguments are saved and identify the call. We recommend setting `match` and returning only the arguments you need to identify the call, so that secrets and other unwanted arguments aren't stored in the fixture. Arguments with names that end in `token`, `secret`, `password`, `api_key`, `credential` or `configuration` are saved as a hash, but other sensitive values aren't masked. Results are never masked.
3. A replay run starts from `record_start/` in a separate `.fixtures_replay` folder, so your `files` folder and the recording aren't changed. Each `@action` call returns the result from `fixture.jsonl`, and the source isn't called.
4. When the replay finishes, its `state.json` and `warehouse.db` are compared with the ones in `record_end/`. For `warehouse.db`, the comparison covers tables, columns, and rows. If they match, there is no regression. If they differ, the run lists each difference and fails.

The recording stops when the number of write operations reaches the `--max-records` limit. The limit is saved in the fixture, so a replay applies the same limit.

Commit the `fixtures` folder with your connector. A replay creates a `.fixtures_replay` folder, which is added to your `.gitignore` file and shouldn't be committed.


## Configuration file
No configuration file values are required for these examples. The `configuration.json` file contains an empty object.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
These connectors do not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The API Playground does not require authentication.


## Pagination
The connector uses page-number pagination. It requests `page=1`, `page=2`, and so on, until the last page is reached or a page has no data. The API returns customers sorted by `updatedAt`, oldest first, and accepts an inclusive `updated_since` filter. The connector saves the newest `updatedAt` it has synced as `last_updated_at` in state, and checkpoints after each fully processed page. The next sync sends `updated_since=<last_updated_at>` and starts again at page 1 of that filtered query, so it reads only new and changed customers and never skips changes on earlier pages. The first sync has no state and reads all customers. Because the filter is inclusive, the newest customer is read again on every sync, which is harmless for an upsert.


## Data handling
- The `update()` function upserts each customer into the `customer` table.
- The recorded `@action` results must be JSON-serializable, so the function returns the parsed JSON response.
- Each recording holds the `customers_page` calls, one per page.


## Error handling
- The `get_with_retry()` helper retries transient failures, which are timeouts, connection errors, and HTTP 429, 500, 502, 503, and 504 responses. It makes up to three attempts with exponential backoff (2 seconds, then 4 seconds) and logs each retry.
- Other HTTP errors, such as 400 or 404, raise immediately through `response.raise_for_status()` because retrying can't fix them.
- Both `@action` functions call the helper, so retries happen only during a live run or `--record`. A replay returns the recorded result and never makes a request.
- A replay fails with a message to record the scenario again if the connector makes an `@action` call that isn't in the recording.


## Tables Created
The connector creates a `customer` table:

```json
{
  "table": "customer",
  "primary_key": ["id"]
}
```


## Additional considerations
- Regression testing supports only JSON-serializable data. The arguments and results of an `@action` function must be JSON-serializable, such as dictionaries, lists, strings, numbers, booleans, and `None`.
- Regression testing is in Private Preview. If you want to try this feature, contact our Support team to enable it.

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
