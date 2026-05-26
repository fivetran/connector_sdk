# This is a simple example for how to work with the fivetran_connector_sdk module.
# It defines a simple `update` method, which uses python-gnupg to sign messages with a private key.
# This example upserts the signed data to a table named "signed_message".
# See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
# and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details

# Note on GPG Key Generation:
# To use this example, you'll need a GPG key pair. To generate your own GPG key pair, you can follow these guides:
# - GnuPG official documentation: https://www.gnupg.org/gph/en/manual/c14.html
# https://docs.github.com/en/authentication/managing-commit-signature-verification/generating-a-new-gpg-key
# https://www.redhat.com/en/blog/creating-gpg-keypairs

# Import required classes from fivetran_connector_sdk
# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Importing the gnupg library for GPG encryption and decryption
import gnupg
import json


def get_gpg_key(configuration: dict, gpg):
    """
    This method is used to import the private key into the GPG object.
    The private key is used to sign messages.
    The method takes the configuration dictionary and the GPG object as parameters.
    The method returns the imported key.
    You can also have multiple keys in the configuration, and you can import them all using similar logic.
    This is a simple example that imports only one key.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        gpg: the GPG object used to import the private key.
    Returns:
        The imported key object.
    """
    # Get the private key from the configuration
    # Ensure that the private key string in configuration is properly escaped as JSON string.
    # You can also import multiple keys from the configuration if needed.
    private_key = configuration.get("private_key")
    key = gpg.import_keys(private_key)
    # Check if the key was imported successfully
    if key.count == 0:
        raise RuntimeError("Failed to import the private key.")
    else:
        log.info("Successfully imported the private key.")
        return key


def sign_message(configuration, gpg, key, message):
    """
    This method is used to sign a message using the GPG object.
    The method takes the configuration dictionary, the GPG object, the key, and the message to be signed as parameters.
    The method returns the signed message.
    In case of multiple keys, you can specify which key to use for signing.
    The passphrase should correspond to the private key used for signing.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        gpg: the GPG object used to sign the message.
        key: the imported key object used for signing.
        message: the message to be signed.
    Returns:
        The signed message as a string.
    """
    # You can also have multiple passphrase in the configuration, depending on the private keys.
    # The passphrase used for signing should correspond to the private key used for signing.
    passphrase = configuration.get("passphrase")
    # Extract the key ID from the imported key and sign the message using the key ID and passphrase
    key_id = key.fingerprints[0]
    signed_message = gpg.sign(message, keyid=key_id, passphrase=passphrase)
    # return the signed message
    return signed_message.data


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
    required_configs = ["private_key", "passphrase"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")


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
            "table": "signed_message",  # Name of the table
            "primary_key": ["id"],
            "columns": {},  # Define the columns and their data types.  # For any columns whose names are not provided here, e.g. message, their data types will be inferred
        }
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: Common Pattern for Connectors Examples - GPG Private Keys")

    validate_configuration(configuration)
    # Initialize the GPG object
    # You can pass the gnupghome parameter to the GPG object if you want to use a different directory for GPG keys.
    # for example, gnupg.GPG(gnupghome="/path/to/your/custom/gnupg/home")
    # When specifying a custom gnupghome parameter:
    # 1. The directory must exist and have proper permissions (typically 700)
    # 2. GPG needs specific files and directory structure to function properly
    # 3. Custom directories must be initialized before use with proper ownership
    # If the directory is not initialized properly, GPG will throw an error.
    # When not specifying gnupghome, it defaults to ~/.gnupg which is already properly configured in the production environment.
    gpg = gnupg.GPG()
    # Load the private key from the configuration and import it into the GPG object
    key = get_gpg_key(configuration, gpg)

    # This is the message to be signed
    # You can change this to any message you want to sign
    message = "This is a test message. This will be encrypted and signed"

    # Sign the message using the GPG object and the imported key
    signed_message = sign_message(configuration, gpg, key, message)

    # Verify if the signed message is valid
    verified = gpg.verify(signed_message)
    if verified:
        log.info("The message is valid and has been verified.")
    else:
        raise RuntimeError("The message is not valid and could not be verified.")

    # The 'upsert' operation inserts the data into the destination.
    # The op.upsert method is called with two arguments:
    # - The first argument is the name of the table to upsert the data into, in this case, "signed_message".
    # - The second argument is a dictionary containing the data to be upserted,
    log.debug("upserting to table 'signed_message'")
    op.upsert(table="signed_message", data={"id": 1, "message": signed_message})

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)


# This creates the connector object that will use the update function defined in this connector.py file.
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Allows testing the connector directly
    connector.debug(configuration=configuration)
