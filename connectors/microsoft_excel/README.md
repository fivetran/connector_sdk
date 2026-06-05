# Microsoft Excel File Example

## Connector overview

This connector fetches Microsoft Excel files from AWS S3 and processes them using three different methods to extract the data:
- `pandas` library,
- `python-calamine` library, and
- `openpyxl` library.

It's designed to efficiently handle Excel files of various sizes, providing flexibility for different data processing needs.

## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating System:  
  * Windows 10 or later  
  * macOS 13 (Ventura) or later

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/microsoft_excel
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Retrieves Excel file from AWS S3 buckets
- Processes Excel data using three different methods:
  - Pandas - This method loads the entire Excel file into memory, which is suitable for small to medium-sized files. Using this for large files is not recommended as it can lead to memory overflow errors.
  - Python-calamine - This method also loads the entire Excel file into memory, but it uses less memory compared to the `pandas` method with a significant improvement in processing speed. It uses the `calamine` engine and provides a balance between memory usage and performance. It is recommended for large files which are less than 1GB.
  - Openpyxl - This method uses the `openpyxl` library in read-only mode, which is more memory-efficient when processing large files but is significantly slower than `python-calamine`. It is suitable for very large files where memory usage is a concern as this method does not load the entire file into memory. It streams the data one row at a time to avoid memory overflow errors at the cost of processing speed.
- Creates three destination tables with identical schemas
- Handles proper cleanup of temporary files

## Configuration file

The connector requires AWS S3 credentials and file information:

```
{
  "aws_access_key_id": "<YOUR_AWS_ACCESS_KEY>",
  "aws_secret_access_key": "<YOUR_AWS_SECRET_KEY>",
  "region_name": "<YOUR_AWS_REGION>",
  "bucket_name": "<YOUR_S3_BUCKET>",
  "file_name": "<path/to/your/file.xlsx>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The connector requires the following Python packages:

```
boto3==1.38.14
pandas==2.2.3
openpyxl
python-calamine
```

In order to use the `calamine` engine with `pandas` library, you need to include the `python-calamine` package and ensure that the `pandas` version is `equal to or above 2.2`.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

This connector authenticates with AWS using an access key ID and secret access key. These credentials must have permissions to read objects from the specified S3 bucket. You can create these credentials in the AWS IAM console.  To set up authentication:  
- Create an IAM user with S3 read access
- Generate an access key and secret key for this user
- Add these credentials to your configuration.json file

## Data handling

The connector processes Excel files using three different methods:  
1. Pandas (Refer to `upsert_using_pandas` function): Loads the entire Excel file into memory, which is suitable for small to medium-sized files.  
2. Python-calamine (Refer to `upsert_using_calamine` function): Uses the calamine engine with pandas for faster processing. It loads the entire Excel file into memory but is more memory-efficient due to its optimized data structures. It provides a balance between memory usage and performance, making it suitable for large files. However, it is not recommended for files larger than 1GB as it can cause memory overflow errors.
3. Openpyxl (Refer to `upsert_using_openpyxl` function): Uses read-only mode for better memory efficiency when processing large files. It streams the data one row at a time, which avoids memory overflow errors but is significantly slower than the `python-calamine` method. It is suitable for very large files where memory usage is a concern.

Data from each method is identical, but upserted into separate tables with identical schemas.

## Error handling

The connector implements error handling in several areas:  
- Configuration validation: Checks if all required keys are present in the configuration.  
- File download: Captures exceptions during S3 file download and raises a RuntimeError with details.  
- Data processing: Wraps the data processing operations in a try-except block to capture and report errors.  

## Tables Created

The connector creates three tables in your destination:

- `excel_data_pandas` : Contains data upserted using the `pandas` library.
- `excel_data_calamine`: Contains data upserted using the `calamine` engine with `pandas`.
- `excel_data_openpyxl`: Contains data upserted using the `openpyxl` library.

The schema for all three tables is identical, with the following defined columns:
- `id`: Unique identifier for each row.
- `timestamp`: Record timestamp.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
