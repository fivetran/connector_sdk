# SharePoint Multi-Site File Data Connector (Connector SDK)

## Overview
This connector extracts CSV and Excel data from multiple SharePoint sites and loads it into a structured format.

## Key Features
- Multi-site ingestion
- CSV and Excel parsing
- Row-level data extraction
- Incremental sync using lastModifiedDateTime
- Deletion handling
- Recursive folder support

## Tables

### files
Metadata about each file.

### file_rows
Row-level data extracted from files.

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Configure:
```
{
  "tenant_id": "YOUR_TENANT_ID",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "site_urls": "https://tenant.sharepoint.com/sites/site1,https://tenant.sharepoint.com/sites/site2"
}
```

3. Run:
```
fivetran debug --configuration configuration.json
```

## Notes
- Supports .csv, .xlsx, .xlsm
- Does not support raw unstructured files (PDF, images)
- Folder path must be consistent across sites

## Summary
Enables scalable multi-site SharePoint ingestion with structured file extraction.
