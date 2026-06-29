# ***Multithreading Guidelines***
#
# Follow the points below to avoid data integrity issues and race conditions which are hard to debug.
# * Never call fivetran_connector_sdk Operations inside a multithreaded function
#   as this requires synchronising operations such as checkpoint.
#   This is hard to do and debug, so avoid it.
# * Use multithreading only to make parallel API calls and get the responses,
#   else multithreading can result in race conditions, which are hard to debug and may not throw an error.
#
# This is a simple example of how to do multithreading to make parallel API calls to improve sync performance.
from fivetran_connector_sdk import Logging as log  # For enabling Logs in your connector code
import constants
import requests
import time
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=constants.MAX_WORKERS)


# Util function to make API calls in parallel using threadPoolExecutor
def make_api_calls_in_parallel(page, fetch_page):
    futures = [executor.submit(fetch_page, p) for p in range(page, page + constants.MAX_WORKERS)]
    results = [future.result() for future in futures]
    return results


# Util function to make an API call and return a response
def fetch_data(
    endpoint,
    access_token,
    params=None,
    timeout=constants.REQUEST_TIMEOUT,
    retries=constants.RETRIES,
):
    """
    Fetch data from the Accelo API with retry logic.

    Args:
        endpoint (str): The API endpoint to fetch data from.
        access_token (str): The OAuth 2.0 access token.
        params (dict, optional): Query parameters for the API request.
        timeout (int, optional): Request timeout in seconds.
        retries (int, optional): Number of retry attempts.

    Returns:
        list: The JSON response data or None if all retries fail.
    """
    url = f"{constants.BASE_URL}/{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}

    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json().get("response", [])
        except requests.exceptions.RequestException as e:
            log.warning(
                f"Error fetching data from {endpoint} (attempt {attempt + 1}/{retries}): {str(e)}"
            )
            if attempt == retries - 1:
                log.error(f"Failed to fetch data from {endpoint} after {retries} retries")
                return None
            time.sleep(2**attempt)  # Exponential backoff
