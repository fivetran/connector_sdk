# This is an example for how to work with the fivetran_connector_sdk module.
# It sends requests to a local bridge IP while verifying the TLS certificate
# against the real source hostname (api.github.com) using urllib3.
# urllib3 allows passing a custom SSL context and assert_hostname directly —
# no raw socket or custom adapter class needed.
# Fivetran's infrastructure routes the traffic from the bridge to the actual source.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import json
import os
import ssl

import urllib3

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
    log.warning("Example: QuickStart Examples - GitHub (urllib3, full TLS verification)")

    # Original source hostname from configuration — used for TLS certificate verification
    original_host = configuration.get("host", "api.github.com")

    # Local bridge IP and port — requests are sent here.
    # Fivetran's infrastructure routes traffic from the bridge to the actual source.
    proxy_host = os.getenv("PROXY_HOST", "api.github.com")
    proxy_port = int(os.getenv("PROXY_PORT", "443"))

    log.info(f"Original source hostname: {original_host}")
    log.info(f"Connecting to: {proxy_host}:{proxy_port}")

    # Custom SSL context — loads system CA bundle to validate the source's certificate
    ssl_context = ssl.create_default_context()

    # urllib3 connects to proxy_host:proxy_port but verifies the TLS certificate
    # against original_host (api.github.com) via assert_hostname
    http = urllib3.HTTPSConnectionPool(
        host=proxy_host,
        port=proxy_port,
        ssl_context=ssl_context,
        assert_hostname=original_host,
    )

    try:
        response = http.request(
            "GET",
            "/",
            headers={"Host": original_host, "User-Agent": "FivetranConnector"},
        )
        log.info(f"Response status: {response.status}")

        if response.status != 200:
            raise RuntimeError(f"Unexpected response status {response.status}: {response.data[:200]}")

        body = json.loads(response.data.decode("utf-8"))

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
