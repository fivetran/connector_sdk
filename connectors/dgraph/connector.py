"""Production-ready Dgraph GraphQL Connector for Fivetran Connector SDK.
This connector syncs e-commerce product catalog graph data from Dgraph into analytics warehouses.
Demonstrates real business value: product relationships, recommendations, and taxonomies.

Key Features:
- True incremental sync using DateTime filters on createdAt/updatedAt fields
- Preserves graph structure via separate edges table
- Cursor-based pagination with per-table checkpointing
- E-commerce use case: products, categories, attributes, reviews

See the Technical Reference documentation (https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update)
and the Best Practices documentation (https://fivetran.com/docs/connectors/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like Upsert(), Update(), Delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For making HTTP requests to Dgraph GraphQL API (provided by SDK runtime)
import requests

# For handling datetime parsing and formatting
from datetime import datetime, timezone

# For handling exponential backoff in retries
import time

# Constants for configuration
__API_TIMEOUT_SECONDS = 30
__MAX_RETRIES = 5
__RETRY_BASE_DELAY_SECONDS = 2
__PAGE_SIZE = 100
__CHECKPOINT_INTERVAL = 500

# Table names
__TABLE_PRODUCTS = "product"
__TABLE_CATEGORIES = "category"
__TABLE_ATTRIBUTES = "attribute"
__TABLE_REVIEWS = "review"
__TABLE_EDGES = "relationship"
__TABLE_SCHEMA = "schema_metadata"

# Relationship types for edges table
__REL_PRODUCT_CATEGORY = "BELONGS_TO_CATEGORY"
__REL_PRODUCT_RELATED = "RELATED_TO"
__REL_PRODUCT_ATTRIBUTE = "HAS_ATTRIBUTE"
__REL_REVIEW_PRODUCT = "REVIEWS_PRODUCT"
__REL_REVIEW_USER = "WRITTEN_BY_USER"

# GraphQL query templates
__SCHEMA_QUERY = """
query {
    getGQLSchema {
        schema
    }
}
"""

__CATEGORY_QUERY_TEMPLATE = """
query {{
    queryCategory(first: {page_size}, offset: {offset}{filter}) {{
        id
        name
        description
        parentCategory {{
            id
        }}
        createdAt
        updatedAt
    }}
}}
"""

__ATTRIBUTE_QUERY_TEMPLATE = """
query {{
    queryAttribute(first: {page_size}, offset: {offset}{filter}) {{
        id
        name
        value
        unit
        createdAt
        updatedAt
    }}
}}
"""

__PRODUCT_QUERY_TEMPLATE = """
query {{
    queryProduct(first: {page_size}, offset: {offset}{filter}) {{
        id
        sku
        name
        description
        price
        inStock
        category {{
            id
        }}
        attributes {{
            id
        }}
        relatedProducts {{
            id
        }}
        createdAt
        updatedAt
    }}
}}
"""

__REVIEW_QUERY_TEMPLATE = """
query {{
    queryReview(first: {page_size}, offset: {offset}{filter}) {{
        id
        rating
        comment
        product {{
            id
        }}
        author {{
            id
            username
        }}
        createdAt
    }}
}}
"""


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    required_configs = ["dgraph_url", "api_key"]
    for key in required_configs:
        if key not in configuration:
            raise ValueError(f"Missing required configuration value: {key}")

    # Validate URL format
    dgraph_url = configuration.get("dgraph_url", "")
    if not dgraph_url or not dgraph_url.strip():
        raise ValueError("dgraph_url cannot be empty")
    if not dgraph_url.startswith("http://") and not dgraph_url.startswith("https://"):
        raise ValueError("dgraph_url must start with http:// or https://")

    # Validate API key is not empty
    api_key = configuration.get("api_key", "")
    if not api_key or not api_key.strip():
        raise ValueError("api_key cannot be empty")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {"table": __TABLE_PRODUCTS, "primary_key": ["product_id"]},
        {"table": __TABLE_CATEGORIES, "primary_key": ["category_id"]},
        {"table": __TABLE_ATTRIBUTES, "primary_key": ["attribute_id"]},
        {"table": __TABLE_REVIEWS, "primary_key": ["review_id"]},
        {"table": __TABLE_EDGES, "primary_key": ["edge_id"]},
        {"table": __TABLE_SCHEMA, "primary_key": ["type_name"]},
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
    log.warning("Example: Source Examples - Dgraph E-Commerce Catalog Connector")

    # Validate the configuration to ensure it contains all required values
    validate_configuration(configuration=configuration)

    # Extract configuration parameters
    dgraph_url = configuration.get("dgraph_url")
    api_key = configuration.get("api_key")

    # Ensure URL ends with proper GraphQL endpoints
    base_url = dgraph_url.rstrip("/")
    graphql_endpoint = f"{base_url}/graphql"
    admin_endpoint = f"{base_url}/admin"

    # Initialize state for first sync with per-table timestamps
    if not state:
        state = {
            "last_sync_timestamp": None,
            "products_last_updated": None,
            "categories_last_updated": None,
            "attributes_last_updated": None,
            "reviews_last_updated": None,
            "schema_synced_at": None,
        }

    try:
        # Sync schema metadata (full sync each time - small dataset)
        sync_schema_metadata(admin_endpoint, api_key, state)

        # Sync categories with incremental support
        sync_categories(graphql_endpoint, api_key, state)

        # Sync attributes with incremental support
        sync_attributes(graphql_endpoint, api_key, state)

        # Sync products with incremental support
        sync_products(graphql_endpoint, api_key, state)

        # Sync reviews with incremental support
        sync_reviews(graphql_endpoint, api_key, state)

        # Update final sync timestamp
        state["last_sync_timestamp"] = datetime.now(timezone.utc).isoformat()

        # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
        # from the correct position in case of next sync or interruptions.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
        op.checkpoint(state)

        log.info(f"Sync completed successfully at {state['last_sync_timestamp']}")

    except Exception as e:
        log.error("Failed to sync data from Dgraph", e)
        raise RuntimeError(f"Failed to sync data: {str(e)}") from e


def sync_schema_metadata(admin_endpoint: str, api_key: str, state: dict):
    """
    Sync GraphQL schema metadata from Dgraph admin API.
    Args:
        admin_endpoint: The Dgraph admin API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    """
    log.info("Syncing schema metadata from Dgraph")

    try:
        response = execute_graphql_query(admin_endpoint, __SCHEMA_QUERY, api_key)

        if response and "data" in response and "getGQLSchema" in response["data"]:
            schema_data = response["data"]["getGQLSchema"]

            if schema_data and schema_data.get("schema"):
                schema_text = schema_data["schema"]
                types = parse_schema_types(schema_text)

                record_count = 0
                for type_info in types:
                    # The 'upsert' operation is used to insert or update data in the destination table.
                    # The first argument is the name of the destination table.
                    # The second argument is a dictionary containing the record to be upserted.
                    op.upsert(table=__TABLE_SCHEMA, data=type_info)
                    record_count += 1

                log.info(f"Synced {record_count} schema types")
                state["schema_synced_at"] = datetime.now(timezone.utc).isoformat()

                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)
            else:
                log.info("No schema found in Dgraph instance")
        else:
            log.warning("Unable to retrieve schema from Dgraph")

    except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
        log.error("Network error syncing schema metadata", e)
        raise
    except ValueError as e:
        log.error("JSON parsing error syncing schema metadata", e)
        raise
    except Exception as e:
        log.error("Unexpected error syncing schema metadata", e)
        raise


def sync_entity(
    entity_name: str,
    query_key: str,
    graphql_endpoint: str,
    api_key: str,
    state: dict,
    state_key: str,
    query_template: str,
    process_fn,
    timestamp_field: str = "updatedAt",
):
    """
    Generalized function to sync entities with incremental sync support.
    Args:
        entity_name: The name of the entity being synced (e.g., "product", "category").
        query_key: The GraphQL query response key (e.g., "queryProduct", "queryCategory").
        graphql_endpoint: The Dgraph GraphQL API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
        state_key: The key in the state dict for this entity's last sync timestamp.
        query_template: The GraphQL query template string with placeholders.
        process_fn: The function to process each batch of records.
        timestamp_field: The field name to use for incremental filtering (default: "updatedAt").
    """
    log.info(f"Syncing {entity_name} with incremental filter")

    last_updated = state.get(state_key)
    filter_clause = ""

    if last_updated:
        log.info(f"Incremental sync: fetching {entity_name} updated after {last_updated}")
        filter_clause = f', filter: {{ {timestamp_field}: {{ ge: "{last_updated}" }} }}'
    else:
        log.info(f"Initial sync: fetching all {entity_name}")

    offset = 0
    total_synced = 0
    max_updated_at = last_updated

    while True:
        query = query_template.format(page_size=__PAGE_SIZE, offset=offset, filter=filter_clause)

        try:
            response = execute_graphql_query(graphql_endpoint, query, api_key)

            if not response or "data" not in response:
                log.warning(f"No data returned for {entity_name} at offset {offset}")
                break

            # Get the data using the query response key (e.g., "queryProduct", "queryCategory")
            entities = response["data"].get(query_key, [])

            if not entities:
                break

            # Process batch of entities
            max_updated_at = process_fn(entities, max_updated_at)
            total_synced += len(entities)

            log.info(f"Processed {len(entities)} {entity_name} at offset {offset}")

            offset += len(entities)

            # Checkpoint after specified interval
            if total_synced % __CHECKPOINT_INTERVAL == 0:
                state[state_key] = max_updated_at
                # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
                # from the correct position in case of next sync or interruptions.
                # Learn more about how and where to checkpoint by reading our best practices documentation
                # (https://fivetran.com/docs/connectors/connector-sdk/best-practices#largedatasetrecommendation).
                op.checkpoint(state)

            if len(entities) < __PAGE_SIZE:
                break

        except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
            ValueError,
        ) as e:
            log.error(f"Error syncing {entity_name} at offset {offset}", e)
            raise

    # Update state with the most recent timestamp
    if max_updated_at:
        state[state_key] = max_updated_at

    log.info(f"Completed syncing {total_synced} {entity_name}")


def process_categories_batch(categories: list, max_updated_at: str):
    """
    Process a batch of categories and upsert them with their relationships.
    Args:
        categories: List of category records from the GraphQL response.
        max_updated_at: The current maximum updated timestamp.
    Returns:
        The updated maximum updated timestamp after processing the batch.
    """
    for category in categories:
        category_record = {
            "category_id": category.get("id"),
            "name": category.get("name"),
            "description": category.get("description"),
            "parent_category_id": (
                category.get("parentCategory", {}).get("id")
                if category.get("parentCategory")
                else None
            ),
            "created_at": category.get("createdAt"),
            "updated_at": category.get("updatedAt"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_CATEGORIES, data=category_record)

        # Track the most recent updatedAt timestamp
        updated_at = category.get("updatedAt")
        if updated_at and (not max_updated_at or updated_at > max_updated_at):
            max_updated_at = updated_at

        # Create edge for parent relationship
        if category_record["parent_category_id"]:
            edge_record = create_edge_record(
                source_id=category_record["category_id"],
                source_type="Category",
                target_id=category_record["parent_category_id"],
                target_type="Category",
                relationship_type="HAS_PARENT",
            )
            # The 'upsert' operation is used to insert or update data in the destination table.
            # The first argument is the name of the destination table.
            # The second argument is a dictionary containing the record to be upserted.
            op.upsert(table=__TABLE_EDGES, data=edge_record)

    return max_updated_at


def sync_categories(graphql_endpoint: str, api_key: str, state: dict):
    """
    Sync product categories with TRUE incremental sync using updatedAt filter.
    Args:
        graphql_endpoint: The Dgraph GraphQL API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    """
    sync_entity(
        entity_name="category",
        query_key="queryCategory",
        graphql_endpoint=graphql_endpoint,
        api_key=api_key,
        state=state,
        state_key="categories_last_updated",
        query_template=__CATEGORY_QUERY_TEMPLATE,
        process_fn=process_categories_batch,
        timestamp_field="updatedAt",
    )


def process_attributes_batch(attributes: list, max_updated_at: str):
    """
    Process a batch of attributes and upsert them.
    Args:
        attributes: List of attribute records from the GraphQL response.
        max_updated_at: The current maximum updated timestamp.
    Returns:
        The updated maximum updated timestamp after processing the batch.
    """
    for attribute in attributes:
        attribute_record = {
            "attribute_id": attribute.get("id"),
            "name": attribute.get("name"),
            "value": attribute.get("value"),
            "unit": attribute.get("unit"),
            "created_at": attribute.get("createdAt"),
            "updated_at": attribute.get("updatedAt"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_ATTRIBUTES, data=attribute_record)

        updated_at = attribute.get("updatedAt")
        if updated_at and (not max_updated_at or updated_at > max_updated_at):
            max_updated_at = updated_at

    return max_updated_at


def sync_attributes(graphql_endpoint: str, api_key: str, state: dict):
    """
    Sync product attributes with TRUE incremental sync.
    Args:
        graphql_endpoint: The Dgraph GraphQL API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    """
    sync_entity(
        entity_name="attribute",
        query_key="queryAttribute",
        graphql_endpoint=graphql_endpoint,
        api_key=api_key,
        state=state,
        state_key="attributes_last_updated",
        query_template=__ATTRIBUTE_QUERY_TEMPLATE,
        process_fn=process_attributes_batch,
        timestamp_field="updatedAt",
    )


def upsert_product_edges(product_id: str, product: dict):
    """
    Create and upsert edges for product relationships to preserve graph structure.
    Args:
        product_id: The product ID for which to create edges.
        product: The product data from the GraphQL response containing relationships.
    """
    # Category relationship
    category_id = product.get("category", {}).get("id") if product.get("category") else None
    if category_id:
        edge = create_edge_record(
            product_id, "Product", category_id, "Category", __REL_PRODUCT_CATEGORY
        )
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_EDGES, data=edge)

    # Attribute relationships
    for attr in product.get("attributes", []):
        edge = create_edge_record(
            product_id, "Product", attr["id"], "Attribute", __REL_PRODUCT_ATTRIBUTE
        )
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_EDGES, data=edge)

    # Related products (recommendations)
    for related in product.get("relatedProducts", []):
        edge = create_edge_record(
            product_id, "Product", related["id"], "Product", __REL_PRODUCT_RELATED
        )
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_EDGES, data=edge)


def process_products_batch(products: list, max_updated_at: str):
    """
    Process a batch of products and upsert them with their relationships.
    Args:
        products: List of product records from the GraphQL response.
        max_updated_at: The current maximum updated timestamp.
    Returns:
        The updated maximum updated timestamp after processing the batch.
    """
    for product in products:
        product_record = {
            "product_id": product.get("id"),
            "sku": product.get("sku"),
            "name": product.get("name"),
            "description": product.get("description"),
            "price": product.get("price"),
            "in_stock": product.get("inStock"),
            "category_id": (
                product.get("category", {}).get("id") if product.get("category") else None
            ),
            "attributes_count": len(product.get("attributes", [])),
            "related_products_count": len(product.get("relatedProducts", [])),
            "created_at": product.get("createdAt"),
            "updated_at": product.get("updatedAt"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_PRODUCTS, data=product_record)

        updated_at = product.get("updatedAt")
        if updated_at and (not max_updated_at or updated_at > max_updated_at):
            max_updated_at = updated_at

        # Create edges for relationships - preserves graph structure
        upsert_product_edges(product_record["product_id"], product)

    return max_updated_at


def sync_products(graphql_endpoint: str, api_key: str, state: dict):
    """
    Sync products with TRUE incremental sync and relationship preservation.
    Args:
        graphql_endpoint: The Dgraph GraphQL API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    """
    sync_entity(
        entity_name="product",
        query_key="queryProduct",
        graphql_endpoint=graphql_endpoint,
        api_key=api_key,
        state=state,
        state_key="products_last_updated",
        query_template=__PRODUCT_QUERY_TEMPLATE,
        process_fn=process_products_batch,
        timestamp_field="updatedAt",
    )


def upsert_review_edges(review_id: str, product_id: str, author_id: str):
    """
    Create and upsert edges for review relationships.
    Args:
        review_id: The review ID for which to create edges.
        product_id: The product ID being reviewed (may be None).
        author_id: The author ID who wrote the review (may be None).
    """
    if product_id:
        edge = create_edge_record(review_id, "Review", product_id, "Product", __REL_REVIEW_PRODUCT)
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_EDGES, data=edge)

    if author_id:
        edge = create_edge_record(review_id, "Review", author_id, "User", __REL_REVIEW_USER)
        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_EDGES, data=edge)


def process_reviews_batch(reviews: list, max_created_at: str):
    """
    Process a batch of reviews and upsert them with their relationships.
    Args:
        reviews: List of review records from the GraphQL response.
        max_created_at: The current maximum created timestamp.
    Returns:
        The updated maximum created timestamp after processing the batch.
    """
    for review in reviews:
        review_record = {
            "review_id": review.get("id"),
            "rating": review.get("rating"),
            "comment": review.get("comment"),
            "product_id": (review.get("product", {}).get("id") if review.get("product") else None),
            "author_id": (review.get("author", {}).get("id") if review.get("author") else None),
            "author_username": (
                review.get("author", {}).get("username") if review.get("author") else None
            ),
            "created_at": review.get("createdAt"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__TABLE_REVIEWS, data=review_record)

        created_at = review.get("createdAt")
        if created_at and (not max_created_at or created_at > max_created_at):
            max_created_at = created_at

        # Create edges for review relationships
        upsert_review_edges(
            review_record["review_id"],
            review_record["product_id"],
            review_record["author_id"],
        )

    return max_created_at


def sync_reviews(graphql_endpoint: str, api_key: str, state: dict):
    """
    Sync product reviews with TRUE incremental sync.
    Args:
        graphql_endpoint: The Dgraph GraphQL API endpoint URL.
        api_key: The API key for authentication.
        state: The state dictionary to track sync progress.
    """
    sync_entity(
        entity_name="review",
        query_key="queryReview",
        graphql_endpoint=graphql_endpoint,
        api_key=api_key,
        state=state,
        state_key="reviews_last_updated",
        query_template=__REVIEW_QUERY_TEMPLATE,
        process_fn=process_reviews_batch,
        timestamp_field="createdAt",
    )


def create_edge_record(
    source_id: str,
    source_type: str,
    target_id: str,
    target_type: str,
    relationship_type: str,
):
    """
    Create an edge record for the relationships table to preserve graph structure.
    Args:
        source_id: The ID of the source node.
        source_type: The type of the source node.
        target_id: The ID of the target node.
        target_type: The type of the target node.
        relationship_type: The type of relationship.
    Returns:
        A dictionary representing the edge record.
    """
    edge_id = f"{source_id}_{relationship_type}_{target_id}"

    return {
        "edge_id": edge_id,
        "source_id": source_id,
        "source_type": source_type,
        "target_id": target_id,
        "target_type": target_type,
        "relationship_type": relationship_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def check_response_status(response: requests.Response):
    """
    Check HTTP response status and raise errors for authentication and bad requests.
    Args:
        response: The HTTP response object from requests.
    """
    # Authentication errors - don't retry
    if response.status_code in (401, 403):
        log.error(f"Authentication failed: {response.status_code}")
        raise RuntimeError(f"Authentication failed with status {response.status_code}")

    # Bad request - don't retry
    if response.status_code == 400:
        log.error(f"Bad request: {response.text}")
        raise RuntimeError(f"Bad request: {response.text}")

    response.raise_for_status()


def handle_retry_logic(attempt: int, error: Exception):
    """
    Handle retry logic with exponential backoff for transient errors.
    Args:
        attempt: The current attempt number (0-indexed).
        error: The exception that was raised.
    """
    if attempt == __MAX_RETRIES - 1:
        log.error(f"Request failed after {__MAX_RETRIES} retries", error)
        raise

    sleep_time = min(60, __RETRY_BASE_DELAY_SECONDS**attempt)
    log.warning(f"Retry {attempt + 1}/{__MAX_RETRIES} after {sleep_time}s due to: {str(error)}")
    time.sleep(sleep_time)


def execute_graphql_query(endpoint: str, query: str, api_key: str):
    """
    Execute a GraphQL query against Dgraph with retry logic.
    Args:
        endpoint: The GraphQL endpoint URL.
        query: The GraphQL query string.
        api_key: The API key for authentication.
    Returns:
        The JSON response from the GraphQL API.
    """
    headers = {"Content-Type": "application/json", "X-Auth-Token": api_key}

    payload = {"query": query}

    # Retry loop with exponential backoff
    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.post(
                endpoint, json=payload, headers=headers, timeout=__API_TIMEOUT_SECONDS
            )

            check_response_status(response)

            # Parse JSON response
            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                log.warning(f"GraphQL errors in response: {result['errors']}")

            return result

        except (requests.Timeout, requests.ConnectionError) as e:
            handle_retry_logic(attempt, e)

        except requests.HTTPError as e:
            # Server errors - retry, client errors - don't retry
            if hasattr(e, "response") and e.response is not None and e.response.status_code >= 500:
                handle_retry_logic(attempt, e)
            else:
                log.error("HTTP error", e)
                raise

        # Removed generic exception catch block to comply with SDK best practices.

    return None


def parse_schema_types(schema_text: str):
    """
    Parse GraphQL schema text to extract type definitions.
    Args:
        schema_text: The GraphQL schema as a string.
    Returns:
        A list of dictionaries containing type information.
    """
    types = []
    current_type = None
    field_count = 0

    lines = schema_text.split("\n")

    for line in lines:
        stripped = line.strip()

        # Look for type definitions (excluding Query and Mutation)
        is_type_def = stripped.startswith("type ")
        is_query_or_mutation = stripped.startswith("type Query") or stripped.startswith(
            "type Mutation"
        )
        if is_type_def and not is_query_or_mutation:
            if current_type:
                # Save previous type
                types.append(
                    {
                        "type_name": current_type,
                        "field_count": field_count,
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Extract type name
            parts = stripped.split()
            if len(parts) >= 2:
                type_name = parts[1].replace("{", "").strip()
                current_type = type_name
                field_count = 0

        elif current_type and ":" in stripped and not stripped.startswith("@"):
            # This is a field definition
            field_count += 1

        elif current_type and stripped == "}":
            # End of current type
            types.append(
                {
                    "type_name": current_type,
                    "field_count": field_count,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            current_type = None
            field_count = 0

    return types


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
