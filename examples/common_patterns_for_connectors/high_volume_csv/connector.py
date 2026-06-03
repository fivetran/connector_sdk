"""
This connector example demonstrates common patterns for handling high-volume CSV data ingestion.
It includes techniques for efficient reading and processing of large CSV files using libraries like Dask, Polars, and Pandas with PyArrow.
We recommend to use Polars for high-volume CSV processing due to its performance and low memory usage.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For handling time delays during retries
import time

# For file system operations
import os

# For making HTTP requests
import requests

# For creating temporary files
import tempfile

# For type hinting
from typing import Optional, Dict

# For processing high volume CSV files
import dask.dataframe as dd
import polars as pl
import pandas as pd

__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__INITIAL_RETRY_DELAY = 1  # Initial delay in seconds for retries
__MAX_RETRY_DELAY = 16  # Maximum delay in seconds between retries
__PYARROW_STRING_DATA_TYPE = "string[pyarrow]"
__DASK_BLOCK_SIZE = "128MB"


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
    required_configs = ["api_url", "api_key"]
    missing = [key for key in required_configs if key not in configuration]
    if missing:
        raise ValueError(f"Missing required configuration value(s): {', '.join(missing)}")


def get_auth_headers(configuration: dict):
    """
    This is the function to generate authentication headers for making API calls.
    You can modify this function based on the authentication mechanism of the API you are connecting to.
    Args:
        configuration: dictionary contains any secrets or payloads you configure when deploying the connector.
    Returns:
        headers: A dictionary containing the Authorization header with the API key.
    """
    api_key = configuration.get("api_key")

    # Create the auth string
    headers = {
        "Authorization": f"apiKey {api_key}",
    }
    return headers


def should_retry_request(exception: Exception) -> bool:
    """
    Determine if a request should be retried based on the exception.
    Args:
        exception (Exception): The exception raised during request
    Returns:
        bool: True if request should be retried, False otherwise
    """
    if not isinstance(exception, requests.exceptions.RequestException):
        return False

    if isinstance(exception, requests.exceptions.ConnectionError):
        return True

    if isinstance(exception, requests.exceptions.Timeout):
        return True

    if isinstance(exception, requests.exceptions.HTTPError):
        status_code = exception.response.status_code if exception.response else None
        return status_code in [429, 500, 502, 503, 504]

    return False


def calculate_retry_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay for retry attempts.
    Args:
        attempt (int): Current retry attempt number (0-based)
    Returns:
        float: Delay in seconds (capped at __MAX_RETRY_DELAY)
    """
    delay = __INITIAL_RETRY_DELAY * (2**attempt)
    return min(delay, __MAX_RETRY_DELAY)


def make_api_request_with_retry(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """
    Make an API request with retry logic and exponential backoff.
    You can modify this function based on the specific requirements of your API requests.
    Args:
        url (str): URL to request
        headers (Optional[Dict[str, str]]): HTTP headers
    Returns:
        str: file path to the saved CSV content
    Raises:
        requests.exceptions.RequestException: If all retry attempts fail
    """
    last_exception = None

    for attempt in range(__MAX_RETRIES):
        try:
            with requests.get(url, headers=headers, stream=True) as response:
                response.raise_for_status()
                temp_file_path = save_csv_locally(response)
                return temp_file_path

        except Exception as e:
            last_exception = e

            if not should_retry_request(e):
                raise

            if attempt < __MAX_RETRIES - 1:
                delay = calculate_retry_delay(attempt)
                log.warning(
                    f"Request failed (attempt {attempt + 1}/{__MAX_RETRIES}): {e}. Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                log.error(f"Request failed after {__MAX_RETRIES} attempts")

    raise last_exception


def save_csv_locally(response) -> str:
    """
    Save CSV content received from API to a file for further processing.
    Args:
        response : Response object from the API request
    Returns:
        str: Path to the saved CSV file
    """
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".csv", mode="w", encoding="utf-8"
    ) as temp_file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_file_path = temp_file.name

    return temp_file_path


def delete_file(file_path: str):
    """
    Delete a file.
    Args:
        file_path (str): Path to the file to be deleted
    """
    try:
        os.remove(file_path)
        log.info(f"Deleted file: {file_path}")
    except OSError as e:
        log.warning(f"Error deleting file {file_path}: {e}")


def upsert_with_dask(csv_path: str, table_name: str, state):
    """
    Upsert using Dask, one row at a time, in a scalable way.
    Args:
        csv_path: Path to the CSV file
        table_name: Name of the target table
        state: State dictionary for checkpointing
    """
    dataframe = dd.read_csv(
        csv_path,
        blocksize=__DASK_BLOCK_SIZE,  # This can be altered based on your data. Adjust for optimal partition size.
        dtype={  # It is suggested to define the columns and datatypes to avoid dtype inference overhead. This makes the read faster.
            "has_id": "object",
            "name": "object",
            "city": "object",
            "created_at": "object",
        },
        usecols=["has_id", "name", "city", "created_at"],  # Read only necessary columns
        assume_missing=True,  # This avoids unnecessary type upcasting and dtype churn. You can remove this if your data is clean.
    )

    for part_index in range(dataframe.npartitions):
        part_df = dataframe.get_partition(part_index).compute()

        # Skip empty partitions (if any)
        if part_df.empty:
            continue

        # Upsert each row in the partition. Using itertuples for efficient row iteration.
        for row in part_df.itertuples(index=False):
            record = row._asdict()  # Convert namedtuple to dictionary for upserting
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table=table_name, data=record)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def upsert_with_polars(csv_path: str, table_name: str, state):
    """
    Upsert using Polars, one row at a time, in a scalable way.
    It is recommended to use Polars for high-volume CSV processing due to its performance and low memory usage.
    Args:
        csv_path: Path to the CSV file
        table_name: Name of the target table
        state: State dictionary for checkpointing
    """
    # Batched reading of the CSV files for better performance and low memory usage
    # For moderate to small data volumes, you can read the CSV using pl.read_csv() directly without batching for better performance.
    csv_reader = pl.read_csv_batched(
        csv_path,
        has_header=True,
        columns=["has_id", "name", "city", "created_at"],
        low_memory=True,
    )

    while True:
        # Read the next batch
        batches = csv_reader.next_batches(1)

        if not batches:
            # No more batches to process. Exit the loop.
            break

        batch_dataframe = batches[0]

        # Upsert each row in the batch
        for row in batch_dataframe.iter_rows(named=True):
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The op.upsert method is called with two arguments:
            # - The first argument is the name of the table to upsert the data into.
            # - The second argument is a dictionary containing the data to be upserted
            op.upsert(table=table_name, data=row)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


def upsert_with_pandas_pyarrow(csv_path: str, table_name: str, state):
    """
    Upsert using Pandas with PyArrow engine, one row at a time.
    Args:
        csv_path: Path to the CSV file
        table_name: Name of the target table
        state: State dictionary for checkpointing
    """
    dataframe = pd.read_csv(
        csv_path,
        engine="pyarrow",  # Using pyarrow engine for better performance on large CSVs
        usecols=["has_id", "name", "city", "created_at"],  # Read only necessary columns
        dtype={  # It is suggested to define the columns and datatypes to avoid dtype inference overhead. This makes the read faster.
            "has_id": __PYARROW_STRING_DATA_TYPE,
            "name": __PYARROW_STRING_DATA_TYPE,
            "city": __PYARROW_STRING_DATA_TYPE,
            "created_at": __PYARROW_STRING_DATA_TYPE,
        },
    )

    # Upsert each row in the DataFrame. Using itertuples for efficient row iteration.
    for row in dataframe.itertuples(index=False):
        # Prepare the record for upserting
        record = {
            "has_id": row.has_id,
            "name": row.name,
            "city": row.city,
            "created_at": row.created_at,
        }
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The op.upsert method is called with two arguments:
        # - The first argument is the name of the table to upsert the data into.
        # - The second argument is a dictionary containing the data to be upserted
        op.upsert(table=table_name, data=record)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


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
            "table": "table_using_dask",
            "primary_key": ["has_id"],
            "columns": {"created_at": "UTC_DATETIME"},
        },
        {
            "table": "table_using_pandas_pyarrow",
            "primary_key": ["has_id"],
            "columns": {"created_at": "UTC_DATETIME"},
        },
        {
            "table": "table_using_polars",
            "primary_key": ["has_id"],
            "columns": {"created_at": "UTC_DATETIME"},
        },
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
    log.warning("Example: Common patterns for connectors - High volume CSV")

    # validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    # Extract configuration parameters as required
    api_url = configuration.get("api_url")

    # Get authentication headers
    headers = get_auth_headers(configuration)

    # Make API request with retry logic and save the response CSV content in a file
    csv_path = make_api_request_with_retry(url=api_url, headers=headers)

    try:
        # Upsert data using Dask
        upsert_with_dask(csv_path, table_name="table_using_dask", state=state)

        # Upsert data using Pandas with PyArrow engine
        upsert_with_pandas_pyarrow(csv_path, table_name="table_using_pandas_pyarrow", state=state)

        # Upsert data using Polars
        # It is recommended to use Polars for high-volume CSV processing due to its performance and low memory usage.
        upsert_with_polars(csv_path, table_name="table_using_polars", state=state)

    except Exception as e:
        raise RuntimeError(f"Error during upsert operations: {e}")

    finally:
        # Clean up the temporary CSV file
        delete_file(csv_path)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
