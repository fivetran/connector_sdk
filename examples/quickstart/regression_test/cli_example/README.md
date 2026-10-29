# Regression Test Example: Command Line

## Connector overview
This example records and replays a connector run with the `fivetran debug` command. The connector reads sample customer records (`id`, `name`, `email`, `address`, `company`, `job`, `createdAt`, and `updatedAt`) from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/), a local mock API that serves generated test data, and upserts them into the `customer` table.

For the record and replay concepts, refer to the [Regression Testing documentation](https://fivetran.com/docs/connector-sdk/testing/regression-testing) and the [regression test examples README](https://github.com/fivetran/connector_sdk/blob/main/examples/quickstart/regression_test/README.md).

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

To initialize a new Connector SDK project using this example as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/regression_test/cli_example
```

For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

### Run the example
1. Start the API Playground in a separate terminal:

   ```bash
   pip install fivetran-api-playground
   playground start
   ```

2. From this folder, record a scenario named `basic`. The recording stops after 100 write operations (`op.upsert`, `op.update`, and `op.delete` calls) by default:

   ```bash
   fivetran debug --record basic
   ```

   To stop after a different number of write operations, add `--max-records <N>`. For example, `--max-records 25` stops after 25 write operations. The first `N` writes go through and the next one ends the sync successfully. The limit is saved in the fixture.

   The run logs `recorded <N> interaction(s)` and saves the recording in `fixtures/basic/`. If `basic` already exists, the command asks before it overwrites it. Add `--yes` to overwrite without asking.

3. Replay the scenario:

   ```bash
   fivetran debug --replay basic
   ```

   The replay doesn't call the source. It reads the interactions from the fixture that the record run generated and returns them to the connector. When the replay finishes, it compares the resulting state and `warehouse.db` with the recorded ones:

   - If they match, so there is no regression, the run logs `replay finished and its state and warehouse.db match the recording`.
   - If they don't match, the run prints each mismatch and exits with code 1.

4. Change the connector, for example rename a field before the `op.upsert()` call, and replay again. The replay fails and lists the rows and columns that changed. If the change is intended, record the scenario again.


### Options

| Option | Description |
|--------|-------------|
| `--record <scenario>` | Records the run into `fixtures/<scenario>/`. |
| `--max-records <N>` | Stops the recording after `N` write operations (`op.upsert`, `op.update`, and `op.delete`). The default is 100. Use only with `--record`. |
| `--replay <scenario>` | Replays the scenario and compares the output with the recording. |
| `--yes` | Overwrites an existing recording without asking. |
| `--non-interactive` | Keeps an existing recording and records nothing, instead of asking. |

You can't use `--record` and `--replay` together, or `--max-records` with `--replay`. A replay applies the limit saved in the recording.


## Features
- Marks the function that reads from the source with the `@action` decorator.
- Records the `@action` calls, the starting state, and the output of a run with `--record`.
- Limits the size of a recording with `--max-records`.
- Replays a recording with `--replay`, which doesn't call the source.
- Compares the replay `state.json` and `warehouse.db` with the recorded ones to detect regressions.
- Uses `match` to identify a call by `page` and `updated_since` only.


## Configuration file
No configuration file values are required for this example. The `configuration.json` file contains an empty object.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
This connector does not require any Python dependencies.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The API Playground does not require authentication.


## Pagination
The connector uses page-number pagination. It requests customers sorted by `updatedAt`, oldest first, with `page=1`, `page=2`, and so on, until a page has no data. It checkpoints the newest `updatedAt` after each page, and the next sync sends it as `updated_since`. This assumes customers don't change while a sync runs. For a source that changes during a sync, use cursor-based (keyset) pagination instead.


## Data handling
- The `update()` function upserts each customer into the `customer` table.
- The recorded `@action` results must be JSON-serializable, so the function returns the parsed JSON response.
- Each recording holds the `customers_page` calls, one per page.


## Error handling
- The `get_with_retry()` helper retries timeouts, connection errors, and HTTP 429, 500, 502, 503, and 504 responses, with up to three attempts and exponential backoff.
- Other HTTP errors, such as 400 or 404, raise immediately.
- A replay fails with a message to record the scenario again if the connector makes an `@action` call that isn't in the recording.


## Tables created
The connector creates a `customer` table:

```json
{
  "table": "customer",
  "primary_key": ["id"]
}
```


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
