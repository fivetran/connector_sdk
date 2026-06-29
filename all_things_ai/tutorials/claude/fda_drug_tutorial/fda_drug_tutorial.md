# FDA Drug API Connector Tutorial

## What This Tutorial Does

This tutorial walks you through building a **Fivetran Connector** that automatically syncs data from the FDA Drug API. You'll learn how to:

- Connect to FDA's public drug database (no API key required to start)
- Automatically discover and sync from multiple endpoints (NDC, events, labels, enforcement)
- Implement incremental syncing to only fetch new/updated data
- Handle rate limiting and API quotas gracefully
- Structure data for analytics with flattened tables or child relationships

**Perfect for**: Data engineers, analysts, and developers who want to build reliable data pipelines for pharmaceutical data.

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
# Contains all the FDA API integration logic
# Handles endpoint discovery, rate limiting, data processing
```

### 2. `configuration.json` - Settings
```json
{
  "api_key": "",
  "base_url": "https://api.fda.gov/drug/",
  "requests_per_checkpoint": "2",
  "rate_limit_delay": "0.25",
  "flatten_nested": "true",
  "create_child_tables": "false"
}
```

### 3. `requirements.txt` - Dependencies
```
fivetran-connector-sdk
requests
```

## The Prompt

Here's the original prompt that created this connector:

> "Create a Fivetran Connector SDK solution for the FDA Drug API that includes:
> 
> - Dynamic endpoint discovery (automatically finds available endpoints)
> - Incremental syncing using date fields
> - Configurable data flattening (flattened tables vs child tables)
> - Rate limiting and quota management
> - Support for both authenticated and unauthenticated access
> - Robust state management for reliable incremental syncs
> - Logical processing of data from @notes.txt, which contains pertinent information about this API
> - Proper upserts based off of @fields.yaml, which contains response data structure
> - Follow the best practices outlined in @CLAUDE.md

> The connector should work with the FDA Drug API endpoints: NDC (National Drug Code), adverse events, drug labeling, and enforcement reports."

## Quick Start

1. **Create your project folder**:
   ```bash
   mkdir fda-drug-connector
   cd fda-drug-connector
   ```

2. **Copy the prompt** above into the chat

3. **Copy the output** configuration.json, requirements.txt, and connector.py into the project folder fda-drug-connector

4. **Install dependencies**:
   ```bash
   pip install fivetran-connector-sdk
   pip install -r requirements.txt
   ```

5. **Test the connector**:
   ```bash
   fivetran debug --configuration configuration.json
   ```

6. **Check your data**:
   ```bash
   duckdb warehouse.db ".tables"
   duckdb warehouse.db "SELECT COUNT(*) FROM fda_drug_ndc;"
   ```

## What You'll Learn

- **API Integration**: How to work with REST APIs in data connectors
- **Incremental Sync**: Building efficient data pipelines that only fetch new data
- **Rate Limiting**: Respecting API limits while maximizing throughput
- **Data Transformation**: Flattening complex JSON structures for analytics
- **Error Handling**: Building resilient connectors that handle API failures
- **State Management**: Tracking sync progress across multiple runs

## Next Steps

Once you've got the basic connector working:

1. **Get an API key** for higher rate limits
2. **Customize the configuration** for your data needs
3. **Add more endpoints** by extending the `KNOWN_ENDPOINTS` list
4. **Implement custom data transformations** for your specific use case
5. **Deploy to production** with proper monitoring and alerting

## Need Help?

- **FDA API Docs**: https://open.fda.gov/apis/
- **Fivetran SDK Docs**: https://fivetran.com/docs/connector-sdk
- **API Status**: https://open.fda.gov/apis/status/

Happy building!
