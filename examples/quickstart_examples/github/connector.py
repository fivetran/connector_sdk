# This is an example for how to work with the fivetran_connector_sdk module.
# It fetches data from the GitHub API (api.github.com).
# The source host and port are read from configuration, while the proxy host and port
# used for the actual connection are read from environment variables PROXY_HOST / PROXY_PORT.
# verify=False disables hostname verification so local proxy or mock-server TLS certs do not fail.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import json
import os

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
    log.warning("Example: QuickStart Examples - GitHub")

    # Original source values from configuration
    original_host = configuration.get("host", "api.github.com")
    original_port = configuration.get("port", "443")

    # Proxy/local routing values from environment variables
    proxy_host = os.getenv("PROXY_HOST", "172.17.0.1")
    proxy_port = os.getenv("PROXY_PORT", "8072")

    log.info(f"Original source from configuration: {original_host}:{original_port}")
    log.info(f"Connecting via: {proxy_host}:{proxy_port} (hostname verification disabled)")

    url = f"https://{proxy_host}:{proxy_port}"
    log.info(f"Calling URL: {url}")

    try:
        # By default, verify=True which enforces both certificate chain validation and hostname verification.
        # Setting verify=False disables both, allowing connections to local proxies or mock servers
        # whose TLS cert does not match the original source hostname (e.g. api.github.com).
        response = rq.get(url, timeout=10, verify=False)
        log.info(f"Response status: {response.status_code}")

        op.upsert(
            table="api_response",
            data={
                "host": original_host,
                "proxy_host": proxy_host,
                "proxy_port": proxy_port,
                "status": str(response.status_code),
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
