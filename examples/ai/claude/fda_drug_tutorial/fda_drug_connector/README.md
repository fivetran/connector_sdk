# FDA Drug API Fivetran Connector

This connector dynamically discovers and syncs data from FDA Drug API endpoints with incremental sync support. It follows Fivetran Connector SDK best practices without using yield statements for easier adoption.

> Note: The agents.md file has been updated to reflect the recent [release](https://fivetran.com/docs/connector-sdk/changelog#august2025) where Yield is no longer required. This solution has been updated as well. Learn more about migrating to this new logic by going to the [Fivetran documentation](https://fivetran.com/docs/connector-sdk/tutorials/removing-yield-usage).

## Overview

The FDA Drug API Connector provides access to comprehensive drug-related data from the U.S. Food and Drug Administration, including:

- **NDC (National Drug Code)**: Drug product information and listings
- **Event**: Adverse event reports and safety data
- **Label**: Drug labeling information and package inserts
- **Enforcement**: Drug recall and enforcement actions

## Features

- **Dynamic Endpoint Discovery**: Automatically discovers available FDA Drug API endpoints
- **Incremental Sync Support**: Uses endpoint-specific date fields for efficient incremental updates
- **Rate Limiting**: Built-in rate limiting to respect FDA API limits
- **Flexible Data Processing**: Options for flattening nested data or creating child tables
- **Authentication Support**: Optional API key authentication for higher rate limits
- **Error Handling**: Comprehensive error handling and retry mechanisms
- **Checkpoint Management**: Regular checkpointing for reliable sync resumption

## Setup Instructions

### Prerequisites

- Python 3.10-3.13
- Fivetran Connector SDK
- FDA API key (optional but recommended)

### Installation

1. Clone or download this connector
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Create a `configuration.json` file with the following parameters:

```json
{
    "api_key": "your_fda_api_key_here",
    "base_url": "https://api.fda.gov/drug/",
    "requests_per_checkpoint": "10",
    "rate_limit_delay": "0.25",
    "flatten_nested": "true",
    "create_child_tables": "false",
    "max_api_calls_per_endpoint": "2"
}
```

#### Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `api_key` | String | No | "" | FDA API key for authentication (recommended for higher limits) |
| `base_url` | String | No | "https://api.fda.gov/drug/" | Base URL for FDA Drug API |
| `requests_per_checkpoint` | String | No | "10" | Number of requests before checkpointing |
| `rate_limit_delay` | String | No | "0.25" | Delay between requests in seconds |
| `flatten_nested` | String | No | "true" | Whether to flatten nested JSON structures |
| `create_child_tables` | String | No | "false" | Whether to create separate child tables for nested data |
| `max_api_calls_per_endpoint` | String | No | "2" | Maximum API calls per endpoint per sync |

## Testing

### Local Testing

Test the connector locally using the Fivetran debug command:

```bash
fivetran debug --configuration configuration.json
```

### Validation Steps

1. **Verify Schema**: Check that tables are created correctly
2. **Check Data Quality**: Review sample data in DuckDB warehouse.db
3. **Monitor Logs**: Review operation counts and error logs
4. **Validate Incremental Sync**: Test cursor progression and checkpointing

Expected log output:
```
Operation     | Calls
------------- + ------------
Upserts       | 44
Updates       | 0
Deletes       | 0
Truncates     | 0
SchemaChanges | 1
Checkpoints   | 1
```

## Data Schema

### Main Tables

The connector creates tables for each discovered endpoint:

- `fda_drug_ndc`: National Drug Code listings
- `fda_drug_event`: Adverse event reports
- `fda_drug_label`: Drug labeling information
- `fda_drug_enforcement`: Enforcement actions and recalls

### Child Tables (Optional)

When `create_child_tables` is enabled, additional tables are created:

- `fda_drug_{endpoint}_active_ingredients`
- `fda_drug_{endpoint}_packaging`
- `fda_drug_{endpoint}_openfda`
- `fda_drug_{endpoint}_route`

## Incremental Sync

The connector supports incremental sync using endpoint-specific date fields:

- **NDC**: `listing_expiration_date`
- **Event**: `receivedate`
- **Label**: `effective_time`
- **Enforcement**: `report_date`

Cursors are stored in the connector state and automatically managed.

## API Limits

### Without API Key
- 1,000 requests per day
- Basic rate limiting

### With API Key
- 120,000 requests per day
- Higher rate limits
- Better reliability

## Troubleshooting

### Common Issues

1. **Rate Limit Errors**
   - Increase `rate_limit_delay` in configuration
   - Reduce `max_api_calls_per_endpoint`
   - Consider getting an FDA API key

2. **Authentication Errors**
   - Verify API key format
   - Check API key permissions
   - Ensure proper base64 encoding

3. **Data Quality Issues**
   - Review flattened field names
   - Check for missing primary keys
   - Validate date field formats

4. **Memory Issues**
   - Reduce `requests_per_checkpoint`
   - Enable `create_child_tables` for large nested data
   - Monitor checkpoint frequency

### Debug Steps

1. Enable detailed logging
2. Test individual endpoints
3. Verify API connectivity
4. Check configuration parameters
5. Review error messages in logs

## Best Practices

### Performance Optimization

- Use appropriate `requests_per_checkpoint` values
- Enable child tables for complex nested data
- Monitor API quota usage
- Implement proper error handling

### Data Quality

- Validate primary key generation
- Handle missing date fields gracefully
- Implement data type validation
- Monitor schema evolution

### Monitoring

- Track API call usage
- Monitor checkpoint frequency
- Review error rates
- Validate data completeness

## References

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [SDK Examples Repository](https://github.com/fivetran/connector_sdk/tree/main/examples)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [FDA Drug API Documentation](https://open.fda.gov/apis/drug/)

## Known Limitations

- Limited to FDA Drug API endpoints
- Rate limits apply based on authentication
- Some endpoints may have data availability issues
- Date field formats vary by endpoint

## Support

For issues related to:
- **Fivetran Connector SDK**: Refer to official documentation
- **FDA API**: Contact FDA support
- **This Connector**: Review troubleshooting section above
