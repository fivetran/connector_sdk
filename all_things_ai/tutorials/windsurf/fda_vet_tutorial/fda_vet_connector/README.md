# FDA Veterinary Adverse Event Reporting System (FAERS) Connector

This connector fetches veterinary adverse event data from the FDA's public API and syncs it to your Fivetran destination. It demonstrates best practices for building Fivetran connectors using the Connector SDK.

## Note: The agents.md file has been updated to reflect the recent [release](https://fivetran.com/docs/connector-sdk/changelog#august2025) where Yield is no longer required. This solution has been updated as well. Learn more about migrating to this new logic by going to the [Fivetran documentation](https://fivetran.com/docs/connector-sdk/tutorials/removing-yield-usage).

## Overview

The FDA Veterinary Adverse Event Reporting System (FAERS) contains reports of adverse events and medication errors submitted to the FDA. This connector provides access to this valuable dataset for analysis and monitoring purposes.

## Features

- **Public API Access**: No authentication required for FDA's public endpoints
- **Incremental Sync**: Supports incremental data synchronization with state management
- **Error Handling**: Comprehensive error handling and logging
- **Configurable Batch Size**: Adjustable batch size for optimal performance
- **Date Filtering**: Optional date-based filtering for targeted data extraction
- **Data Flattening**: Automatically flattens nested JSON structures for easier analysis

## Setup Instructions

### Prerequisites

- Python 3.10-3.13
- Fivetran Connector SDK
- Access to Fivetran destination

### Installation

1. Clone or download this connector to your local environment
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Edit the `configuration.json` file with your desired settings:

```json
{
    "batch_size": "100",
    "start_date": ""
}
```

#### Configuration Parameters

- **batch_size** (string): Number of records to fetch per API call (default: "100")
- **start_date** (string): Optional start date for filtering records in YYYYMMDD format (e.g., "20240101")

## Testing

### Local Testing

Test the connector locally using the Fivetran debug command:

```bash
fivetran debug --configuration configuration.json
```

### Expected Output

The connector will create a `warehouse.db` file containing the synced data. You can inspect the data using:

```bash
sqlite3 warehouse.db "SELECT COUNT(*) FROM events;"
sqlite3 warehouse.db "SELECT * FROM events LIMIT 5;"
```

### Operation Summary

After running the connector, you should see an operation summary like:

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

### Events Table

The connector creates an `events` table with the following structure:

- **Primary Key**: `unique_aer_id_number`
- **Data Types**: Automatically inferred by Fivetran
- **Content**: Flattened veterinary adverse event data from FDA API

### Sample Data Fields

- `unique_aer_id_number`: Unique identifier for the adverse event report
- `receivedate`: Date the report was received by FDA
- `patient`: Patient information (age, weight, species, etc.)
- `drug`: Drug information (name, dosage, route, etc.)
- `reaction`: Adverse reactions reported
- `outcome`: Patient outcome information

## Best Practices Implementation

This connector follows Fivetran Connector SDK best practices:

### 1. No Yield Statements
- Uses direct operation calls (`op.upsert()`, `op.checkpoint()`)
- Eliminates complexity of generator functions
- Easier to understand and maintain

### 2. Proper State Management
- Implements checkpointing for incremental syncs
- Tracks processing statistics
- Maintains sync state across runs

### 3. Error Handling
- Comprehensive exception handling
- Detailed logging at appropriate levels
- Graceful failure recovery

### 4. Performance Optimization
- Configurable batch sizes
- Efficient data processing
- Memory-conscious implementation

### 5. Documentation
- Clear docstrings and comments
- Comprehensive README
- Configuration examples

## Troubleshooting

### Common Issues

1. **API Rate Limits**
   - Reduce `batch_size` in configuration
   - Monitor logs for rate limit warnings

2. **Memory Issues**
   - Decrease batch size if processing large datasets
   - Monitor memory usage during sync

3. **Network Timeouts**
   - Check internet connectivity
   - Verify FDA API availability

### Debug Steps

1. Check connector logs for error messages
2. Verify configuration.json format
3. Test API connectivity manually
4. Review warehouse.db for data completeness

### Log Analysis

Look for these log messages:
- `INFO`: Normal operation progress
- `WARNING`: Potential issues (rate limits, empty responses)
- `ERROR`: Critical errors requiring attention

## API Reference

### FDA Veterinary API
- **Base URL**: `https://api.fda.gov/animalandveterinary/event.json`
- **Documentation**: [FDA API Documentation](https://open.fda.gov/apis/drug/event/)
- **Rate Limits**: Public API with reasonable limits
- **Authentication**: None required for public endpoints

### Fivetran Connector SDK
- **Documentation**: [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- **Examples**: [SDK Examples Repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples)
- **Best Practices**: [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)

## Limitations and Constraints

- **Public API**: Subject to FDA's API availability and rate limits
- **Data Volume**: Large datasets may require multiple sync runs
- **Schema Evolution**: FDA may add new fields over time
- **Historical Data**: Limited by FDA's data retention policies

## Support and Maintenance

### Monitoring
- Review logs regularly for errors
- Monitor sync performance metrics
- Track data quality and completeness

### Updates
- Monitor FDA API changes
- Update connector for new data fields
- Test thoroughly before production deployment

## Contributing

When modifying this connector:

1. Follow Fivetran Connector SDK best practices
2. Maintain comprehensive documentation
3. Test thoroughly with debug command
4. Update README for any new features
5. Ensure backward compatibility

## License

This connector is provided as-is for educational and development purposes. Please review FDA's terms of service for production use.
