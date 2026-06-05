import json
import socket

import psycopg2

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op


def schema(configuration: dict):
    return [
        {
            "table": "test",
            "primary_key": ["id"],
        }
    ]


def update(configuration: dict, state: dict):

    host = configuration["host"]
    port = int(configuration["port"])
    database = configuration["database"]
    user = configuration["user"]
    password = configuration["password"]

    log.info(f"Attempting connection to {host}:{port}")

    try:
        resolved = socket.getaddrinfo(
            host,
            port,
            proto=socket.IPPROTO_TCP
        )

        resolved_ips = sorted(
            {entry[4][0] for entry in resolved}
        )

        log.warning(
            f"Python DNS resolved {host} to: {resolved_ips}"
        )

    except Exception as e:
        log.warning(f"DNS resolution failed: {e}")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            connect_timeout=10
        )

        log.info("Successfully connected to PostgreSQL")

        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM test")
        rows = cursor.fetchall()
        log.info(f"Fetched {len(rows)} rows from test table")

        for row in rows:
            op.upsert(
                table="test",
                data={
                    "id": row[0],
                    "name": row[1],
                },
            )

        cursor.close()
        conn.close()

    except Exception as e:
        log.error(f"Connection failed: {e}")
        raise

    op.checkpoint(state)


connector = Connector(update=update, schema=schema)


if __name__ == "__main__":
    try:
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        configuration = {}

    connector.debug(configuration=configuration)