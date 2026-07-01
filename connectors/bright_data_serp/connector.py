"""This connector syncs search engine results from Bright Data's SERP REST API to Fivetran.
See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Helper functions for data processing, validation, and API interaction
from helpers import (
    collect_all_fields,
    perform_search,
    process_and_upsert_results,
    process_search_result,
    validate_configuration,
)

# For supporting Connector operations like Update() and Schema()
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

__SERP_TABLE = "search_results"


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
            "table": __SERP_TABLE,
            "primary_key": [
                "query",
                "result_index",
            ],
            "columns": {
                "query": "STRING",
                "result_index": "INT",
            },
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
    log.warning("Example: Connectors : Bright Data SERP")

    validate_configuration(configuration=configuration)

    api_token = configuration.get("api_token")
    new_state = dict(state) if state else {}

    search_query_input = configuration.get("search_query", "")
    queries = parse_search_queries(search_query_input)

    if queries:
        sync_search_queries(
            configuration=configuration,
            queries=queries,
            api_token=api_token,
            state=new_state,
        )

    # Save the progress by checkpointing the state. This is important for ensuring that the sync
    # process can resume from the correct position in case of next sync or interruptions.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
    op.checkpoint(state=new_state)


def sync_search_queries(configuration: dict, queries: list, api_token: str, state: dict):
    """
    Fetch search results for the requested queries and upsert them to Fivetran.
    Args:
        configuration: Configuration dictionary containing search parameters.
        queries: List of search queries to execute.
        api_token: Bright Data API token.
        state: Current connector state.
    """
    search_engine = configuration.get("search_engine")
    country = configuration.get("country")
    search_zone = configuration.get("search_zone")
    response_format = configuration.get("format")

    query_payload = queries if len(queries) > 1 else queries[0]
    search_results = perform_search(
        api_token=api_token,
        query=query_payload,
        search_engine=search_engine,
        country=country,
        zone=search_zone,
        response_format=response_format,
    )

    processed_results = process_search_results(search_results, queries)

    if not processed_results:
        log.warning("No search results returned from API")
        return

    log.info(f"Upserting {len(processed_results)} search results to Fivetran")

    all_fields = collect_all_fields(processed_results)
    process_and_upsert_results(processed_results, all_fields, __SERP_TABLE)

    state["last_search_queries"] = queries
    state["last_search_count"] = len(processed_results)


def process_search_results(search_results, queries: list) -> list:
    """
    Normalize API results into flattened rows.
    Args:
        search_results: Raw search results from the Bright Data API.
        queries: List of queries that were executed.
    Returns:
        list: Processed result dictionaries ready for upsert.
    """
    processed_results = []

    if isinstance(search_results, list) and len(queries) > 1:
        for query_idx, query in enumerate(queries):
            if query_idx < len(search_results):
                query_results = search_results[query_idx]
                if isinstance(query_results, list):
                    for result_idx, result in enumerate(query_results):
                        processed_results.append(process_search_result(result, query, result_idx))
                elif isinstance(query_results, dict):
                    processed_results.append(process_search_result(query_results, query, 0))
    elif isinstance(search_results, list):
        for idx, result in enumerate(search_results):
            processed_results.append(process_search_result(result, queries[0], idx))
    elif isinstance(search_results, dict):
        processed_results.append(process_search_result(search_results, queries[0], 0))

    return processed_results


def parse_search_queries(search_query_input) -> list:
    """
    Normalize the search_query configuration value into a list of queries.
    Args:
        search_query_input: The search_query configuration value (various formats supported).
    Returns:
        list: List of normalized query strings.
    """
    if not search_query_input:
        return []

    if isinstance(search_query_input, list):
        return [
            item.strip() for item in search_query_input if isinstance(item, str) and item.strip()
        ]

    if isinstance(search_query_input, str):
        try:
            parsed = json.loads(search_query_input)
            if isinstance(parsed, list):
                return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
            if isinstance(parsed, str) and parsed.strip():
                return [parsed.strip()]
        except (json.JSONDecodeError, TypeError):
            pass

        if "," in search_query_input:
            return [item.strip() for item in search_query_input.split(",") if item.strip()]

        if "\n" in search_query_input:
            return [item.strip() for item in search_query_input.split("\n") if item.strip()]

        return [search_query_input.strip()] if search_query_input.strip() else []

    return []


connector = Connector(update=update, schema=schema)


if __name__ == "__main__":
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    connector.debug(configuration=configuration)
