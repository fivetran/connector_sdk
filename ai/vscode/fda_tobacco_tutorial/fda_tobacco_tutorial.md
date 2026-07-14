# FDA Tobacco Problem API Connector Tutorial

## What This Tutorial Does

This tutorial walks you through building a **Fivetran Connector** that automatically syncs tobacco problem data from the FDA's openFDA API. You'll learn how to:

- Connect to FDA's public tobacco problem database (no API key required)
- Automatically sync tobacco problem reports with pagination
- Implement basic data processing with JSON flattening
- Handle API responses and error scenarios gracefully
- Flatten complex JSON structures into tabular format for analytics
- Process data in configurable batches with checkpointing

**Perfect for**: Data engineers, analysts, and developers who want to build reliable data pipelines for tobacco regulation and public health data.

## Prerequisites

### Technical Requirements
- **Python 3.10 - 3.13+** installed on your machine
- **Basic Python knowledge** (functions, dictionaries, loops)
- **Fivetran Connector SDK** (we'll install this)
- **Git** (optional, for version control)

### API Access
- **FDA API Key** (optional)
  - Free registration at: https://open.fda.gov/apis/authentication/
  - Without key: 1,000 requests/day limit
  - With key: 120,000 requests/day limit
- **Public endpoint** available without authentication

### Development Environment
- **Text editor** (Claude.ai or Claude code.)
- **Terminal/Command line** access
- **Internet connection** for API calls

## Required Files

You'll need these 3 core files to get started:

### 1. `connector.py` - Main Connector Logic
```python
# This is your main connector file
# Contains all the FDA Tobacco Problem API integration logic
# Handles pagination, data processing, and flattening
```

### 2. `config.json` - Settings
```json
{
    "api_key": "",
    "base_url": "https://api.fda.gov/tobacco/problem.json",
    "batch_size": "10",
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

> "Create a Fivetran Connector SDK solution for the FDA Tobacco Problem API that includes:
> 
> - Basic data fetching from the FDA Tobacco Problem API endpoint
> - Configurable batch processing with pagination support
> - Automatic JSON flattening for complex nested structures
> - Robust error handling with proper logging
> - State management for reliable data syncs
> - Support for public API access (no authentication required)
> - Configurable batch limits for testing and production use
> 
> The connector should work with the FDA Tobacco Problem API endpoint to fetch tobacco problem report data."

## Quick Start

1. **Create your project folder**:
   ```bash
   mkdir fda-tobacco-connector
   cd fda-tobacco-connector
   ```

2. **Copy the three files** above into your folder

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Test the connector**:
   ```bash
   fivetran debug --configuration config.json
   ```

5. **Check your data**:
   ```bash
   duckdb warehouse.db ".tables"
   duckdb warehouse.db "SELECT COUNT(*) FROM tobacco_problem;"
   ```

## What You'll Learn

- **API Integration**: How to work with REST APIs in data connectors
- **Data Processing**: Building efficient data pipelines for tobacco regulation data
- **JSON Flattening**: Converting complex nested structures to tabular format
- **Error Handling**: Building resilient connectors with proper logging
- **State Management**: Tracking sync progress across multiple runs
- **Batch Processing**: Configurable batch sizes for optimal performance
- **Data Validation**: Ensuring data quality and completeness

## Key Features

### 1. **Simple Data Fetching**
- Fetches tobacco problem reports from FDA API
- Configurable batch size (currently set to 10 records)
- No authentication required for basic access

### 2. **JSON Flattening**
- Automatic flattening of nested JSON structures
- List-to-string conversion for tabular compatibility
- Preserves all data fields in flattened format

### 3. **Robust Error Handling**
- Comprehensive exception handling
- Detailed logging for debugging
- Graceful handling of API failures

### 4. **Data Processing**
- Automatic JSON flattening for nested structures
- Primary key validation (report_id)
- Skip records without required primary keys

### 5. **State Management**
- Checkpointing after each batch
- State tracking for sync progress
- Reliable incremental syncs

## Configuration Options

| Parameter | Description | Default | Required |
|-----------|-------------|---------|----------|
| `api_key` | FDA API key for authentication | "" | No |
| `base_url` | FDA Tobacco Problem API endpoint | FDA URL | Yes |
| `batch_size` | Number of records per API request | 10 | No |
| `rate_limit_pause` | Seconds to pause between requests | 0.5 | No |

## Data Schema

The connector creates a single table: `tobacco_problem`

**Primary Keys**: `report_id`

**Sample Fields**:
- `report_id`: Unique identifier for the tobacco problem report
- `date_submitted`: Date when the problem was submitted
- `product_name`: Name of the tobacco product
- `problem_description`: Description of the reported problem
- `manufacturer`: Name of the product manufacturer
- `category`: Category of the tobacco product
- `subcategory`: Subcategory of the tobacco product

## Code Structure

### Main Functions

1. **`flatten_dict()`**: Recursively flattens nested JSON structures
2. **`schema()`**: Defines table structure with primary keys
3. **`update()`**: Main data fetching and processing logic

### Key Implementation Details

```python
# JSON flattening for nested structures
def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """Recursively flattens a nested dictionary."""
    # Converts nested JSON to flat structure suitable for database storage

# Schema definition
def schema(configuration: dict):
    return [
        {"table": "tobacco_problem", "primary_key": ["report_id"]}
    ]

# Main update function
def update(configuration: dict, state: dict = None):
    # Fetches data from FDA API
    # Processes and flattens JSON data
    # Yields upsert operations
    # Checkpoints state after processing
```

## Next Steps

Once you've got the basic connector working:

1. **Get an API key** for higher rate limits
2. **Customize the configuration** for your data needs
3. **Adjust batch sizes** based on your data volume
4. **Implement incremental syncing** using date-based filtering
5. **Add rate limiting** for production use
6. **Implement custom data transformations** for your specific use case
7. **Deploy to production** with proper monitoring and alerting

## Advanced Enhancements

### 1. **Incremental Syncing**
```python
# Add date-based filtering for incremental syncs
params = {
    "limit": batch_size,
    "search": f"date_submitted:[{last_sync_date} TO NOW]"
}
```

### 2. **Rate Limiting**
```python
# Add rate limiting for production use
import time
time.sleep(rate_limit_pause)
```

### 3. **Enhanced Error Handling**
```python
# Add retry logic with exponential backoff
def fetch_with_retry(url, params, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)
```

### 4. **Data Validation**
```python
# Add data validation for required fields
def validate_record(record):
    required_fields = ['report_id', 'date_submitted']
    return all(field in record for field in required_fields)
```

## Troubleshooting

### Common Issues

1. **Rate Limit Errors**: Increase `rate_limit_pause` in configuration
2. **Memory Issues**: Decrease `batch_size` in configuration
3. **API Key Issues**: Ensure API key is properly formatted and valid
4. **Missing Primary Keys**: Check that records contain `report_id` field
5. **JSON Parsing Errors**: Verify API response format

### Debug Mode

Run the connector in debug mode to see detailed logs:
```bash
fivetran debug --configuration config.json --verbose
```

### Log Analysis

Check the logs for:
- Number of records fetched
- Any skipped records (missing report_id)
- API response status
- Processing errors

## Performance Optimization

### 1. **Batch Size Tuning**
- Start with small batches (10-50 records)
- Increase gradually based on API performance
- Monitor memory usage and processing time

### 2. **Rate Limiting**
- Respect FDA API rate limits
- Implement exponential backoff for retries
- Use API key for higher limits when available

### 3. **Data Processing**
- Optimize JSON flattening for large datasets
- Consider parallel processing for multiple endpoints
- Implement data validation early in the pipeline

## Data Quality Considerations

### 1. **Data Validation**
- Ensure required fields are present
- Validate data types and formats
- Handle missing or null values appropriately

### 2. **Data Transformation**
- Normalize date formats
- Standardize text fields
- Handle special characters and encoding

### 3. **Data Completeness**
- Track missing records
- Implement data quality metrics
- Set up alerts for data quality issues

## Monitoring and Alerting

### 1. **Sync Monitoring**
- Track sync success/failure rates
- Monitor processing time and throughput
- Alert on sync failures or data quality issues

### 2. **API Monitoring**
- Monitor API response times
- Track rate limit usage
- Alert on API errors or downtime

### 3. **Data Quality Monitoring**
- Monitor record counts and completeness
- Track data freshness
- Alert on data quality degradation

## Need Help?

- **FDA Tobacco Problem API Docs**: https://open.fda.gov/apis/tobacco/problem/
- **Fivetran SDK Docs**: https://fivetran.com/docs/connector-sdk
- **API Status**: https://open.fda.gov/apis/status/
- **Tobacco Product Data**: https://www.fda.gov/tobacco-products

## Related Resources

- **FDA Food Enforcement Tutorial**: Similar connector for food recall data
- **Fivetran Connector Examples**: More connector patterns and examples
- **Python Requests Library**: HTTP library documentation
- **JSON Processing**: Python JSON handling best practices

Happy building! 
