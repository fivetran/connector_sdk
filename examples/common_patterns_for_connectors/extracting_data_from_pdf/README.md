# Extracting Data from PDF Connector Example

## Connector overview
This connector extracts data from PDF invoice files stored in an AWS S3 bucket. It uses `pdfplumber` to read PDF content and applies regular expressions to extract structured information like invoice IDs, dates, amounts, and other invoice-related details. The extracted data is then upserted to the destination as structured tables.


## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/extracting_data_from_pdf
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Connects to AWS S3 to retrieve PDF invoice files
- Extracts text and tables from PDF documents using `pdfplumber`
- Uses regex pattern matching to extract structured invoice data
- Supports extraction of key invoice details including invoice ID, invoice date and due date, total amounts, contact information and amount in words
- Processes PDF files modified after the last successful sync


## Configuration file
The connector uses a configuration file to specify connection details and table information.

```json
{
  "aws_access_key_id": "<YOUR_AWS_S3_ACCESS_KEY>",
  "aws_secret_access_key": "<YOUR_AWS_S3_SECRET_KEY>",
  "region_name": "<YOUR_AWS_S3_REGION>",
  "bucket_name": "<YOUR_AWS_S3_BUCKET_NAME>",
  "prefix": "<YOUR_AWS_S3_FOLDER_NAME>" 
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The `requirements.txt` file specifies the Python libraries required by the connector. This connector uses the following library:

```
boto3
pdfplumber
python-dateutil
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
Authentication is handled through AWS credentials (access key and secret key) provided in the `configuration.json` file. These credentials must have permission to list and read objects from the specified S3 bucket.

Refer to `create_s3_client()` function in `connector.py` for the authentication implementation.


## Data handling
The connector processes PDF files through these steps:

- Lists PDF files in the specified S3 bucket prefix (refer to `get_invoice_files()` method)
- Downloads each PDF file to a temporary location (refer to `process_single_pdf()` method)
- Processes each PDF using the `PDFInvoiceExtractor` class to extract structured data
- Upserts the extracted data to the `invoices` table
- Cleans up temporary files after processing
- Checkpoints the last processed file to ensure incremental processing in subsequent syncs.


## Error handling
The connector implements several error handling mechanisms:

- Configuration validation to ensure all required parameters are present (Refer to `validate_configuration()` method)
- Try/except blocks around PDF processing to handle individual file failures gracefully
- Logging at different severity levels (info, warning, error) to provide visibility into connector operations
- Proper cleanup of temporary files in finally blocks to prevent resource leaks

## Tables created
- `INVOICES`: The connector creates a single table  with the following schema:

```json
{
  "table": "invoices",
  "primary_key": ["invoice_id"],
  "columns": {
    "invoice_id": "STRING",
    "invoice_date": "NAIVE_DATE",
    "due_date": "NAIVE_DATE",
    "total_amount": "FLOAT",
    "address": "STRING",
    "email": "STRING",
    "phone": "STRING",
    "code": "STRING",
    "vat_code": "STRING",
    "amount_in_words": "STRING",
    "pages": "INT",
    "discount": "FLOAT",
    "taxable_amount": "FLOAT",
    "tax_rate": "INT",
    "total_taxes": "FLOAT",
    "shipping": "FLOAT",
    "raw_text": "STRING"
  }
}
```


## Additional files
- `process_pdf.py` – Contains the `PDFInvoiceExtractor` class which handles PDF parsing and data extraction. This class implements various methods to extract text from PDFs, locate specific information using regex patterns, and normalize extracted data into standard formats.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
