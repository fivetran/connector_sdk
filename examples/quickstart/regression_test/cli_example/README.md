# Regression Test Example: Command Line

## Connector overview
This example records and replays a connector run with the `fivetran debug` command. The connector reads customers from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/) and upserts them into the `customer` table.

For the concepts, requirements, and data handling, refer to the [parent README](../README.md).


## Run the example
1. Start the API Playground in a separate terminal:

   ```bash
   pip install fivetran-api-playground
   playground start
   ```

2. From this folder, record a scenario named `basic` and stop after 25 write operations:

   ```bash
   fivetran debug --record basic --max-records 25
   ```

   The run logs `recorded <N> interaction(s)` and saves the recording in `fixtures/basic/`. If `basic` already exists, the command asks before it overwrites it. Add `--yes` to overwrite without asking.

3. Replay the scenario:

   ```bash
   fivetran debug --replay basic
   ```

   The run logs `replay finished and its state and warehouse.db match the recording`. The source isn't called.

4. Change the connector, for example rename a field before the `op.upsert()` call, and replay again. The replay fails and lists the rows and columns that changed. If the change is intended, record the scenario again.


## Options

| Option | Description |
|--------|-------------|
| `--record <scenario>` | Records the run into `fixtures/<scenario>/`. |
| `--max-records <N>` | Stops the recording after `N` write operations. The default is 100. Use only with `--record`. |
| `--replay <scenario>` | Replays the scenario and compares the output with the recording. |
| `--yes` | Overwrites an existing recording without asking. |
| `--non-interactive` | Keeps an existing recording and records nothing, instead of asking. |

You can't use `--record` and `--replay` together, or `--max-records` with `--replay`. A replay applies the limit saved in the recording.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
