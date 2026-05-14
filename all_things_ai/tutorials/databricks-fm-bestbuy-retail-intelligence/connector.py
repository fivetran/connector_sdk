"""
Databricks Best Buy Retail Intelligence Connector - Simple Enrichment

Syncs product catalog data from the Best Buy Products API and enriches
each product with AI-powered retail analytics using Databricks ai_query()
SQL function. Enrichments include competitive positioning assessment,
price optimization recommendations, and customer sentiment analysis.

This connector demonstrates Fivetran's value for the Retail vertical
on Databricks, mapping directly to the Databricks FY27 Retail Outcome
Map outcomes: Dynamic Price Optimization, Product Affinity, Assortment
Optimization, and Behavioral Segmentation.

Two-phase architecture:
  - Phase 1 (MOVE): Fetch product catalog data from the Best Buy API
  - Phase 2 (TRANSFORM): Enrich each product with AI analysis via
    Databricks ai_query() SQL function

Optional Genie Space creation after data lands for natural language
retail analytics.

See the Technical Reference documentation
(https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
and the Best Practices documentation
(https://fivetran.com/docs/connectors/connector-sdk/best-practices)
for details
"""

# For reading configuration from a JSON file
import json

# For time-based operations and rate limiting
import time

# For URL-encoding user-supplied path segments
import urllib.parse

# For generating unique IDs for Genie Space config elements
import uuid

# For making HTTP requests to external APIs
import requests

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# Best Buy API Configuration
__BASE_URL_BESTBUY = "https://api.bestbuy.com/v1/products"
__API_TIMEOUT_SECONDS = 30
__BESTBUY_PRODUCT_FIELDS = (
    "sku,name,salePrice,regularPrice,onSale,percentSavings,"
    "customerReviewAverage,customerReviewCount,manufacturer,"
    "shortDescription,categoryPath.name,condition,freeShipping,"
    "inStoreAvailability,onlineAvailability,url"
)

# Retry and Rate Limiting Constants
__MAX_RETRIES = 3
__BASE_DELAY_SECONDS = 1
__RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]
__BESTBUY_RATE_LIMIT_DELAY = 0.3

# Default Configuration Values
__DEFAULT_MAX_PRODUCTS = 25
__DEFAULT_BATCH_SIZE = 25
__DEFAULT_MAX_ENRICHMENTS = 10
__DEFAULT_DATABRICKS_MODEL = "databricks-claude-sonnet-4-6"
__DEFAULT_DATABRICKS_TIMEOUT = 120

# Best Buy Products API hard limit on pageSize per request.
__BESTBUY_API_MAX_PAGE_SIZE = 100

# Databricks SQL Statement API
__SQL_STATEMENT_ENDPOINT = "/api/2.0/sql/statements"
__SQL_WAIT_TIMEOUT = "50s"

# Genie Space API
__GENIE_SPACE_ENDPOINT = "/api/2.0/genie/spaces"

# Sanity ceilings
__MAX_PRODUCTS_CEILING = 500
__MAX_ENRICHMENTS_CEILING = 100

# Enrichment prompt truncation
__MAX_DESCRIPTION_CHARS = 500

# Genie Space configuration
__GENIE_SPACE_INSTRUCTIONS = (
    "You are a retail intelligence agent. This dataset contains "
    "Best Buy product catalog data enriched with AI-powered retail "
    "analytics. Each product has pricing data (sale vs regular price, "
    "percent savings), customer reviews, and AI-generated competitive "
    "positioning, price optimization recommendations, and sentiment "
    "analysis. Use the products_enriched table for all queries."
)

__GENIE_SPACE_SAMPLE_QUESTIONS = [
    "Which products have the highest price optimization opportunity?",
    "Show me products with high reviews but low sales price",
    "What categories have the most products on sale?",
    "List products where the AI recommends a price increase",
    "Which manufacturers have the highest average customer review scores?",
]


def flatten_dict(d, parent_key="", sep="_"):
    """
    Flatten nested dictionaries and serialize lists to JSON strings.
    REQUIRED for Fivetran compatibility.

    Args:
        d: Dictionary to flatten
        parent_key: Prefix for nested keys (used in recursion)
        sep: Separator between nested key levels

    Returns:
        Flattened dictionary with all nested structures resolved
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, (list, tuple)):
            items.append((new_key, json.dumps(v) if v else None))
        else:
            items.append((new_key, v))
    return dict(items)


def _is_placeholder(value):
    """
    Check if a configuration value is unset or an angle-bracket
    placeholder. Type-safe for non-strings.
    """
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if not value:
        return True
    return value.startswith("<") and value.endswith(">")


def _parse_bool(value, default=False):
    """
    Parse a boolean-like config value.

    Args:
        value: Configuration value to parse
        default: Default if value is None or placeholder

    Returns:
        Boolean interpretation of the value
    """
    if isinstance(value, bool):
        return value
    if value is None or _is_placeholder(value):
        return default
    return str(value).strip().lower() == "true"


def _optional_int(configuration, key, default):
    """
    Read an optional int config value, treating placeholders as unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to read
        default: Default value if key is missing or placeholder

    Returns:
        Integer value or default
    """
    value = configuration.get(key)
    if _is_placeholder(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _optional_str(configuration, key, default=None):
    """
    Read an optional string config value, treating placeholders as unset.

    Args:
        configuration: Configuration dictionary
        key: Configuration key to read
        default: Default value if key is missing or placeholder

    Returns:
        String value or default
    """
    value = configuration.get(key)
    if _is_placeholder(value):
        return default
    return value


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure all required
    parameters are present and valid.

    Args:
        configuration: a dictionary that holds the configuration
            settings for the connector.

    Raises:
        ValueError: if any required configuration parameter is
            missing or invalid.
    """
    if _is_placeholder(configuration.get("api_key")):
        raise ValueError("api_key is required (Best Buy Developer API key)")

    for param in ["max_products", "max_enrichments", "batch_size"]:
        value = configuration.get(param)
        if value is not None and not _is_placeholder(value):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{param} must be a positive integer")
            if parsed < 1:
                raise ValueError(f"{param} must be a positive integer")

    max_products = _optional_int(configuration, "max_products", __DEFAULT_MAX_PRODUCTS)
    if max_products > __MAX_PRODUCTS_CEILING:
        raise ValueError(
            f"max_products={max_products} exceeds ceiling of {__MAX_PRODUCTS_CEILING}."
        )

    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    if max_enrichments > __MAX_ENRICHMENTS_CEILING:
        raise ValueError(
            f"max_enrichments={max_enrichments} exceeds ceiling of {__MAX_ENRICHMENTS_CEILING}."
        )

    batch_size = _optional_int(configuration, "batch_size", __DEFAULT_BATCH_SIZE)
    if batch_size > __BESTBUY_API_MAX_PAGE_SIZE:
        raise ValueError(
            f"batch_size={batch_size} exceeds ceiling of {__BESTBUY_API_MAX_PAGE_SIZE}."
        )

    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)

    if is_enrichment or is_genie:
        for key in ["databricks_workspace_url", "databricks_token", "databricks_warehouse_id"]:
            if _is_placeholder(configuration.get(key)):
                raise ValueError(f"Missing required Databricks config: {key}")

        url = configuration.get("databricks_workspace_url", "")
        if not url.startswith("https://"):
            raise ValueError(f"databricks_workspace_url must start with 'https://'. Got: {url}")

    if is_genie and _is_placeholder(configuration.get("genie_table_identifier")):
        raise ValueError("genie_table_identifier required for Genie Space")


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [{"table": "products_enriched", "primary_key": ["sku"]}]


def create_session():
    """
    Create a requests session for Best Buy and Databricks API calls.

    Returns:
        requests.Session with appropriate headers
    """
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Fivetran-BestBuy-Databricks-Connector/1.0", "Accept": "application/json"}
    )
    return session


def fetch_data_with_retry(session, url, params=None):
    """
    Fetch data from API with exponential backoff retry logic.

    Args:
        session: requests.Session object
        url: Full URL to fetch
        params: Optional query parameters

    Returns:
        JSON response as dictionary

    Raises:
        RuntimeError: If all retry attempts fail
    """
    for attempt in range(__MAX_RETRIES):
        try:
            response = session.get(url, params=params, timeout=__API_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Connection failed after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.Timeout as e:
            log.warning(f"Timeout: {str(e)}")
            if attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"Retrying in {delay}s (attempt {attempt + 1}/{__MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise RuntimeError(f"Timeout after {__MAX_RETRIES} attempts: {e}") from e

        except requests.exceptions.RequestException as e:
            status_code = (
                e.response.status_code
                if hasattr(e, "response") and e.response is not None
                else None
            )
            if status_code in (401, 403):
                raise RuntimeError(f"HTTP {status_code}: Check API key. URL: {url}") from e

            if status_code in __RETRYABLE_STATUS_CODES and attempt < __MAX_RETRIES - 1:
                delay = __BASE_DELAY_SECONDS * (2**attempt)
                log.warning(f"HTTP {status_code}, retrying in {delay}s")
                time.sleep(delay)
            else:
                attempts = attempt + 1
                raise RuntimeError(f"API request failed after {attempts} attempt(s): {e}") from e


def call_ai_query(session, configuration, prompt):
    """
    Call Databricks ai_query() with async polling for PENDING states.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        prompt: Prompt text

    Returns:
        Response content string, or None on error
    """
    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
    timeout = _optional_int(configuration, "databricks_timeout", __DEFAULT_DATABRICKS_TIMEOUT)

    url = f"{workspace_url}{__SQL_STATEMENT_ENDPOINT}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    escaped = prompt.replace("'", "''")
    statement = f"SELECT ai_query('{model}', '{escaped}') as response"
    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": __SQL_WAIT_TIMEOUT,
    }

    try:
        response = session.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        sql_state = result.get("status", {}).get("state", "")

        statement_id = result.get("statement_id")

        # Pre-poll guard: when state is PENDING/RUNNING the initial response is
        # structurally allowed to omit statement_id. Polling f"{url}/None"
        # silently 404s and the failure mode is invisible. Surface it instead.
        if sql_state in ("PENDING", "RUNNING") and not statement_id:
            log.warning(
                "ai_query() initial response state=%s but missing statement_id; "
                "cannot poll. Returning None." % sql_state
            )
            return None

        poll_count = 0
        max_polls = 12

        while sql_state in ("PENDING", "RUNNING") and poll_count < max_polls:
            poll_count += 1
            time.sleep(10)
            poll_resp = session.get(f"{url}/{statement_id}", headers=headers, timeout=timeout)
            poll_resp.raise_for_status()
            result = poll_resp.json()
            sql_state = result.get("status", {}).get("state", "")
            log.info(f"ai_query() poll {poll_count}/{max_polls}: {sql_state}")

        if sql_state == "SUCCEEDED":
            data_array = result.get("result", {}).get("data_array", [])
            if data_array and data_array[0]:
                return data_array[0][0]
        elif sql_state == "FAILED":
            error = result.get("status", {}).get("error", {})
            log.warning("ai_query() failed: " + error.get("message", "Unknown"))
        else:
            log.warning(f"ai_query() final state: {sql_state}")
        return None

    except requests.exceptions.Timeout:
        log.warning(f"ai_query() timeout after {timeout}s")
        return None
    except requests.exceptions.HTTPError as e:
        body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json().get("message", "")[:200]
            except (json.JSONDecodeError, AttributeError):
                body = e.response.text[:200]
        log.warning(f"ai_query() HTTP error: {str(e)} — {body}")
        return None
    except requests.exceptions.ConnectionError as e:
        log.warning(f"ai_query() connection error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"ai_query() error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        log.warning(f"ai_query() JSON parse error: {str(e)}")
        return None


def extract_json_from_content(content):
    """
    Extract a JSON object from LLM response text.

    Args:
        content: String potentially containing JSON

    Returns:
        Parsed dictionary if found, or None
    """
    if not content or "{" not in content:
        return None
    start = content.find("{")
    end = content.rfind("}") + 1
    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return None


def build_product_record(product):
    """
    Build a normalized product record from Best Buy API data.

    Args:
        product: Raw Best Buy product dictionary

    Returns:
        Dictionary with normalized product fields
    """
    category_path = product.get("categoryPath", [])
    categories = [c.get("name", "") for c in category_path if c.get("name")]

    return {
        "sku": str(product.get("sku")),
        "name": product.get("name"),
        "sale_price": product.get("salePrice"),
        "regular_price": product.get("regularPrice"),
        "on_sale": product.get("onSale"),
        "percent_savings": product.get("percentSavings"),
        "customer_review_average": product.get("customerReviewAverage"),
        "customer_review_count": product.get("customerReviewCount"),
        "manufacturer": product.get("manufacturer"),
        "short_description": (
            (product.get("shortDescription") or "")[:__MAX_DESCRIPTION_CHARS] or None
        ),
        "category": categories[-1] if categories else None,
        "category_path": json.dumps(categories) if categories else None,
        "condition": product.get("condition"),
        "free_shipping": product.get("freeShipping"),
        "in_store_available": product.get("inStoreAvailability"),
        "online_available": product.get("onlineAvailability"),
        "url": product.get("url"),
    }


def enrich_product(session, configuration, record):
    """
    Enrich a product record with AI analysis via ai_query().

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        record: Normalized product record

    Returns:
        Dictionary with enrichment fields
    """
    model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)

    enrichment = {
        "competitive_positioning": None,
        "price_optimization": None,
        "price_action": None,
        "sentiment_summary": None,
        "retail_category_ai": None,
        "enrichment_model": model,
    }

    name = record.get("name", "Unknown")
    sale = record.get("sale_price")
    regular = record.get("regular_price")
    reviews = record.get("customer_review_average")
    review_count = record.get("customer_review_count")
    manufacturer = record.get("manufacturer", "Unknown")
    category = record.get("category", "Unknown")
    desc = record.get("short_description", "")

    prompt = (
        "Analyze this retail product and respond ONLY with a JSON "
        "object. No text outside the JSON.\n\n"
        "{\n"
        '  "competitive_positioning": "PREMIUM|MID_MARKET|VALUE|BUDGET",\n'
        '  "price_optimization": "Price is competitive/underpriced/overpriced '
        'relative to category and reviews (1-2 sentences)",\n'
        '  "price_action": "INCREASE|MAINTAIN|DECREASE|CLEARANCE",\n'
        '  "sentiment_summary": "Summary of likely customer sentiment based on '
        'review score and product positioning (1-2 sentences)",\n'
        '  "retail_category_ai": "AI-classified retail category '
        "(e.g., Consumer Electronics, Appliances, Computing, Gaming, "
        'Home Theater, Mobile, Smart Home, Other)"\n'
        "}\n\n"
        f"Product: {name}\n"
        f"Manufacturer: {manufacturer}\n"
        f"Category: {category}\n"
        f"Sale Price: ${sale}\n"
        f"Regular Price: ${regular}\n"
        f"On Sale: {record.get('on_sale')}\n"
        f"Savings: {record.get('percent_savings')}%\n"
        f"Review Score: {reviews}/5 ({review_count} reviews)\n"
        f"Description: {(desc or '')[:300]}\n\n"
        "JSON:"
    )

    content = call_ai_query(session, configuration, prompt)
    result = extract_json_from_content(content)

    if result and isinstance(result, dict):
        enrichment["competitive_positioning"] = result.get("competitive_positioning")
        enrichment["price_optimization"] = result.get("price_optimization")
        enrichment["price_action"] = result.get("price_action")
        enrichment["sentiment_summary"] = result.get("sentiment_summary")
        enrichment["retail_category_ai"] = result.get("retail_category_ai")

    time.sleep(__BESTBUY_RATE_LIMIT_DELAY)
    return enrichment


def create_genie_space(session, configuration, state):
    """
    Create a Databricks Genie Space for retail analytics.

    Args:
        session: requests.Session
        configuration: Configuration dictionary
        state: State dict for persisting space_id

    Returns:
        Space ID or None
    """
    existing = state.get("genie_space_id")
    if existing:
        log.info(f"Genie Space exists: {existing}")
        return existing

    workspace_url = configuration.get("databricks_workspace_url")
    token = configuration.get("databricks_token")
    warehouse_id = configuration.get("databricks_warehouse_id")
    table_id = configuration.get("genie_table_identifier")

    url = f"{workspace_url}{__GENIE_SPACE_ENDPOINT}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": uuid.uuid4().hex, "question": q} for q in __GENIE_SPACE_SAMPLE_QUESTIONS
            ]
        },
        "data_sources": {"tables": [{"identifier": table_id}]},
        "instructions": {
            "text_instructions": [{"id": uuid.uuid4().hex, "content": __GENIE_SPACE_INSTRUCTIONS}]
        },
    }

    payload = {
        "warehouse_id": warehouse_id,
        "title": "Best Buy Retail Intelligence",
        "description": "AI-enriched retail product data. Powered by Fivetran + Databricks.",
        "serialized_space": json.dumps(serialized),
    }

    try:
        resp = session.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        space_id = result.get("space_id")
        if space_id:
            log.info(f"Genie Space created: {space_id}")
            return space_id
        return None
    except requests.exceptions.HTTPError as e:
        log.warning(f"Genie Space error: {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        log.warning(f"Genie Space error: {str(e)}")
        return None


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during
    each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connectors/connector-sdk/technical-reference#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: all_things_ai/tutorials : databricks-fm-bestbuy-retail-intelligence")

    validate_configuration(configuration)

    api_key = configuration.get("api_key")
    max_products = _optional_int(configuration, "max_products", __DEFAULT_MAX_PRODUCTS)
    batch_size = _optional_int(configuration, "batch_size", __DEFAULT_BATCH_SIZE)
    is_enrichment = _parse_bool(configuration.get("enable_enrichment"), default=True)
    is_genie = _parse_bool(configuration.get("enable_genie_space"), default=False)
    max_enrichments = _optional_int(configuration, "max_enrichments", __DEFAULT_MAX_ENRICHMENTS)
    search_category = _optional_str(configuration, "search_category")

    if is_enrichment:
        model = _optional_str(configuration, "databricks_model", __DEFAULT_DATABRICKS_MODEL)
        log.info(f"Enrichment ENABLED: model={model}, max_enrichments={max_enrichments}")
    else:
        log.info("Enrichment DISABLED")

    session = create_session()

    try:
        # --- Phase 1: MOVE ---
        log.info("Phase 1 (MOVE): Fetching products from Best Buy")

        # Best Buy category filter goes in the URL path. URL-encode the
        # user-supplied value so spaces and reserved chars (e.g., parens)
        # cannot break the URL or inject path segments.
        if search_category:
            encoded_category = urllib.parse.quote(search_category, safe="")
            fetch_url = f"{__BASE_URL_BESTBUY}(categoryPath.name={encoded_category})"
        else:
            fetch_url = __BASE_URL_BESTBUY

        # Best Buy caps a single page at __BESTBUY_API_MAX_PAGE_SIZE; iterate
        # pages until we hit max_products or the API returns no more.
        page_size = min(batch_size, max_products, __BESTBUY_API_MAX_PAGE_SIZE)
        page = 1
        total_synced = 0
        enriched_count = 0
        api_total = None

        while total_synced < max_products:
            params = {
                "apiKey": api_key,
                "format": "json",
                "pageSize": page_size,
                "page": page,
                "show": __BESTBUY_PRODUCT_FIELDS,
                "sort": "customerReviewCount.dsc",
            }
            data = fetch_data_with_retry(session, fetch_url, params=params)
            products = data.get("products", [])

            if api_total is None:
                api_total = data.get("total", 0)
                log.info(f"Best Buy reports {api_total} products, max_products={max_products}")

            if not products:
                break

            for product in products:
                if total_synced >= max_products:
                    break

                record = build_product_record(product)
                if not record.get("sku"):
                    continue

                # Enrich if enabled and within budget
                if is_enrichment and enriched_count < max_enrichments:
                    has_content = record.get("name") and record.get("sale_price")
                    if has_content:
                        enrichment = enrich_product(session, configuration, record)
                        record.update(enrichment)
                        enriched_count += 1

                flattened = flatten_dict(record)

                # The 'upsert' operation is used to insert or update data in the destination table.
                # The first argument is the name of the destination table.
                # The second argument is a dictionary containing the record to be upserted.
                op.upsert(table="products_enriched", data=flattened)

                total_synced += 1

            # Stop if the API page returned fewer than requested (final page).
            if len(products) < page_size:
                break
            page += 1

        if total_synced == 0:
            log.info("No products found")
            # Save the progress by checkpointing the state. This is important for ensuring that
            # the sync process can resume from the correct position in case of next sync or
            # interruptions.
            # You should checkpoint even if you are not using incremental sync, as it tells
            # Fivetran it is safe to write to destination.
            # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
            # Learn more about how and where to checkpoint by reading our best practices
            # documentation
            # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
            op.checkpoint(state=state)
            return

        log.info(f"Phase 1 complete: {total_synced} products, {enriched_count} enriched")

        # Save the progress by checkpointing the state. This is important for ensuring that the
        # sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        # --- Phase 2: AGENT ---
        if is_genie:
            log.info("Phase 2 (AGENT): Creating Genie Space")
            space_id = create_genie_space(session, configuration, state)
            if space_id:
                state["genie_space_id"] = space_id
                # Save the progress by checkpointing the state. This is important for ensuring
                # that the sync process can resume from the correct position in case of next sync
                # or interruptions.
                # You should checkpoint even if you are not using incremental sync, as it tells
                # Fivetran it is safe to write to destination.
                # For large datasets, checkpoint regularly (e.g., every N records) not only at the
                # end.
                # Learn more about how and where to checkpoint by reading our best practices
                # documentation
                # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
                op.checkpoint(state=state)

        # Final checkpoint
        # Save the progress by checkpointing the state. This is important for ensuring that the
        # sync process can resume from the correct position in case of next sync or interruptions.
        # You should checkpoint even if you are not using incremental sync, as it tells Fivetran
        # it is safe to write to destination.
        # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
        # Learn more about how and where to checkpoint by reading our best practices documentation
        # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
        op.checkpoint(state=state)

        log.info(f"Sync complete: {total_synced} products synced")

    except Exception as e:
        log.error(f"Unexpected error: {str(e)}")
        raise

    finally:
        session.close()


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the
# command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
