# This is an example for how to work with the fivetran_connector_sdk module.
# It fetches data from the GitHub API (api.github.com) using urllib.request from the
# Python standard library, which accepts an ssl.SSLContext directly — no custom adapter needed.
# This validates the certificate chain but disables only hostname verification,
# which is simpler than the requests-based approach in connector.py.
# The certificate being validated is the SOURCE's certificate (api.github.com), not the proxy's.
# ssl.create_default_context() already trusts it via the system CA bundle — no custom CA needed.
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

import json
import os
import ssl
import urllib.request

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
    log.warning("Example: QuickStart Examples - GitHub (urllib, cert verified, hostname verification disabled)")

    # Original source values from configuration
    original_host = configuration.get("host", "api.github.com")
    original_port = configuration.get("port", "443")

    # Proxy/local routing values from environment variables
    proxy_host = os.getenv("PROXY_HOST", "172.17.0.1")
    proxy_port = os.getenv("PROXY_PORT", "8072")

    log.info(f"Original source from configuration: {original_host}:{original_port}")
    log.info(f"Connecting via: {proxy_host}:{proxy_port}")
    log.info("Certificate chain will be validated. Hostname verification is disabled.")

    # skip hostname matching only; cert chain validation remains on by default
    ctx = ssl.create_default_context()
    ctx.check_hostname = False

    url = f"https://{proxy_host}:{proxy_port}"
    log.info(f"Calling URL: {url}")

    try:
        with urllib.request.urlopen(url, context=ctx, timeout=10) as response:
            status = response.status
            body = response.read().decode("utf-8")

        log.info(f"Response status: {status}")

        op.upsert(
            table="api_response",
            data={
                "host": original_host,
                "proxy_host": proxy_host,
                "proxy_port": proxy_port,
                "status": str(status),
                "response": body[:500],
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
