# Regression Test Example: Command Line

## Connector overview
This example records and replays a connector run with the `fivetran debug` command. The connector reads customers from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/) and upserts them into the `customer` table.

For the record and replay concepts, requirements, and data handling, refer to the [parent README](../README.md).


## Run the example
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


## Options

| Option | Description |
|--------|-------------|
| `--record <scenario>` | Records the run into `fixtures/<scenario>/`. |
| `--max-records <N>` | Stops the recording after `N` write operations (`op.upsert`, `op.update`, and `op.delete`). The default is 100. Use only with `--record`. |
| `--replay <scenario>` | Replays the scenario and compares the output with the recording. |
| `--yes` | Overwrites an existing recording without asking. |
| `--non-interactive` | Keeps an existing recording and records nothing, instead of asking. |

You can't use `--record` and `--replay` together, or `--max-records` with `--replay`. A replay applies the limit saved in the recording.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
