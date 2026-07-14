# FDA Food Enforcement API Connector Tutorial

## What This Tutorial Does

This tutorial walks you through building a **Fivetran Connector** that automatically syncs food enforcement data from the FDA's openFDA API. You'll learn how to:

- Connect to FDA's public food enforcement database (no API key required to start)
- Automatically sync food recall and enforcement data with pagination
- Implement incremental syncing using date-based filtering
- Handle rate limiting and API quotas gracefully
- Flatten complex JSON structures into tabular format for analytics
- Process data in configurable batches with checkpointing

**Perfect for**: Data engineers, analysts, and developers who want to build reliable data pipelines for food safety and regulatory compliance data.

## Prerequisites

### Technical Requirements
- **Python 3.10 - 3.13+** installed on your machine
- **Basic Python knowledge** (functions, dictionaries, loops)
- **Fivetran Connector SDK** (we'll install this)
- **Git** (optional, for version control)

### API Access
- **FDA API Key** (optional but recommended)
  - Free registration at: https://open.fda.gov/apis/authentication/
  - Without key: 1,000 requests/day limit
  - With key: 120,000 requests/day limit

### Development Environment
- **Text editor** (Claude.ai or Claude code.)
- **Terminal/Command line** access
- **Internet connection** for API calls

## Required Files

You'll need these 3 core files to get started:

### 1. `connector.py` - Main Connector Logic
```python
# This is your main connector file
# Contains all the FDA Food Enforcement API integration logic
# Handles pagination, rate limiting, data processing, and flattening
```

### 2. `config.json` - Settings
```json
{
    "api_key": "",
    "base_url": "https://api.fda.gov/food/enforcement.json",
    "batch_size": "50",
    "rate_limit_pause": "0.5"
}
```

### 3. `requirements.txt` - Dependencies
```
fivetran-connector-sdk
requests
python-dateutil
pytz
```

## The Prompt

Here's the original prompt that created this connector:

> "Create a Fivetran Connector SDK solution for the FDA Food Enforcement API that includes:
> 
> - Incremental syncing using date-based filtering (report_date field)
> - Configurable batch processing with pagination support
> - Rate limiting and quota management for both authenticated and unauthenticated access
> - Automatic JSON flattening for complex nested structures
> - Date string normalization to ISO format
> - Robust error handling with retry logic
> - State management for reliable incremental syncs
> - Support for both authenticated and unauthenticated API access
> - Configurable batch limits for testing and production use
> - Logical processing of data from @notes.txt, which contains pertinent information about this API
> - Proper upserts based off of @fields.yaml, which contains response data structure
> - Follow the best practices outlined in @agents.md

> The connector should work with the FDA Food Enforcement API endpoint to fetch food recall and enforcement data."

## Quick Start

1. **Create your project folder**:
   ```bash
   mkdir fda-food-connector
   cd fda-food-connector
   ```

2. **Copy the agents.md** into a new cursor [notepad](https://docs.cursor.com/context/@-symbols/@-notepads) file 

3. **Copy the prompt** above into the chat

4. **Copy the output** configuration.json, requirements.txt, and connector.py into the project folder fda-drug-connector

5. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

6. **Test the connector**:
   ```bash
   fivetran debug --configuration config.json
   ```

7. **Check your data**:
   ```bash
   duckdb warehouse.db ".tables"
   duckdb warehouse.db "SELECT COUNT(*) FROM fda_food_enforcement;"
   ```

## What You'll Learn

- **API Integration**: How to work with REST APIs in data connectors
- **Incremental Sync**: Building efficient data pipelines using date-based filtering
- **Rate Limiting**: Respecting API limits while maximizing throughput
- **Data Transformation**: Flattening complex JSON structures for analytics
- **Error Handling**: Building resilient connectors with retry logic
- **State Management**: Tracking sync progress across multiple runs
- **Batch Processing**: Configurable batch sizes for optimal performance
- **Date Handling**: Normalizing date strings to ISO format

## Key Features

### 1. **Incremental Syncing**
- Uses `report_date` field for date-based filtering
- Only fetches new/updated records since last sync
- Maintains sync state across runs

### 2. **Flexible Rate Limiting**
- Automatic rate limit adjustment based on API key presence
- Configurable pause between requests
- Respects FDA API quotas (1,000/day without key, 120,000/day with key)

### 3. **Robust Error Handling**
- Retry logic with exponential backoff
- Graceful handling of API failures
- Comprehensive logging for debugging

### 4. **Data Processing**
- Automatic JSON flattening for nested structures
- Date string normalization to ISO format
- List-to-string conversion for tabular compatibility

### 5. **Configurable Batch Processing**
- Adjustable batch sizes for optimal performance
- Checkpointing after each batch
- Optional batch limits for testing

## Configuration Options

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `api_key` | FDA API key for authentication | "" | No |
| `base_url` | FDA Food Enforcement API endpoint | FDA URL | Yes |
| `batch_size` | Number of records per API request | 50 | No |
| `rate_limit_pause` | Seconds to pause between requests | 0.5 | No |

## Data Schema

The connector creates a single table: `fda_food_enforcement`

**Primary Keys**: `recall_number`, `event_id`

**Sample Fields**:
- `recall_number`: Unique identifier for the recall
- `event_id`: Event identifier
- `report_date`: Date when the recall was reported
- `recalling_firm`: Name of the recalling company
- `product_description`: Description of the recalled product
- `reason_for_recall`: Reason for the recall
- `classification`: Recall classification (Class I, II, or III)

## Next Steps

Once you've got the basic connector working:

1. **Get an API key** for higher rate limits
2. **Customize the configuration** for your data needs
3. **Adjust batch sizes** based on your data volume
4. **Set MAX_BATCHES to None** in connector.py for full dataset processing
5. **Implement custom data transformations** for your specific use case
6. **Deploy to production** with proper monitoring and alerting

## Troubleshooting

### Common Issues

1. **Rate Limit Errors**: Increase `rate_limit_pause` in configuration
2. **Memory Issues**: Decrease `batch_size` in configuration
3. **API Key Issues**: Ensure API key is properly formatted and valid
4. **Date Parsing Errors**: Check date format in API response

### Debug Mode

Run the connector in debug mode to see detailed logs:
```bash
fivetran debug --configuration config.json --verbose
```

## Need Help?

- **FDA Food Enforcement API Docs**: https://open.fda.gov/apis/food/enforcement/
- **Fivetran SDK Docs**: https://fivetran.com/docs/connector-sdk
- **API Status**: https://open.fda.gov/apis/status/
- **Food Recall Data**: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts

Happy building! 
