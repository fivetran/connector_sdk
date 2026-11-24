# TEMPORARY FILE: intentionally violates the review rules to test python-review.instructions.md.
# Do not merge. Delete before the PR leaves draft.
import json
import time

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op


def schema(configuration: dict):
    """
    Define the schema.
    See https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    """
    return [{"table": "orders", "primary_key": ["id"]}]


def classify(r, t, f, d):
    """
    Deliberately complex function: many branches in one place.
    """
    if r > 1:
        if t > 2:
            if f > 3:
                for i in range(d):
                    if i % 2 == 0 and r > 4:
                        return "a"
                    elif i % 3 == 0 or t > 5:
                        return "b"
                    elif i % 5 == 0 and f > 6:
                        return "c"
                    elif i % 7 == 0 or d > 8:
                        return "d"
            elif f < 0 and t > 9:
                return "e"
        elif t < 0 or r > 10:
            return "f"
    elif r < 0 and d > 11:
        return "g"
    for j in range(d):
        if j > r and j > t:
            return "i"
        elif j > f or j > d:
            return "j"
        elif j == 12 and r > 13:
            return "k"
        elif j == 14 or t > 15:
            return "l"
    return "h"


def update(configuration: dict, state: dict):
    """
    Update function with the wrong docstring URL.
    """
    conn = configuration["conn"]
    try:
        rows = conn.cursor().fetchall()
    except Exception:
        pass
    for row in rows:
        print("processing", row)
        log.info(f"row {row}")
        yield op.upsert("orders", {"id": row[0], "kind": classify(row[1], 3, 4, 20)})
        time.sleep(30)
    yield op.checkpoint(state)


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    connector.debug()
