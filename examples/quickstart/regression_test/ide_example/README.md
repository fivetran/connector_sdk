# Regression Test Example: IDE

## Connector overview
This example records and replays a connector run from an IDE or a script, without the `fivetran` command. The connector reads customers from the [Fivetran API Playground](https://pypi.org/project/fivetran-api-playground/) and upserts them into the `customer` table.

For the record and replay concepts, requirements, and data handling, refer to the [parent README](../README.md).


## Run the example
1. Start the API Playground in a separate terminal:

   ```bash
   pip install fivetran-api-playground
   playground start
   ```

2. Open `connector.py` in your IDE. In the `__main__` block, `MODE` is set to `"record"`. Run the file. It records the scenario `basic` into `fixtures/basic/` and stops after 50 write operations.

3. Set `MODE` to `"replay"` and run the file again. The replay doesn't call the source. It reads the interactions from the fixture that the record run generated and returns them to the connector. When the replay finishes, it compares the resulting state and `warehouse.db` with the recorded ones:

   - If they match, so there is no regression, the run logs `replay finished and its state and warehouse.db match the recording`.
   - If they don't match, the run prints each mismatch and exits with code 1.

4. Change the connector, for example rename a field before the `op.upsert()` call, and replay again. The replay fails and lists the rows and columns that changed. If the change is intended, set `MODE` back to `"record"` and record the scenario again.

You can also run the file from a terminal with `python connector.py`.


## Arguments

The example passes the same options as the command line to `connector.debug()`:

| `debug()` argument | Command-line option | Description |
|--------------------|---------------------|-------------|
| `record="<scenario>"` | `--record <scenario>` | Records the run into `fixtures/<scenario>/`. |
| `max_records=<N>` | `--max-records <N>` | Stops the recording after `N` write operations (`op.upsert`, `op.update`, and `op.delete`). The default is 100. Use only with `record`. |
| `replay="<scenario>"` | `--replay <scenario>` | Replays the scenario and compares the output with the recording. |

You can't combine `record` and `replay`, or use `max_records` with `replay`. If a replay doesn't match, `debug()` logs the differences and exits with code 1. Recording over an existing scenario asks for confirmation, so run the file from a terminal to answer it.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
