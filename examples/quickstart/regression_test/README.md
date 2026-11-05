# Regression Test Connector Example

## Connector overview
This example shows how to use record and replay regression testing with the Fivetran Connector SDK. You record a connector run against a live source once, and then replay the recording without calling the source to confirm that code changes don't alter the data your connector delivers.

The connector reads sample records from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/), a local mock API that serves generated test data, so you don't need a real source or credentials. Each customer has an `id`, `name`, `email`, `address`, `company`, `job`, `createdAt`, and `updatedAt`. The connector reads them with page-number pagination and upserts them into the `CUSTOMER` table. You can start the record and replay runs in either of these ways:

| How you run it | Command |
|----------------|---------|
| From the command line | `fivetran debug --record <scenario>` and `fivetran debug --replay <scenario>` |
| From an IDE or a script | Pass `record=` and `replay=` to `connector.debug()`, as the `__main__` block in `connector.py` does. |

Regression testing is in [Public Preview](https://fivetran.com/docs/core-concepts#releasephases). For more information, refer to the [Regression Testing documentation](https://fivetran.com/docs/connector-sdk/testing/regression-testing).


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

To initialize a new Connector SDK project using this example as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/regression_test
```

For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

### Run from the command line
```bash
fivetran debug --record basic --max-records 50
fivetran debug --replay basic
```

The record run saves the scenario `basic` into `fixtures/basic/` and stops after 50 write operations. The replay doesn't call the source. When it finishes, it compares the resulting state and `warehouse.db` with the recorded ones. If they match, the run logs `replay finished and its state and warehouse.db match the recording`. If they don't, the run prints each mismatch and exits with code 1.

### Run from an IDE or a script
In the `__main__` block of `connector.py`, `MODE` is set to `"record"`. Run the file to record the scenario `basic`. Then set `MODE` to `"replay"` and run the file again. You can also run it from a terminal with `python connector.py`. The block passes the command-line options to `connector.debug()`:

| `debug()` argument | Command-line option | Description |
|--------------------|---------------------|-------------|
| `record="<scenario>"` | `--record <scenario>` | Records the run into `fixtures/<scenario>/`. |
| `max_records=<N>` | `--max-records <N>` | Stops the recording after `N` write operations (`op.upsert`, `op.update`, and `op.delete`). The default is 100. Use only with `record`. |
| `replay="<scenario>"` | `--replay <scenario>` | Replays the scenario and compares the output with the recording. |

You can't combine `record` and `replay`, or use `max_records` with `replay`. Recording over an existing scenario asks for confirmation, so run the file from a terminal to answer it.


## Features
- Marks the functions that read from the source with the `@action` decorator.
- Records the `@action` calls, the starting state, and the output of a run with `--record`.
- Limits the size of a recording with `--max-records`, which counts the `op.upsert`, `op.update`, and `op.delete` calls. The default is 100.
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
1. Add the `@action` decorator to each function in your connector that calls the source, such as the function that fetches a page of customers. A record run saves these calls, and a replay returns the saved results instead of calling the source.
2. A record run calls the source and saves the run in `fixtures/<scenario>/`:
   - `record_start/` holds the starting `state.json` and `warehouse.db`. It's a snapshot of the `files` folder taken just before the run.
   - `record_data/fixture.jsonl` holds each `@action` call, one per line, with its name, arguments, and result.
   - `record_end/` holds the `state.json` and `warehouse.db` that the run produced. A replay is compared with them.
3. A replay run starts from `record_start/` in a separate `.fixtures_replay` folder, so your `files` folder and the recording aren't changed. Each `@action` call returns the result from `fixture.jsonl`, and the source isn't called.
4. When the replay finishes, its `state.json` and `warehouse.db` are compared with the ones in `record_end/`. For `warehouse.db`, the comparison covers tables, columns, and rows. If they match, there is no regression. If they differ, the run lists each difference and fails.

Note: A record run saves the arguments of every `@action` call in the fixture. If you don't set `match`, all arguments are saved and identify the call. We recommend setting `match` and returning only the arguments you need to identify the call, so that secrets and other unwanted arguments aren't stored in the fixture. Arguments with names that end in `api_key`, `api-key`, `apikey`, `token`, `secret`, `password`, `credential`, `configuration` or `configurations` are saved as a hash, but other sensitive values aren't masked. Results are never masked.

The `--max-records` limit works as follows:
- It counts every `op.upsert`, `op.update`, and `op.delete` call. `op.checkpoint` and `op.truncate` aren't counted.
- The first `N` write operations go through. The next write stops your `update` function, and the run is treated as a successful end of the sync. A checkpoint after that point doesn't run.
- After the limit is reached, new `@action` calls also stop.
- `N` is saved as `capped_count` in the first line of `fixture.jsonl`. A replay applies the same limit, so it stops at the same write as the recording. You can't pass `--max-records` to `--replay`.
- The limit works by raising an exception inside the write operation. If your code wraps a write in `except Exception`, it can catch the exception, but every later write is still rejected.

## Commit recordings to Git
Commit the `fixtures` folder with your connector so that you and your team can replay the recordings later. Before you push it to Git, check the recorded data for personal data (PII) and other sensitive values. A replay creates a `.fixtures_replay` folder, which is replaced every time a replay runs to compare its output with the recorded data, so add it to your `.gitignore` file and don't commit it.

## Configuration file
No configuration file values are required for this example. The `configuration.json` file contains an empty object.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The API Playground does not require authentication.


## Pagination
The connector uses page-number pagination. It requests `page=1`, `page=2`, and so on, until the last page is reached or a page has no data. The API returns customers sorted by `updatedAt`, oldest first, and accepts an inclusive `updated_since` filter. The connector saves the newest `updatedAt` it has synced as `last_updated_at` in state, and checkpoints after each fully processed page. The next sync sends `updated_since=<last_updated_at>` and starts again at page 1 of that filtered query, so it reads only new and changed customers. 
This works when customers don't change while a sync is running. Page-number pagination can't guarantee that for live data, because a customer that changes between page requests can move to a page you've already read. For a source that changes during a sync, use cursor-based (keyset) pagination instead. The first sync has no state and reads all customers. Because the filter is inclusive, the newest customer is read again on every sync, which is harmless for an upsert.


## Data handling
- The `update()` function upserts each customer into the `CUSTOMER` table.
- The recorded `@action` results must be JSON-serializable, so the function returns the parsed JSON response.
- Each recording holds the `customers_page` calls, one per page.


## Error handling
- The `get_with_retry()` helper retries transient failures, which are timeouts, connection errors, and HTTP 429, 500, 502, 503, and 504 responses. It makes up to three attempts with exponential backoff (2 seconds, then 4 seconds) and logs each retry.
- Other HTTP errors, such as 400 or 404, raise immediately through `response.raise_for_status()` because retrying can't fix them.
- Both `@action` functions call the helper, so retries happen only during a live run or `--record`. A replay returns the recorded result and never makes a request.
- A replay fails with a message to record the scenario again if the connector makes an `@action` call that isn't in the recording.


## Tables created
The connector creates a `CUSTOMER` table:

```json
{
  "table": "customer",
  "primary_key": ["id"]
}
```


## Additional considerations
The example provided is intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using this example. For inquiries, please reach out to our Support team.
