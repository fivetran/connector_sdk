"""This connector syncs Employee, Leave Transactions, and Attendance data from greytHR API to Fivetran destination.
See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# For date manipulation and handling API date ranges
from datetime import datetime, timedelta

# For making HTTP requests to greytHR API
import requests

# For handling request delays during retries
import time

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Maximum number of retry attempts for API requests
__MAX_RETRIES = 3

# Base delay in seconds for exponential backoff retries
__BASE_DELAY_SECONDS = 2

# Maximum date range window for Leave and Attendance API calls (greytHR limit is 31 days)
__MAX_DATE_RANGE_DAYS = 31

# Page size for Employee API pagination
__EMPLOYEE_PAGE_SIZE = 100

# Timeout in seconds for HTTP requests
__REQUEST_TIMEOUT_SECONDS = 60

# Default sync start date for leave transactions and attendance data if not configured
__DEFAULT_SYNC_START_DATE = "1900-01-01"


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing.
    """
    required_configs = ["api_username", "api_password", "greythr_domain"]
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
        {"table": "employee", "primary_key": ["employeeId"]},
        {"table": "leave_transaction", "primary_key": ["id"]},
        {"table": "leave_transaction_child", "primary_key": ["id", "parent_id"]},
        {
            "table": "attendance_insight",
            "primary_key": ["employee", "sync_start_date", "sync_end_date"],
        },
        {
            "table": "attendance_average",
            "primary_key": ["employee", "sync_start_date", "sync_end_date", "type"],
        },
        {
            "table": "attendance_day",
            "primary_key": ["employee", "sync_start_date", "sync_end_date", "type"],
        },
        {
            "table": "attendance_status",
            "primary_key": ["employee", "sync_start_date", "sync_end_date", "type"],
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function which lets you configure how your connector fetches data.
    See the technical reference documentation for more details on the update function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: a dictionary that holds the state of the connector.
    """
    log.warning("Example: SOURCE_EXAMPLES : GREYTHR_API_CONNECTOR")

    # Validate the configuration to ensure all required fields are present
    validate_configuration(configuration)

    api_username = configuration.get("api_username")
    api_password = configuration.get("api_password")
    greythr_domain = configuration.get("greythr_domain")
    sync_start_date = configuration.get("sync_start_date", __DEFAULT_SYNC_START_DATE)

    access_token = get_access_token(api_username, api_password, greythr_domain)

    sync_employees(greythr_domain, access_token, state, api_username, api_password)
    sync_leave_transactions(
        greythr_domain, access_token, state, sync_start_date, api_username, api_password
    )
    sync_attendance_insights(
        greythr_domain, access_token, state, sync_start_date, api_username, api_password
    )


def get_access_token(api_username, api_password, greythr_domain):
    """
    Obtain OAuth2 access token using client credentials flow.
    Args:
        api_username: The API username for greytHR.
        api_password: The API password for greytHR.
        greythr_domain: The greytHR domain for the organization.
    Returns:
        str: The access token for API authentication.
    Raises:
        RuntimeError: If authentication fails after retries.
    """
    url = f"https://{greythr_domain}/uas/v1/oauth2/client-token"

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.post(
                url, auth=(api_username, api_password), timeout=__REQUEST_TIMEOUT_SECONDS
            )

            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get("access_token")

                # Validate that access_token is present in the response
                if not access_token:
                    log.error("Access token missing from authentication response")
                    raise RuntimeError("Access token missing from authentication response")

                log.info("Successfully obtained access token")
                return access_token

            if response.status_code == 403:
                log.error("Authentication failed: Invalid API credentials")
                raise RuntimeError(f"Authentication failed: {response.text}")

            if response.status_code in [429, 500, 502, 503, 504]:
                handle_retryable_error(attempt, response.status_code, "Authentication")
                continue

            log.error(f"Unexpected authentication error: {response.status_code} - {response.text}")
            raise RuntimeError(f"Authentication error: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            handle_timeout_error(attempt, "Authentication")
            continue

        except requests.exceptions.RequestException as error:
            handle_request_exception(attempt, "Authentication", error)
            continue
    raise RuntimeError(
        "Authentication failed after maximum retry attempts. Unable to obtain access token."
    )


def make_api_request(
    url, headers, params=None, api_username=None, api_password=None, greythr_domain=None
):
    """
    Make an API request with retry logic, exponential backoff, and token refresh.
    Args:
        url: The API endpoint URL.
        headers: HTTP headers for the request.
        params: Query parameters for the request.
        api_username: API username for token refresh (optional).
        api_password: API password for token refresh (optional).
        greythr_domain: greytHR domain for token refresh (optional).
    Returns:
        dict: JSON response from the API.
    Raises:
        RuntimeError: If request fails after retries.
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=__REQUEST_TIMEOUT_SECONDS
            )
            result = handle_api_response(
                response, url, headers, api_username, api_password, greythr_domain, attempt
            )
            if result is not None:
                return result

        except requests.exceptions.Timeout:
            handle_timeout_error(attempt, "Request")
            continue

        except requests.exceptions.RequestException as error:
            handle_request_exception(attempt, "Request", error)
            continue
    raise RuntimeError("API request failed after maximum retries")


def handle_api_response(
    response, url, headers, api_username, api_password, greythr_domain, attempt
):
    """
    Handle API response status codes and return appropriate result.
    Args:
        response: HTTP response object.
        url: API endpoint URL.
        headers: HTTP headers dictionary.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
        greythr_domain: greytHR domain for token refresh.
        attempt: Current retry attempt number.
    Returns:
        dict or None: JSON response if successful, None to continue retry, raises on errors.
    Raises:
        RuntimeError: If request fails permanently.
    """
    if response.status_code == 200:
        return handle_success_response(response)
    if response.status_code in [401, 403]:
        return handle_auth_errors(
            response, headers, api_username, api_password, greythr_domain, attempt
        )
    if response.status_code == 404:
        return handle_client_errors(response, url)
    if response.status_code in [429, 500, 502, 503, 504]:
        return handle_retryable_errors(response, attempt)
    return handle_unexpected_error(response)


def handle_success_response(response):
    """
    Handle successful API response (HTTP 200).
    Args:
        response: HTTP response object.
    Returns:
        dict: JSON response.
    """
    return response.json()


def handle_auth_errors(response, headers, api_username, api_password, greythr_domain, attempt):
    """
    Handle authentication errors (HTTP 401, 403).
    Args:
        response: HTTP response object.
        headers: HTTP headers dictionary.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
        greythr_domain: greytHR domain for token refresh.
        attempt: Current retry attempt number.
    Returns:
        None if token refresh is attempted, otherwise raises RuntimeError.
    Raises:
        RuntimeError: If authentication fails permanently.
    """
    if response.status_code == 401:
        if handle_token_expiration(headers, api_username, api_password, greythr_domain, attempt):
            return None
        raise RuntimeError(f"Authentication failed: {response.text}")
    if response.status_code == 403:
        log.error(f"Access forbidden: {response.text}")
        raise RuntimeError(f"Access forbidden: {response.text}")


def handle_client_errors(response, url):
    """
    Handle client errors (HTTP 404).
    Args:
        response: HTTP response object.
        url: API endpoint URL.
    Returns:
        dict: Empty dictionary for not found.
    """
    log.warning(f"Resource not found: {url}")
    return {}


def handle_retryable_errors(response, attempt):
    """
    Handle retryable errors (HTTP 429, 500, 502, 503, 504).
    Args:
        response: HTTP response object.
        attempt: Current retry attempt number.
    Returns:
        None to indicate retry.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    handle_retryable_error(attempt, response.status_code, "API request")
    return None


def handle_unexpected_error(response):
    """
    Handle unexpected API errors.
    Args:
        response: HTTP response object.
    Raises:
        RuntimeError: For unexpected errors.
    """
    log.error(f"Unexpected API error: {response.status_code} - {response.text}")
    raise RuntimeError(f"API error: {response.status_code} - {response.text}")


def handle_retryable_error(attempt, status_code, operation_name):
    """
    Handle retryable HTTP errors with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        status_code: HTTP status code received.
        operation_name: Name of the operation being retried.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} failed with status {status_code}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} failed after {__MAX_RETRIES} attempts. Status: {status_code}")
        raise RuntimeError(f"{operation_name} failed after {__MAX_RETRIES} attempts")


def handle_timeout_error(attempt, operation_name):
    """
    Handle timeout errors with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        operation_name: Name of the operation being retried.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} timed out, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} timed out after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{operation_name} timed out after {__MAX_RETRIES} attempts")


def handle_request_exception(attempt, operation_name, error):
    """
    Handle generic request exceptions with exponential backoff.
    Args:
        attempt: Current retry attempt number.
        operation_name: Name of the operation being retried.
        error: The exception that occurred.
    Raises:
        RuntimeError: If maximum retries exceeded.
    """
    if attempt < __MAX_RETRIES - 1:
        delay = __BASE_DELAY_SECONDS * (2**attempt)
        log.warning(
            f"{operation_name} failed, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        time.sleep(delay)
    else:
        log.error(f"{operation_name} failed after {__MAX_RETRIES} attempts")
        raise RuntimeError(f"{operation_name} failed: {str(error)}")


def handle_token_expiration(headers, api_username, api_password, greythr_domain, attempt):
    """
    Handle token expiration by refreshing the access token.
    Args:
        headers: HTTP headers dictionary to update with new token.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
        greythr_domain: greytHR domain for token refresh.
        attempt: Current retry attempt number.
    Returns:
        bool: True if token was refreshed, False otherwise.
    """
    if api_username and api_password and greythr_domain and attempt < __MAX_RETRIES - 1:
        log.warning(
            f"Token expired (401), refreshing token (attempt {attempt + 1}/{__MAX_RETRIES})"
        )
        new_token = get_access_token(api_username, api_password, greythr_domain)
        headers["ACCESS-TOKEN"] = new_token
        return True

    log.error("Authentication failed - unable to refresh token")
    return False


def build_api_headers(access_token, greythr_domain):
    """
    Build standard API request headers for greytHR API.
    Args:
        access_token: OAuth2 access token.
        greythr_domain: The greytHR domain.
    Returns:
        dict: Headers dictionary for API requests.
    """
    return {"ACCESS-TOKEN": access_token, "x-greythr-domain": greythr_domain}


def calculate_date_windows(state_key, state, sync_start_date):
    """
    Calculate start date for date windowing based on state.
    Args:
        state_key: Key name in state dictionary.
        state: State dictionary.
        sync_start_date: Initial sync start date string.
    Returns:
        tuple: (current_start_date, today_date) as date objects.
    """
    last_sync_end_date = state.get(state_key)

    if last_sync_end_date:
        current_start = datetime.fromisoformat(last_sync_end_date).date() + timedelta(days=1)
    else:
        current_start = datetime.fromisoformat(sync_start_date).date()

    today = datetime.now().date()
    return current_start, today


def sync_employees(greythr_domain, access_token, state, api_username, api_password):
    """
    Sync employee data from greytHR API using pagination.
    Args:
        greythr_domain: The greytHR domain.
        access_token: OAuth2 access token.
        state: State dictionary for tracking sync progress.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
    """
    log.info("Starting employee sync")

    headers = build_api_headers(access_token, greythr_domain)
    last_modified = state.get("employee_last_modified")
    page = 0
    has_next = True

    while has_next:
        params = build_employee_params(page, last_modified)
        log.info(f"Fetching employees page {page}")

        response_data = make_api_request(
            "https://api.greythr.com/employee/v2/employees",
            headers,
            params,
            api_username,
            api_password,
            greythr_domain,
        )

        if not response_data or "data" not in response_data:
            log.warning(f"No employee data found for page {page}")
            break

        employees = response_data.get("data", [])
        pages_info = response_data.get("pages", {})

        last_modified = process_employee_records(employees, last_modified)
        has_next = pages_info.get("hasNext", False)
        page += 1

        state["employee_last_modified"] = last_modified

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

    log.info(f"Completed employee sync. Last modified: {last_modified}")


def build_employee_params(page, last_modified):
    """
    Build query parameters for employee API request.
    Args:
        page: Page number for pagination.
        last_modified: Last modified timestamp for incremental sync.
    Returns:
        dict: Query parameters dictionary.
    """
    params = {"page": page, "size": __EMPLOYEE_PAGE_SIZE}

    if last_modified:
        params["modifiedSince"] = last_modified

    return params


def process_employee_records(employees, last_modified):
    """
    Process and upsert employee records.
    Args:
        employees: List of employee records.
        last_modified: Current last modified timestamp.
    Returns:
        str: Updated last modified timestamp.
    """
    for employee in employees:
        flatten_employee = flatten_dict(employee)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="employee", data=flatten_employee)

        employee_last_modified = employee.get("lastModified")
        if employee_last_modified:
            if not last_modified or employee_last_modified > last_modified:
                last_modified = employee_last_modified

    return last_modified


def sync_leave_transactions(
    greythr_domain, access_token, state, sync_start_date, api_username, api_password
):
    """
    Sync leave transaction data from greytHR API with date windowing due to 31-day API limit.
    Args:
        greythr_domain: The greytHR domain.
        access_token: OAuth2 access token.
        state: State dictionary for tracking sync progress.
        sync_start_date: The initial start date for syncing leave data.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
    """
    log.info("Starting leave transactions sync")

    headers = build_api_headers(access_token, greythr_domain)
    current_start, today = calculate_date_windows(
        "leave_last_sync_end_date", state, sync_start_date
    )

    while current_start <= today:
        current_end = min(current_start + timedelta(days=__MAX_DATE_RANGE_DAYS - 1), today)
        start_str = current_start.isoformat()
        end_str = current_end.isoformat()

        log.info(f"Fetching leave transactions for date range: {start_str} to {end_str}")

        params = {"start": start_str, "end": end_str}
        response_data = make_api_request(
            "https://api.greythr.com/leave/v2/employee/transactions",
            headers,
            params,
            api_username,
            api_password,
            greythr_domain,
        )

        if response_data and "data" in response_data:
            process_leave_data(response_data.get("data", []))

        state["leave_last_sync_end_date"] = end_str

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        current_start = current_end + timedelta(days=1)

    log.info(
        f"Completed leave transactions sync. Last sync end date: {state.get('leave_last_sync_end_date')}"
    )


def process_leave_data(employees_leave_data):
    """
    Process leave transaction data for all employees.
    Args:
        employees_leave_data: List of employee leave data from API.
    """
    for employee_data in employees_leave_data:
        employee_id = employee_data.get("employeeId")
        transactions = employee_data.get("list", [])

        for transaction in transactions:
            process_leave_transaction(transaction, employee_id)


def process_leave_transaction(transaction, employee_id):
    """
    Process a single leave transaction and its children.
    Args:
        transaction: Leave transaction record.
        employee_id: Employee ID for the transaction.
    """
    transaction["employeeId"] = employee_id
    children = transaction.pop("children", [])
    flatten_transaction = flatten_dict(transaction)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table="leave_transaction", data=flatten_transaction)

    process_leave_children(children, transaction.get("id"))


def process_leave_children(children, parent_id):
    """
    Process child records of a leave transaction.
    Args:
        children: List of child leave records.
        parent_id: Parent transaction ID.
    """
    for child in children:
        child["parent_id"] = parent_id
        flatten_child = flatten_dict(child)

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="leave_transaction_child", data=flatten_child)


def sync_attendance_insights(
    greythr_domain, access_token, state, sync_start_date, api_username, api_password
):
    """
    Sync attendance insight data from greytHR API with date windowing.
    Args:
        greythr_domain: The greytHR domain.
        access_token: OAuth2 access token.
        state: State dictionary for tracking sync progress.
        sync_start_date: The initial start date for syncing attendance data.
        api_username: API username for token refresh.
        api_password: API password for token refresh.
    """
    log.info("Starting attendance insights sync")

    headers = build_api_headers(access_token, greythr_domain)
    current_start, today = calculate_date_windows(
        "attendance_last_sync_end_date", state, sync_start_date
    )

    while current_start <= today:
        current_end = min(current_start + timedelta(days=__MAX_DATE_RANGE_DAYS - 1), today)
        start_str = current_start.isoformat()
        end_str = current_end.isoformat()

        log.info(f"Fetching attendance insights for date range: {start_str} to {end_str}")

        params = {"start": start_str, "end": end_str}
        response_data = make_api_request(
            "https://api.greythr.com/attendance/v2/employee/insights",
            headers,
            params,
            api_username,
            api_password,
            greythr_domain,
        )

        if response_data and "data" in response_data:
            process_attendance_data(response_data.get("data", []), start_str, end_str)

        state["attendance_last_sync_end_date"] = end_str

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        current_start = current_end + timedelta(days=1)

    log.info(
        f"Completed attendance insights sync. Last sync end date: {state.get('attendance_last_sync_end_date')}"
    )


def process_attendance_data(attendance_data, start_str, end_str):
    """
    Process attendance data for all employees.
    Args:
        attendance_data: List of attendance records from API.
        start_str: Start date string for the sync window.
        end_str: End date string for the sync window.
    """
    for record in attendance_data:
        employee_id = record.get("employee")
        insights = record.get("insights", {})

        base_record = {
            "employee": employee_id,
            "sync_start_date": start_str,
            "sync_end_date": end_str,
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="attendance_insight", data=base_record)

        process_attendance_averages(employee_id, insights.get("averages", []), start_str, end_str)
        process_attendance_day(employee_id, insights.get("days", []), start_str, end_str)
        process_attendance_status(employee_id, insights.get("status", []), start_str, end_str)


def process_attendance_averages(employee_id, averages, start_str, end_str):
    """
    Process attendance average metrics.
    Args:
        employee_id: Employee ID.
        averages: List of average metric records.
        start_str: Start date string.
        end_str: End date string.
    """
    for avg in averages:
        avg_record = {
            "employee": employee_id,
            "sync_start_date": start_str,
            "sync_end_date": end_str,
            "type": avg.get("type"),
            "average": avg.get("average"),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="attendance_average", data=avg_record)


def process_attendance_day(employee_id, days, start_str, end_str):
    """
    Process attendance day metrics.
    Args:
        employee_id: Employee ID.
        days: List of day metric records.
        start_str: Start date string.
        end_str: End date string.
    """
    for day in days:
        day_record = {
            "employee": employee_id,
            "sync_start_date": start_str,
            "sync_end_date": end_str,
            "type": day.get("type"),
            "days": day.get("days"),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="attendance_day", data=day_record)


def process_attendance_status(employee_id, status, start_str, end_str):
    """
    Process attendance status metrics.
    Args:
        employee_id: Employee ID.
        status: List of status metric records.
        start_str: Start date string.
        end_str: End date string.
    """
    for stat in status:
        status_record = {
            "employee": employee_id,
            "sync_start_date": start_str,
            "sync_end_date": end_str,
            "type": stat.get("type"),
            "days": stat.get("days"),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table="attendance_status", data=status_record)


def flatten_dict(data, prefix="", separator="_"):
    """
    Flatten nested dictionary into single level with underscore notation keys.
    Args:
        data: Dictionary to flatten.
        prefix: Prefix for flattened keys.
        separator: Separator character for nested keys.
    Returns:
        dict: Flattened dictionary.
    """
    flattened = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_dict(value, new_key, separator))
        elif isinstance(value, list):
            flattened[new_key] = json.dumps(value)
        else:
            flattened[new_key] = value

    return flattened


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
