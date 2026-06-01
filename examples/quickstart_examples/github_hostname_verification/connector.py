# This is an example for how to work with the fivetran_connector_sdk module.
# It sends requests to a local bridge IP while verifying the TLS certificate
# against the real source hostname (api.github.com).
# Fivetran's infrastructure routes the traffic from the bridge to the actual source.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import http.client
import json
import os
import socket
import ssl

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
            "table": "api_endpoints",
            "primary_key": ["name"],
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
    log.warning("Example: QuickStart Examples - GitHub (raw socket, full TLS verification)")

    # Original source hostname from configuration — used for TLS verification
    original_host = configuration.get("host", "api.github.com")
    original_port = configuration.get("port", "443")

    # Local bridge IP and port — requests are sent here.
    # Fivetran's infrastructure routes traffic from the bridge to the actual source.
    proxy_host = os.getenv("PROXY_HOST", "api.github.com")
    proxy_port = int(os.getenv("PROXY_PORT", "443"))

    log.info(f"Original source hostname: {original_host}")
    log.info(f"Connecting network socket to: {proxy_host}:{proxy_port}")

    try:
        # Create TCP socket to the local bridge IP
        raw_socket = socket.create_connection((proxy_host, proxy_port), timeout=10)

        # Wrap with TLS — server_hostname ensures certificate is verified against
        # api.github.com even though the TCP connection is to the bridge IP
        ssl_context = ssl.create_default_context()
        tls_socket = ssl_context.wrap_socket(raw_socket, server_hostname=original_host)
        log.info("TLS handshake succeeded")

        # Use http.client on top of the TLS socket to make the HTTP request
        conn = http.client.HTTPConnection(proxy_host)
        conn.sock = tls_socket
        # User-Agent is required by GitHub API — without it the server returns a non-JSON error response
        conn.request("GET", "/", headers={"Host": original_host, "User-Agent": "FivetranConnector"})
        response = conn.getresponse()
        log.info(f"Response status: {response.status}")

        raw_body = response.read().decode("utf-8")
        conn.close()

        if response.status != 200:
            raise RuntimeError(f"Unexpected response status {response.status}: {raw_body[:200]}")

        body = json.loads(raw_body)

        for name, url in body.items():
            op.upsert(table="api_endpoints", data={"name": name, "url": url})

        log.info(f"Upserted {len(body)} API endpoints")

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
