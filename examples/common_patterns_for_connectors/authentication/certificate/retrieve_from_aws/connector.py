"""
This is an example of a Fivetran connector that demonstrates how to retrieve certificates from AWS S3 and use them for authentication.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# Import required for SSL context
import ssl

# Import required for temporary file operations
import tempfile

# Import required for making HTTP requests
import urllib.request

# Import required for JSON operations
import json

# Import required for file operations
import os

# Import required for regular expression operations
import re

# Import the S3Client class from the aws_client module to interact with AWS S3
from aws_client import S3Client

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__BASE_URL = "https://client.badssl.com/"
__CHECKPOINT_INTERVAL = 5


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


def get_urllib_context(cert_path: str, passkey: str):
    """
    Get an SSL context for urllib with the given certificate and key.
    Args:
        cert_path: temporary certificate file path
        passkey: password for the private key
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.load_cert_chain(certfile=cert_path, password=passkey)
    return context


def get_s3_client(configuration: dict, bucket_name: str):
    """
    Get an S3 client using the provided configuration.
    This method initializes the S3 client with credentials and probes the S3 bucket
    This ensures that the credentials and permissions are valid and the bucket is accessible.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector
        bucket_name: name of the S3 bucket
    Returns:
        An instance of the S3Client class initialized with the provided AWS credentials and region.
    """
    aws_access_key_id = configuration["AWS_ACCESS_KEY_ID"]
    aws_secret_access_key = configuration["AWS_ACCESS_SECRET_KEY"]
    region = configuration["REGION"]

    client = S3Client(aws_access_key_id, aws_secret_access_key, region)
    # Probe the S3 bucket to ensure that the provided credentials are valid and the bucket is accessible
    client.probe(bucket_name=bucket_name)
    return client


def get_certificates(client, bucket_name, object_key):
    """
    Get the certificates from the cloud storage.
    Args:
        client: AWS S3 client object
        bucket_name: name of the S3 bucket where the certificate is stored
        object_key: key of the certificate object in the S3 bucket
    """
    try:
        log.info("Fetching certificates from cloud")

        content = client.get_object(bucket_name, object_key)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as temp_cert_file:
            temp_cert_file.write(content)
            cert_path = temp_cert_file.name
        return cert_path
    except Exception as e:
        raise RuntimeError(f"Could not fetch the certificates from cloud: {str(e)}")


def get_data_with_certificate(base_url: str, cert_path: str, passkey: str):
    """
    Get the data from the API using the certificate.
    Args:
        base_url: base URL of the API
        cert_path: certificate file path
        passkey: password for the private key
    """
    try:
        log.info(f"Fetching data from {base_url}")
        context = get_urllib_context(cert_path, passkey)
        with urllib.request.urlopen(base_url, context=context) as response:
            content = response.read()

        content = re.sub(r"<[^>]+>", "", content.decode("utf-8"))
        content = [line.strip() for line in content.splitlines() if line.strip()]
        return content

    except Exception as exception:
        raise ConnectionError(f"Failed to get data from {base_url}: {exception}")
    finally:
        log.info("Deleting downloaded certificate files")
        if cert_path:
            os.unlink(cert_path)


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
    required_configs = [
        "AWS_ACCESS_KEY_ID",
        "AWS_ACCESS_SECRET_KEY",
        "PASSKEY",
        "BUCKET_NAME",
        "OBJECT_KEY",
        "REGION",
    ]
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
    log.warning(
        "Example: Common patterns for connectors - Using certificates for API authentication"
    )

    last_index = state["last_index"] if "last_index" in state else -1

    validate_configuration(configuration)

    bucket_name = configuration["BUCKET_NAME"]
    object_key = configuration["OBJECT_KEY"]

    s3_client = get_s3_client(configuration=configuration, bucket_name=bucket_name)
    cert_path = get_certificates(client=s3_client, bucket_name=bucket_name, object_key=object_key)
    passkey = configuration["PASSKEY"]

    data = get_data_with_certificate(base_url=__BASE_URL, cert_path=cert_path, passkey=passkey)
    if not data:
        raise RuntimeError("No data received")

    for value in data:
        last_index += 1
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="sample_data", data={"id": last_index, "content": value})
        if last_index % __CHECKPOINT_INTERVAL == 0:
            # checkpoint after every __CHECKPOINT_INTERVAL records
            op.checkpoint({"last_index": last_index})

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint({"last_index": last_index})  # checkpoint after all records are processed


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents into a dictionary.
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
