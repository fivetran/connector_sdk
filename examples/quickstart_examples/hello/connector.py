"""
gRPC Benchmark Connector - Baseline (Standard SDK Operations)

Uses standard SDK Operations for type inference.
Start with: python connector.py
Connect with Java tester on port 50051.
"""
import os
from datetime import datetime

from fivetran_connector_sdk import Connector, Operations as op, Logging as log

NUM_RECORDS = int(os.environ.get("NUM_RECORDS", "10000"))
STR_COL_SIZE = int(os.environ.get("STR_COL_SIZE", "220"))

# Schema: 4 string + 2 int + 2 float + 2 bool = 10 columns, ~1 KB per row
_STR_COLS = ["str_col_0", "str_col_1", "str_col_2", "str_col_3"]
_INT_COLS = ["int_col_0", "int_col_1"]
_FLOAT_COLS = ["float_col_0", "float_col_1"]
_BOOL_COLS = ["bool_col_0", "bool_col_1"]

_BYTES_PER_RECORD = (
    len("id") + len(str(NUM_RECORDS - 1))
    + sum(len(c) for c in _STR_COLS) + len(_STR_COLS) * STR_COL_SIZE
    + sum(len(c) for c in _INT_COLS) + len(_INT_COLS) * 8
    + sum(len(c) for c in _FLOAT_COLS) + len(_FLOAT_COLS) * 8
    + sum(len(c) for c in _BOOL_COLS) + len(_BOOL_COLS) * 5
)


def update(configuration: dict, state: dict):
    start_time = datetime.now()
    log.info(f"Sending {NUM_RECORDS} records...")

    for i in range(NUM_RECORDS):
        str_val = f"value_{i}".ljust(STR_COL_SIZE, '0')
        op.upsert("benchmark_data", {
            "id": i,
            "str_col_0": str_val,
            "str_col_1": str_val,
            "str_col_2": str_val,
            "str_col_3": str_val,
            "int_col_0": i * 1000,
            "int_col_1": i * 7,
            "float_col_0": i * 3.14,
            "float_col_1": i * 1.41,
            "bool_col_0": i % 2 == 0,
            "bool_col_1": i % 3 == 0,
        })

    op.checkpoint(state={})

    time_diff_sec = (datetime.now() - start_time).total_seconds()
    overall_data_sent_mbs = (NUM_RECORDS * _BYTES_PER_RECORD) / (1024 * 1024)
    throughput = overall_data_sent_mbs / time_diff_sec if time_diff_sec > 0 else 0
    latency_per_row_ms = time_diff_sec / NUM_RECORDS * 1_000 if NUM_RECORDS > 0 else 0

    log.info(f"Total records upserted: {NUM_RECORDS}")
    log.info(f"Time taken in seconds: {time_diff_sec}")
    log.info(f"Overall data sent (in mb): {overall_data_sent_mbs}")
    log.info(f"Throughput (MB/s): {throughput}")
    log.info(f"Latency per row (millis): {latency_per_row_ms}")
    log.info("Benchmark complete.")


connector = Connector(update=update)

if __name__ == "__main__":
    print("Starting gRPC server on port 50051...")
    print("Connect with Java tester: java -jar sdk-grpc/java_tester/build/libs/java_tester.jar")
    connector.run(port=50051, configuration={}, state={})