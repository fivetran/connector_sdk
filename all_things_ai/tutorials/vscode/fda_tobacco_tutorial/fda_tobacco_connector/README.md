# FDA Tobacco Problem Reports API Connector

This Fivetran Connector SDK connector fetches data from the FDA Tobacco Problem Reports API and upserts it into your destination using the Fivetran Connector SDK.

## Note: The agents.md file has been updated to reflect the recent [release](https://fivetran.com/docs/connector-sdk/changelog#august2025) where Yield is no longer required. This solution has been updated as well. Learn more about migrating to this new logic by going to the [Fivetran documentation](https://fivetran.com/docs/connector-sdk/tutorials/removing-yield-usage).

## Overview

The FDA Tobacco Problem Reports API provides public health data on tobacco product problems and health issues. This connector:

- Fetches tobacco problem reports with comprehensive health and product data
- Implements proper rate limiting (240 requests/minute with API key)
- Supports both full and incremental syncs
- Includes test mode for development and validation
- Checkpoints every 100 rows for reliable data processing
- Handles pagination efficiently (up to 1,000 records per API call)

## Data Schema

The connector creates a single table: `fda_tobacco_problem_reports`

**Primary Key**: `report_id`

**Columns**:
- `report_id`: Unique identifier for each report
- `date_submitted`: Date when the report was submitted
- `nonuser_affected`: Whether non-users were affected
- `reported_health_problems`: JSON array of health problems (stored as JSON string)
- `number_health_problems`: Count of health problems
- `reported_product_problems`: JSON array of product problems (stored as JSON string)
- `number_product_problems`: Count of product problems
- `number_tobacco_products`: Count of tobacco products involved
- `tobacco_products`: JSON array of tobacco product types (stored as JSON string)
- `sync_timestamp`: When the record was synced

## Configuration

All configuration values must be strings. Create a `configuration.json` file with the following parameters:

### Required Parameters

- `base_url`: FDA API endpoint (default: "https://api.fda.gov/tobacco/problem.json")
- `rate_limit`: Requests per minute (default: "240")
- `page_size`: Records per API call, max 1000 (default: "1000")
- `checkpoint_interval`: Rows between checkpoints (default: "100")

### Optional Parameters

- `api_key`: FDA API key for higher rate limits (default: "")
- `test_mode`: Enable test mode with limited records (default: "false")
- `test_limit`: Maximum records in test mode (default: "10")
- `sync_frequency_minutes`: Sync frequency in minutes (default: "1440" - daily)

### Example Configuration

```json
{
    "base_url": "https://api.fda.gov/tobacco/problem.json",
    "api_key": "your_api_key_here",
    "rate_limit": "240",
    "page_size": "1000",
    "checkpoint_interval": "100",
    "test_mode": "false",
    "test_limit": "10",
    "sync_frequency_minutes": "1440"
}
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Authentication

- **Without API Key**: Limited to 1,000 requests/day per IP
- **With API Key**: Up to 120,000 requests/day
- Get your free API key from [FDA Open Data](https://open.fda.gov/apis/authentication/)

### 3. Test the Connector

#### Using Python Debug Mode

```bash
python connector.py
```

#### Using Fivetran CLI

```bash
fivetran debug --configuration configuration.json
```

## Testing and Validation

### Test Mode

Enable test mode to validate with a small dataset:

```json
{
    "test_mode": "true",
    "test_limit": "10"
}
```

### Validation Steps

1. **Check Logs**: Verify successful API calls and data processing
2. **Review Operations**: Confirm upserts and checkpoints are working
3. **Data Quality**: Validate record counts and data completeness
4. **Rate Limiting**: Ensure requests respect rate limits

### Expected Output

```
Operation     | Calls
------------- + ------------
Upserts       | 10
Updates       | 0
Deletes       | 0
Truncates     | 0
SchemaChanges | 1
Checkpoints   | 1
```

## Features

### Rate Limiting

- **Default**: 240 requests/minute
- **Configurable**: Adjust via `rate_limit` parameter
- **Automatic**: Built-in delays between requests
- **Retry Logic**: Exponential backoff for rate limit errors

### Pagination

- **Efficient**: Processes up to 1,000 records per API call
- **Configurable**: Adjust page size via `page_size` parameter
- **Automatic**: Handles pagination seamlessly

### Incremental Syncs

- **State Management**: Tracks last sync date and report ID
- **Resume Capability**: Continues from last successful sync
- **Checkpointing**: Saves progress every 100 rows

### Error Handling

- **Retry Logic**: Automatic retries with exponential backoff
- **Rate Limit Handling**: Respects API limits and waits appropriately
- **Comprehensive Logging**: Detailed error information and debugging

## Best Practices

### Performance

- Use appropriate page sizes (1000 is optimal)
- Enable test mode for development
- Monitor rate limit usage
- Implement proper error handling

### Data Quality

- Validate API responses
- Handle null values gracefully
- Process arrays as JSON strings
- Add sync timestamps for tracking

### Monitoring

- Check operation counts
- Review error logs
- Monitor sync completion times
- Track rate limit usage

## Troubleshooting

### Common Issues

1. **Rate Limit Exceeded**
   - Check `rate_limit` configuration
   - Verify API key is valid
   - Reduce page size if needed

2. **Authentication Errors**
   - Verify API key format
   - Check API key permissions
   - Test API access manually

3. **Data Processing Errors**
   - Review API response format
   - Check data validation logic
   - Verify schema configuration

### Debug Steps

1. Enable test mode with small limits
2. Check configuration validation
3. Review API response structure
4. Monitor rate limiting behavior
5. Validate checkpoint operations

### Log Analysis

- **INFO**: Normal operations and progress
- **WARNING**: Rate limits and retries
- **ERROR**: Errors and failures

## API Reference

### FDA Tobacco Problem Reports API

- **Base URL**: https://api.fda.gov/tobacco/problem.json
- **Documentation**: https://open.fda.gov/apis/tobacco-problem-reports/
- **Rate Limits**: 240 requests/minute, 120,000 requests/day with API key
- **Data Format**: JSON with meta and results sections

### Search Parameters

- **Date Ranges**: `search=date_submitted:[YYYYMMDD+TO+YYYYMMDD]`
- **Pagination**: `limit` and `skip` parameters
- **Product Types**: Filter by specific tobacco products
- **Health Problems**: Filter by reported health issues

## Support and Maintenance

### Monitoring

- Regular log review
- Performance metrics tracking
- Error rate monitoring
- Rate limit usage analysis

### Updates

- Monitor API changes
- Review rate limit adjustments
- Update connector as needed
- Test with new data formats

### Escalation

1. Check connector logs
2. Verify API connectivity
3. Review configuration
4. Contact support if needed

## References

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [SDK Examples Repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [FDA Open Data API](https://open.fda.gov/apis/)
- [Tobacco Problem Reports API](https://open.fda.gov/apis/tobacco-problem-reports/)

## License

This connector is provided as-is for use with the Fivetran Connector SDK. Please refer to the FDA Open Data terms of service for API usage requirements.
