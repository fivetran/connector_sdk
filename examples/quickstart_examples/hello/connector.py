"""
gRPC Benchmark Connector - Baseline (Standard SDK Operations)

Uses standard SDK Operations for type inference.
Start with: python connector.py
Connect with Java tester on port 50051.
"""
import os
import random
import string
from datetime import datetime

from fivetran_connector_sdk import Connector, Operations as op, Logging as log

NUM_RECORDS = int(os.environ.get("NUM_RECORDS", "10000"))
NUM_COLUMNS = int(os.environ.get("NUM_COLUMNS", "10"))
FIELD_SIZE = int(os.environ.get("FIELD_SIZE", "100"))

_CHARSET = string.ascii_letters + string.digits
_COL_NAMES = [f"col_{i}" for i in range(NUM_COLUMNS)]
_COL_KEYS_SIZE = sum(len(n) for n in _COL_NAMES)
_BYTES_PER_RECORD = len("id") + 16 + _COL_KEYS_SIZE + NUM_COLUMNS * FIELD_SIZE


def gen_record():
    record = {"id": ''.join(random.choices(_CHARSET, k=16))}
    for name in _COL_NAMES:
        record[name] = ''.join(random.choices(_CHARSET, k=FIELD_SIZE))
    return record


def update(configuration: dict, state: dict):
    start_time = datetime.now()
    log.info(f"Sending {NUM_RECORDS} records...")

    for _ in range(NUM_RECORDS):
        op.upsert("benchmark_data", gen_record())

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