# FDA Food Enforcement API Connector

This connector fetches data from the FDA Food Enforcement API and upserts it into your Fivetran destination. The connector supports both API key and no API key authentication, configurable batch sizes, and incremental syncs.

## Note: The agents.md file has been updated to reflect the recent [release](https://fivetran.com/docs/connector-sdk/changelog#august2025) where Yield is no longer required. This solution has been updated as well. Learn more about migrating to this new logic by going to the [Fivetran documentation](https://fivetran.com/docs/connector-sdk/tutorials/removing-yield-usage).

## Overview

The FDA Food Enforcement API provides access to food recall and enforcement data from the U.S. Food and Drug Administration. This connector implements best practices for data ingestion, including:

- Direct operation calls (no yield statements) for easier adoption
- Proper state management and checkpointing
- Rate limiting and error handling
- Support for both full and incremental syncs
- AI/ML data optimization patterns

## Features

- **Flexible Authentication**: Supports both API key and no API key authentication
- **Configurable Data Volume**: Set maximum records per sync
- **Date Filtering**: Optional date range filtering for incremental syncs
- **Rate Limiting**: Built-in rate limiting for FDA API compliance
- **Error Handling**: Comprehensive error handling and logging
- **State Management**: Proper checkpointing for resumable syncs
- **Data Flattening**: Handles nested JSON structures automatically

## Setup Instructions

### Prerequisites

- Python 3.10-3.13
- Fivetran Connector SDK
- Valid FDA API key (optional but recommended)

### Installation

1. Clone or download this connector
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Edit the `configuration.json` file with your settings:

```json
{
    "max_records": "100",
    "use_api_key": "false",
    "api_key": "",
    "lookback_days": "30",
    "use_date_filter": "false"
}
```

#### Configuration Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `max_records` | string | Yes | Maximum number of records to fetch per sync (default: "100") |
| `use_api_key` | string | Yes | Whether to use API key authentication ("true" or "false") |
| `api_key` | string | No | FDA API key (required if use_api_key is "true") |
| `lookback_days` | string | No | Number of days to look back for date filtering (default: "30") |
| `use_date_filter` | string | No | Whether to use date filtering ("true" or "false") |

## Testing

### Local Testing

Test the connector locally using the Fivetran debug command:

```bash
fivetran debug --configuration configuration.json
```

### Expected Output

The connector will create a `warehouse.db` file with the following table:

- `fda_food_enforcement_reports`: Contains FDA food enforcement data

### Sample Log Output

```
Operation     | Calls
------------- + ------------
Upserts       | 100
Updates       | 0
Deletes       | 0
Truncates     | 0
SchemaChanges | 1
Checkpoints   | 1
```

## Data Schema

### fda_food_enforcement_reports

Primary Key: `event_id`

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | STRING | Unique identifier for the enforcement event |
| `recall_number` | STRING | FDA recall number |
| `product_description` | STRING | Description of the recalled product |
| `reason_for_recall` | STRING | Reason for the recall |
| `recall_initiation_date` | STRING | Date when recall was initiated |
| `recall_status` | STRING | Current status of the recall |
| `distribution_pattern` | STRING | Geographic distribution pattern |
| `product_quantity` | STRING | Quantity of product recalled |
| `code_info` | STRING | Product codes and identifiers |
| `voluntary_mandated` | STRING | Whether recall was voluntary or mandated |
| `initial_firm_notification` | STRING | Initial notification details |
| `event_id_original` | STRING | Original event ID |
| `more_code_info` | STRING | Additional code information |
| `recall_classification` | STRING | Classification of the recall |
| `product_type` | STRING | Type of product |
| `report_date` | STRING | Date the report was filed |
| `openfda` | STRING | OpenFDA data (JSON string) |
| `classification` | STRING | Classification details |
| `recalling_firm` | STRING | Name of the recalling firm |
| `recall_date` | STRING | Date of the recall |
| `city` | STRING | City where recall occurred |
| `state` | STRING | State where recall occurred |
| `country` | STRING | Country where recall occurred |
| `_fivetran_synced` | STRING | Fivetran sync timestamp |
| `_fivetran_batch_id` | STRING | Fivetran batch identifier |
| `_data_source` | STRING | Data source identifier |

## Best Practices Implementation

This connector follows Fivetran Connector SDK best practices:

### Direct Operations
- Uses `op.upsert()` directly without yield statements
- Implements proper checkpointing with `op.checkpoint()`
- Handles state management for incremental syncs

### Error Handling
- Comprehensive exception handling
- Proper logging at appropriate levels
- Graceful failure handling

### Performance Optimization
- Batch processing for large datasets
- Rate limiting for API compliance
- Efficient data flattening
- Memory-conscious data handling

### State Management
- Checkpointing after each batch
- Resumable syncs from last checkpoint
- State persistence across runs

## Troubleshooting

### Common Issues

1. **API Rate Limiting**
   - Without API key: 240 requests/minute, 1000 requests/day
   - With API key: Higher limits available
   - Solution: Enable API key authentication

2. **Configuration Errors**
   - Ensure all required parameters are provided
   - Validate parameter types (strings only)
   - Check API key format if using authentication

3. **Data Quality Issues**
   - Nested JSON fields are automatically flattened
   - Empty arrays and objects are handled gracefully
   - Missing fields are populated with empty strings

### Debug Steps

1. Check configuration.json format
2. Verify API key validity (if using)
3. Review connector logs for errors
4. Test with smaller max_records value
5. Check network connectivity to FDA API

### Log Analysis

- `INFO`: Status updates, progress, cursors
- `WARNING`: Rate limits, potential issues
- `ERROR`: Errors, failures, critical issues

## API Reference

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [SDK Examples Repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [FDA Food Enforcement API](https://open.fda.gov/apis/food-enforcement/)

## Limitations

- FDA API has rate limits (240 requests/minute without API key)
- Maximum 1000 records per API request
- Date filtering may not work in all cases
- Some fields may contain nested JSON structures

## Support

For issues related to:
- **Fivetran Connector SDK**: Refer to official documentation
- **FDA API**: Check FDA API documentation and status
- **This Connector**: Review logs and troubleshooting section

## Version History

- **v1.0**: Initial release with yield-based implementation
- **v2.0**: Refactored to use direct operations (no yield) following best practices
