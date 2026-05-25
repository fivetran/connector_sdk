"""This connector syncs web scraping data from Bright Data's Web Scraper API to Fivetran destination.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Helper functions for data processing, validation, and schema management
from helpers import (
    collect_all_fields,
    perform_scrape,
    process_scrape_result,
    update_fields_yaml,
    validate_configuration,
)

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
# For enabling Logs in your connector code
# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

# Table name constant
__SCRAPE_TABLE = "scrape_results"

# Linkedin Post By URL dataset ids
LINKEDIN_POST_BY_URL_DATASET_ID = "gd_d85r5d60186q96c883"


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
            "table": __SCRAPE_TABLE,
            "primary_key": [
                "url",
                "result_index",
            ],
        }
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
    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    api_token = configuration.get("api_token")
    dataset_id = configuration.get("dataset_id")
    scrape_url_input = configuration.get("scrape_url", "")

    urls = parse_scrape_urls(scrape_url_input)

    if not urls:
        log.warning("No URLs provided in configuration")
        raise RuntimeError("No URLs configured for sync")

    sync_scrape_urls(api_token, dataset_id, urls, state)


def parse_scrape_urls(scrape_url_input):
    """
    Parse URLs from configuration input, supporting multiple formats.
    Args:
        scrape_url_input: The scrape_url configuration value (various formats supported).
    Returns:
        list: List of URL strings.
    """
    if not scrape_url_input:
        return []

    if isinstance(scrape_url_input, list):
        return [
            item.strip() for item in scrape_url_input if isinstance(item, str) and item.strip()
        ]

    if isinstance(scrape_url_input, str):
        # Try parsing as JSON first
        parsed = json.loads(scrape_url_input)
        if isinstance(parsed, list):
            return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
        if isinstance(parsed, str) and parsed.strip():
            return [parsed.strip()]
        # Try comma-separated format
        if "," in scrape_url_input:
            return [item.strip() for item in scrape_url_input.split(",") if item.strip()]

        # Try newline-separated format
        if "\n" in scrape_url_input:
            return [item.strip() for item in scrape_url_input.split("\n") if item.strip()]

        # Single URL
        return [scrape_url_input.strip()] if scrape_url_input.strip() else []

    return []


def sync_scrape_urls(api_token, dataset_id, urls, state):
    """
    Sync scrape results for the requested URLs.
    Args:
        api_token: Bright Data API token.
        dataset_id: ID of the dataset to use for scraping.
        urls: List of URLs to scrape (processed in batch by API).
        state: State dictionary for tracking sync progress.
    """
    log.info(f"Starting scrape sync for {len(urls)} URL(s)")

    # Fetch scrape results for all URLs
    # The Bright Data REST API processes URLs and returns results in order
    # Apply dataset-specific query parameters when needed
    if dataset_id == LINKEDIN_POST_BY_URL_DATASET_ID:
        scrape_results = perform_scrape(
            api_token=api_token,
            dataset_id=dataset_id,
            url=urls,
            extra_query_params={"discover_by": "profile_url", "type": "discover_new"},
        )
    else:
        scrape_results = perform_scrape(
            api_token=api_token,
            dataset_id=dataset_id,
            url=urls,
        )

    # Normalize results to always be a list
    if not isinstance(scrape_results, list):
        scrape_results = [scrape_results]

    if not scrape_results:
        log.warning("No scrape results returned from API")
        return

    # Process and flatten results
    processed_results = process_scrape_results(scrape_results, urls)

    if not processed_results:
        log.warning("No processed results to upsert")
        return

    log.info(f"Upserting {len(processed_results)} scrape results to Fivetran")

    # Collect all fields and update schema documentation
    all_fields = collect_all_fields(processed_results)
    update_fields_yaml(all_fields, __SCRAPE_TABLE)

    # Upsert each result
    process_and_upsert_results(processed_results, all_fields)

    # Update state with sync information
    state["last_scrape_urls"] = urls
    state["last_scrape_count"] = len(processed_results)

    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state)

    log.info(f"Completed scrape sync. Total synced: {len(processed_results)} results")


def process_scrape_results(scrape_results, urls):
    """
    Process and flatten scrape results.
    Args:
        scrape_results: List of scrape results from API.
        urls: List of URLs that were scraped.
    Returns:
        list: List of processed result dictionaries.
    """
    processed_results = []

    # If we have multiple URLs, match results by index (one result per URL)
    # If we have one URL but multiple results, process all results
    if len(urls) == 1 and len(scrape_results) > 1:
        # Single URL with multiple results - process all results
        url = urls[0]
        log.info(
            f"Processing {len(scrape_results)} results from single URL. "
            f"Each result will get a unique result_index (0 to {len(scrape_results) - 1})"
        )
        for result_idx, result in enumerate(scrape_results):
            if isinstance(result, dict):
                result_url = result.get("input", {}).get("url") or result.get("url") or url
                processed_results.append(process_scrape_result(result, result_url, result_idx))
            elif isinstance(result, list):
                for item_idx, item in enumerate(result):
                    result_url = (
                        item.get("input", {}).get("url") if isinstance(item, dict) else url
                    )
                    processed_results.append(
                        process_scrape_result(item, result_url or url, item_idx)
                    )
    else:
        # Multiple URLs or one-to-one mapping - match by index
        missing_results = []
        for url_idx, url in enumerate(urls):
            if url_idx < len(scrape_results):
                result = scrape_results[url_idx]
                if isinstance(result, list):
                    for item_idx, item in enumerate(result):
                        processed_results.append(process_scrape_result(item, url, item_idx))
                else:
                    processed_results.append(process_scrape_result(result, url, 0))
            else:
                missing_results.append((url_idx, url))
        # Log missing results once after processing
        if missing_results:
            log.warning(
                f"No result found for {len(missing_results)} URL(s) at indices: "
                f"{', '.join(str(idx) for idx, _ in missing_results[:5])}"
                f"{' (and more)' if len(missing_results) > 5 else ''}"
            )

    return processed_results


def process_and_upsert_results(processed_results, all_fields):
    """
    Process and upsert scrape result records.
    Args:
        processed_results: List of processed result dictionaries.
        all_fields: List of all field names discovered from results.
    """
    primary_keys = {"url": str, "result_index": int}
    primary_key_errors = []
    for result in processed_results:
        # Ensure primary keys are always present with correct types
        for pk, pk_type in primary_keys.items():
            if pk not in result:
                primary_key_errors.append(f"Primary key '{pk}' missing from result")
                result[pk] = pk_type() if pk_type == str else 0
            else:
                current_value = result[pk]
                if not isinstance(current_value, pk_type):
                    try:
                        if pk_type == str:
                            result[pk] = str(current_value)
                        elif pk_type == int:
                            if isinstance(current_value, str):
                                cleaned = current_value.strip().strip("[]\"'")
                                result[pk] = int(cleaned) if cleaned.isdigit() else 0
                            else:
                                result[pk] = int(current_value)
                    except (ValueError, TypeError):
                        primary_key_errors.append(
                            f"Could not convert primary key '{pk}' to {pk_type.__name__}"
                        )
                        result[pk] = pk_type() if pk_type == str else 0

        # Build row data, ensuring primary keys have correct types
        row = {}
        for field in all_fields:
            value = result.get(field)
            # Explicitly ensure result_index is an integer before upsert
            if field == "result_index":
                if isinstance(value, str):
                    cleaned = value.strip().strip("[]\"'")
                    value = int(cleaned) if cleaned.isdigit() else 0
                elif value is not None:
                    value = int(value)
                else:
                    value = 0
            row[field] = value

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__SCRAPE_TABLE, data=row)

    # Log primary key errors once after processing all results
    if primary_key_errors:
        unique_errors = list(set(primary_key_errors))
        log.warning(
            f"Primary key validation issues: {', '.join(unique_errors[:3])}"
            f"{' (and more)' if len(unique_errors) > 3 else ''}"
        )


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button.
# This is useful for debugging while you write your code. Note this method is not called by
# Fivetran when executing your connector in production.
# Please test using the Fivetran debug command prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
