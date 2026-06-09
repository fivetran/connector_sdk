# This is a simple example for how to work with the fivetran_connector_sdk module.
# It defines a simple `update` method, which uses certificates to make API calls.
# See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update)
# and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details

import os  # Import required for file operations
import base64  # Import required for decoding the certificate and key data
import tempfile  # Import required for creation of temporary certificate and key files
import ssl  # Import required for SSL context
import urllib.request  # Import required for making HTTP requests
import json  # Import required for JSON operations
import re

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

BASE_URL = "https://client.badssl.com/"


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": "sample_data",  # Name of the table in the destination.
            "primary_key": ["id"],  # Primary key column(s) for the table.
        }
    ]


def build_temporary_certificates(cert_data: bytes, key_data: bytes):
    """
    Build temporary certificate and key files from the given data.
    Args:
        cert_data: certificate data
        key_data: key data
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as temp_cert_file:
        temp_cert_file.write(cert_data)
        cert_path = temp_cert_file.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as temp_key_file:
        temp_key_file.write(key_data)
        key_path = temp_key_file.name

    log.info(f"Temporary certificate file: {cert_path}")
    log.info(f"Temporary key file: {key_path}")
    return cert_path, key_path


def delete_temporary_certificates(cert_path: str, key_path: str):
    """
    Delete the temporary certificate and key files.
    Args:
        cert_path: temporary certificate file path
        key_path: temporary key file path
    """
    if os.path.exists(cert_path):
        os.unlink(cert_path)

    if os.path.exists(key_path):
        os.unlink(key_path)


def get_urllib_context(cert_path: str, key_path: str, passkey: str):
    """
    Get an SSL context for urllib with the given certificate and key.
    Args:
        cert_path: temporary certificate file path
        key_path: temporary key file path
        passkey: password for the private key
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path, password=passkey)
    return context


def get_encoded_certificate_values(configuration: dict):
    """
    Get the encoded certificate, key, and passkey from the configuration.
    Args:
        configuration: connector configuration
    """
    encoded_cert = configuration["ENCODED_CERTIFICATE"]
    encoded_key = configuration["ENCODED_PRIVATE_KEY"]
    passkey = configuration["PASSKEY"]

    if not encoded_cert:
        raise ValueError("Encoded certificate not found in configuration")
    if not encoded_key:
        raise ValueError("Encoded key not found in configuration")
    if not passkey:
        raise ValueError("Passkey not found in configuration")

    return encoded_cert, encoded_key, passkey


def get_data_with_certificate(configuration: dict):
    """
    Get data from the server using the certificate and key
    Args:
        configuration: connector configuration
    """
    encoded_cert, encoded_key, passkey = get_encoded_certificate_values(configuration)
    cert_data = base64.b64decode(encoded_cert)
    key_data = base64.b64decode(encoded_key)
    cert_path, key_path = build_temporary_certificates(cert_data, key_data)

    try:
        context = get_urllib_context(cert_path, key_path, passkey)
        with urllib.request.urlopen(BASE_URL, context=context) as response:
            content = response.read()

        log.info(f"Data received from {BASE_URL}")
        content = re.sub(r"<[^>]+>", "", content.decode("utf-8"))
        content = [line.strip() for line in content.splitlines() if line.strip()]
        return content

    except Exception as exception:
        raise ConnectionError(f"Failed to get data from {BASE_URL}: {exception}")

    finally:
        delete_temporary_certificates(cert_path, key_path)
        log.info("Temporary certificate and key files deleted")


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """

    # Validate required configuration parameters
    required_configs = ["ENCODED_CERTIFICATE", "ENCODED_PRIVATE_KEY", "PASSKEY"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.info("Example: Using certificates for making API calls")

    last_index = state["last_index"] if "last_index" in state else -1

    validate_configuration(configuration)

    data = get_data_with_certificate(configuration)
    if not data:
        raise RuntimeError("No data received")

    for value in data:
        last_index += 1
        op.upsert(table="sample_data", data={"id": last_index, "content": value})
        if last_index % 5 == 0:  # checkpoint after every 5 record
            op.checkpoint({"last_index": last_index})

    op.checkpoint({"last_index": last_index})  # checkpoint after all records are processed


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)
    # Adding this code to your `connector.py` allows you to test your connector by running your file directly from your IDE.
    connector.debug(configuration=configuration)
