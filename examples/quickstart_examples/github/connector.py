# This is an example for how to work with the fivetran_connector_sdk module.
# It fetches data from the GitHub API (api.github.com).
# The source host and port are read from configuration, while the proxy host and port
# used for the actual connection are read from environment variables PROXY_HOST / PROXY_PORT.
# verify=False disables hostname verification so local proxy or mock-server TLS certs do not fail.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import json
import os
import socket

import requests as rq

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "api_response",
            "primary_key": ["host"],
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details (source host and port).
        state: A dictionary containing state information from previous runs.
               Empty for the first sync or any full re-sync.
    """
    original_host = configuration.get("host", "1.1.1.1")
    original_port = int(configuration.get("port", "443"))

    log.info(f"Original source from configuration: {original_host}:{original_port}")

    try:
        resolved = socket.getaddrinfo(original_host, original_port, proto=socket.IPPROTO_TCP)
        resolved_ips = sorted({entry[4][0] for entry in resolved})
        log.warning(f"Python DNS resolved {original_host} to: {resolved_ips}")
    except Exception as e:
        log.warning(f"Python DNS resolution skipped or failed for {original_host}:{original_port}: {e}")

    url = f"https://{original_host}:{original_port}"
    log.info(f"Calling URL: {url}")

    try:
        response = rq.get(url, timeout=10, verify=False)
        log.info(f"Response status: {response.status_code}")
        log.info(f"Final response URL: {response.url}")
        log.info(f"Response server header: {response.headers.get('server')}")
        log.info(f"Response content-type: {response.headers.get('content-type')}")
        log.info(f"Response first 200 chars: {response.text[:200]}")

        op.upsert(
            table="api_response",
            data={
                "host": original_host,
                "response": response.text[:500],
            },
        )

    except Exception as e:
        log.error(f"Request failed: {str(e)}")
        raise

    op.checkpoint(state)

# This creates the connector object that will use the update and schema functions defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    try:
        with open("configuration.json", "r") as f:
            configuration = json.load(f)
    except FileNotFoundError:
        configuration = {}
    connector.debug(configuration=configuration)
