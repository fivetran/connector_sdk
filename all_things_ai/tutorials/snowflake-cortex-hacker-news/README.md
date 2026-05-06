# Hacker News and Snowflake Cortex Connector Example

## Connector overview

This connector syncs top stories from the Hacker News API and enriches them with AI-powered analysis using the Snowflake Cortex REST API during ingestion. It demonstrates real-time AI enrichment as part of a Fivetran data pipeline, combining a free public API with Snowflake Cortex inference capabilities.

Each story is optionally enriched with two AI analyses: sentiment analysis that classifies the story title as positive, negative, or neutral with a confidence score and reasoning, and topic classification that assigns one of eight categories (AI, Security, Startups, Programming, Hardware, Science, Business, Other) with keyword extraction. The connector supports incremental syncing using story ID as a cursor and checkpoints progress after each batch for reliable resumable syncs.

Use cases:
- Tech trend analysis - Track sentiment and topic trends across Hacker News to understand what the developer community cares about
- Content curation - Automatically classify and filter stories by topic for newsletters, dashboards, or research feeds
- AI enrichment demonstration - Showcase real-time Snowflake Cortex inference during data ingestion in a Fivetran pipeline
- Model comparison - Test different Cortex LLM models (Claude, Mistral, Llama) on the same data by changing a single configuration parameter

APIs used:
- [Hacker News API](https://github.com/HackerNews/API) - Story retrieval via Firebase endpoints (no authentication required)
- [Snowflake Cortex REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-llm-rest-api) - AI inference for sentiment analysis and topic classification


## Requirements

- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- Snowflake account with Cortex enabled (for AI enrichment)
- Snowflake Personal Access Token (PAT) with the `snowflake.cortex_user` database role


## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.


## Features

- Incremental syncing using story ID as a cursor to avoid re-fetching previously synced stories
- Real-time AI enrichment during ingestion via Snowflake Cortex REST API with configurable model selection
- Dual enrichment pipeline with sentiment analysis and topic classification on each story title
- Configurable enrichment limits for cost control during testing and production use
- Cortex enrichment is optional and can be disabled to sync raw Hacker News data only
- Exponential backoff retry logic for transient API failures and rate limiting
- Batch processing with checkpointing after each batch for reliable resumable syncs


## Configuration file

The `configuration.json` file contains the parameters needed to connect to the Hacker News API and optionally configure Snowflake Cortex enrichment:

```json
{
    "max_stories": "50",
    "batch_size": "10",
    "enable_cortex": "true",
    "snowflake_account": "<YOUR_SNOWFLAKE_ACCOUNT.snowflakecomputing.com>",
    "snowflake_pat_token": "<YOUR_SNOWFLAKE_PAT>",
    "cortex_model": "mistral-large2",
    "cortex_timeout": "30",
    "max_enrichments": "50"
}
```

Configuration parameters:

- `max_stories` (optional): Maximum number of stories to sync per run, defaults to `50`
- `batch_size` (optional): Number of stories to process before checkpointing, defaults to `10`
- `enable_cortex` (optional): Enable or disable Cortex AI enrichment, defaults to `true`
- `snowflake_account` (conditional): Full Snowflake account domain, required when enable_cortex is `true`
- `snowflake_pat_token` (conditional): Snowflake personal access token, required when enable_cortex is `true`
- `cortex_model` (optional): Cortex LLM model name for inference, defaults to `mistral-large2`
- `cortex_timeout` (optional): Timeout in seconds for Cortex API calls, defaults to `30`
- `max_enrichments` (optional): Maximum number of AI enrichments per sync for cost control, defaults to `50`

Note: This example repository includes a `configuration.json` file checked into version control, but it contains only placeholder values and no real credentials. In your own production repositories, do not commit `configuration.json` files containing real secrets or environment-specific configuration; instead, use environment variables or a secrets manager to store sensitive values.


## Authentication

This connector uses two authentication mechanisms:

Hacker News API:
- No authentication required
- The API is free and open with no API key needed
- A descriptive user-agent header is included for polite API usage

Snowflake Cortex REST API:
- Uses [personal access token (PAT) authentication](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens). Generate a PAT through the Snowflake UI:
  1. Go to **Profile** > **Account Settings**.
  2. Select **Security** and then go to **Personal Access Tokens**.
  3. You must grant the user the `snowflake.cortex_user` database role for Cortex inference access.
- The token is sent in the Authorization header as `Bearer <token>` on every Cortex API request.


## Pagination

The Hacker News API returns the complete list of top story IDs (up to 500) in a single response from the `/topstories.json` endpoint. No pagination is required for story ID retrieval.

Individual story details are fetched one at a time from the `/item/{id}.json` endpoint. The connector processes stories in configurable batches (default 10) and checkpoints state after each batch. Only stories with IDs greater than the last synced ID are fetched, implementing incremental sync behavior.


## Data handling

The `def update(configuration, state)` function orchestrates the sync by fetching the list of top story IDs, filtering to new stories, sorting them in ascending order for contiguous state advancement, and processing them in batches. Ascending sort order combined with halt-on-failure semantics ensures the state cursor never advances past a failed lower-ID story.

For each batch, the `def process_batch(session, configuration, story_ids, is_cortex_enabled, enriched_count, max_enrichments, state)` function fetches individual story details via `def fetch_story(session, story_id)`, optionally enriches them with AI analysis via `def enrich_story(session, configuration, title)`, flattens nested structures, and upserts records to the destination. The `max_enrichments` limit counts each enrichment attempt regardless of which specific enrichment fields succeed, ensuring cost control is enforced based on Cortex API calls made.

The `def fetch_story(session, story_id)` function distinguishes between fetch failures and legitimate skips. Fetch failures (after all retry attempts are exhausted) raise a `RuntimeError`, which causes `def process_batch` to halt the loop immediately and return without advancing the state cursor past the failed story_id. The failed story is then retried on the next sync. Legitimate skips, such as deleted items or non-story item types (comments, jobs, polls), return `None` and the cursor safely advances past them since they will never become valid stories.

The `def enrich_story(session, configuration, title)` function calls both `def call_cortex_sentiment(session, account, title, pat_token, model, timeout)` and `def call_cortex_classification(session, account, title, pat_token, model, timeout)` to generate sentiment and topic enrichments. Cortex responses are Server-Sent Events parsed by `def parse_cortex_streaming_response(response)`.

Records with nested structures (such as the kids comment ID array) are flattened using `def flatten_dict(d, parent_key, sep)`. Lists are serialized to JSON strings for warehouse compatibility.


## Error handling

The `def fetch_data_with_retry(session, url, params, headers)` function implements exponential backoff retry logic for transient failures. Retryable HTTP status codes (429, 500, 502, 503, 504) trigger up to 3 retry attempts with increasing delays of 1, 2, and 4 seconds. Connection errors and timeouts are also retried.

Authentication and authorization failures (HTTP 401/403) surface immediately with a descriptive error message directing users to check their credentials and API scopes.

Cortex API errors are handled gracefully in `def call_cortex_sentiment(session, account, title, pat_token, model, timeout)` and `def call_cortex_classification(session, account, title, pat_token, model, timeout)`. Timeouts and request failures are logged as warnings and the story is stored without enrichment fields rather than failing the entire sync.

Configuration validation occurs before the sync starts in `def validate_configuration(configuration)`. Missing or invalid parameters raise descriptive ValueError messages.


## Tables created

The connector creates the `STORIES_ENRICHED` table.

### STORIES_ENRICHED

The `STORIES_ENRICHED` table consists of the following columns:

- `id` (INTEGER, primary key): Unique Hacker News story ID
- `submitted_by` (STRING): Author username who submitted the story (renamed from the Hacker News API field `by`, which collides with a reserved SQL keyword)
- `title` (STRING): Story title text
- `url` (STRING): URL of the linked article, if present
- `score` (INTEGER): Story score representing net upvotes
- `descendants` (INTEGER): Total comment count on the story
- `time` (INTEGER): Unix timestamp of when the story was submitted
- `type` (STRING): Item type, always "story" for this connector
- `text` (STRING): Story body text for Ask HN and similar text posts
- `kids` (STRING): JSON-serialized array of top-level comment IDs
- `cortex_sentiment` (STRING): AI-determined sentiment classification (positive, negative, or neutral)
- `cortex_sentiment_score` (FLOAT): Confidence score for the sentiment classification from 0.0 to 1.0
- `cortex_sentiment_reasoning` (STRING): Brief AI explanation for the sentiment classification
- `cortex_category` (STRING): AI-assigned topic category (AI, Security, Startups, Programming, Hardware, Science, Business, or Other)
- `cortex_category_confidence` (FLOAT): Confidence score for the topic classification from 0.0 to 1.0
- `cortex_keywords` (STRING): JSON-serialized array of key themes extracted from the title
- `cortex_model_used` (STRING): Name of the Cortex LLM model that generated the enrichments


## Cost considerations

Cortex AI enrichment costs scale with the number of enrichments per sync and the model selected. Each story requires two Cortex API calls (sentiment and classification), using approximately 200 tokens per story.

Example cost projections by model:
- mistral-large2 (recommended): approximately $0.008 per 50 stories, $0.016 per 100 stories, $0.16 per 1000 stories
- llama3.3-70b: approximately $0.005 per 50 stories, $0.01 per 100 stories, $0.10 per 1000 stories
- claude-sonnet-4-5: approximately $0.03 per 50 stories, $0.06 per 100 stories, $0.58 per 1000 stories

Use the `max_enrichments` configuration parameter to control costs during testing and production. Set `enable_cortex` to "false" to sync raw Hacker News data without any Cortex costs.

Snowflake Cortex rate limits are generous at 600 requests per minute and 600,000 tokens per minute, which is well above the throughput of this connector.


## Additional considerations

This example was contributed by [Kelly Kohlleffel](https://github.com/kellykohlleffel).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

Cortex model selection: The `cortex_model` parameter accepts any model available in your Snowflake Cortex region. Common options include mistral-large2 (recommended for balanced speed and accuracy), llama3.3-70b (fastest and lowest cost), and claude-sonnet-4-5 (highest accuracy). Check Snowflake documentation for model availability in your region.

Sync behavior: This connector uses incremental sync based on story IDs. On each sync, it fetches the current top stories list and only processes stories with IDs higher than the last synced ID. The recommended sync frequency is every 1 to 6 hours depending on your use case.
