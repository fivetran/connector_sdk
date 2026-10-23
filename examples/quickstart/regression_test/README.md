# Regression Test Connector Examples

## Connector overview
These examples show how to use record and replay regression testing with the Fivetran Connector SDK. You record a connector run against a live source once, and then replay the recording without calling the source to confirm that code changes don't alter the data your connector delivers.

Both examples read customers from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/) with page-number pagination. They differ only in how you start the record and replay runs:

| Example | How you run it |
|---------|----------------|
| [`cli_example`](cli_example) | With the `fivetran debug --record` and `fivetran debug --replay` commands. |
| [`ide_example`](ide_example) | From an IDE or a script, by passing `record=` and `replay=` to `connector.debug()`. |

Regression testing is in Private Preview.


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
- Marks the source calls with the `@action` decorator so they can be recorded and replayed.
- Shows both forms of `@action`: with and without `match`.
- Limits the size of a recording with `max_records` and `--max-records`.
- Compares the replay `state.json` and `warehouse.db` with the recorded files.


## Using `@action` with and without `match`
During a replay, the connector finds the recorded result of a call by the `@action` name and the call's arguments. `match` controls which arguments count. The examples use both forms:

| Function | Decorator | What identifies the call |
|----------|-----------|--------------------------|
| `fetch_customers_page(page)` | `@action("customers_page", match=lambda page: {"page": page})` | Only `page`. |
| `fetch_total_pages(per_page)` | `@action("customers_total_pages")` | All arguments, which is `per_page`. |

**Without `match`**, every argument is part of the call identity. This is the simplest form. Use it when all arguments have the same values on every run, as `per_page` does here. If an argument changes on every run, such as a timestamp or a request ID, the replay can't find the recorded call and fails.

**With `match`**, you return a dictionary of only the arguments that identify the call. `match` must accept the same arguments as the decorated function and return a dictionary. Use it to leave out arguments that change on every run or that you don't want in the recording, such as a secret. In this example, the page number is enough to identify a page, so `match` returns `{"page": page}`.

For example, if `fetch_customers_page` also took a `request_id` that changes on every run, `match=lambda page, request_id: {"page": page}` ignores it, and the replay still finds the recorded page.

`match` doesn't work with functions that accept `*args` or `**kwargs`. The arguments and results must be JSON-serializable. Arguments whose names end in `token`, `secret`, `password`, `api_key`, `credential` or `configuration` are saved as a hash instead of their value.


## How regression testing works
1. `@action` marks the function that reads from the source.
2. A record run calls the source and saves every `@action` call, the starting state, and the output in `fixtures/<scenario>/`.
3. A replay run starts from the recorded state. Each `@action` call returns the recorded result, and the source isn't called.
4. The replay `state.json` and `warehouse.db` are compared with the recorded ones. A difference fails the run and lists what changed.

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
The connector uses page-number pagination. It requests `page=1`, `page=2`, and so on, until a page has no data or the last page is reached. The last synced page is saved in the state, so the next sync resumes after it.


## Data handling
- The `update()` function upserts each customer into the `customer` table.
- The recorded `@action` results must be JSON-serializable, so the functions return the parsed JSON response or a plain number.
- Each recording holds the `customers_page` calls, one per page, and one `customers_total_pages` call.


## Error handling
- `response.raise_for_status()` raises an exception for an HTTP error response.
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
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
