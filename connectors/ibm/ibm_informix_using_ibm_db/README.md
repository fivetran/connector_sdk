# IBM Informix Connector using ibm_db

## **Connector Overview**

This connector uses the native `ibm_db` Python package provided by IBM to connect to IBM Informix databases. This is the recommended approach for most use cases as it provides:
- Direct interface to IBM Informix databases
- Full compatibility with IBM Informix features

## **Requirements**

* [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
  
## **Getting Started**

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/ibm/ibm_informix_using_ibm_db
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## **Features**

- Native connection to IBM Informix databases using the `ibm_db` python package.
- Proper handling of datetime values
- Incremental sync using `state` and `op.checkpoint()`

## **Configuration File**

The connector requires the following configuration parameters:

```
{
  "hostname": "<YOUR_HOSTNAME>",
  "port": "<YOUR_PORT_NUMBER>",
  "database": "<YOUR_DATABASE_NAME>",
  "username": "<YOUR_USERNAME>",
  "password": "<YOUR_PASSWORD>",
  "table_name": "<YOUR_TABLE_NAME>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## **Requirements File**

This connector requires the following Python packages:

```
ibm_db
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## **Authentication**

The connector uses username and password authentication to connect to your IBM Informix database. You'll need to provide valid database credentials with appropriate permissions to access the tables you want to sync in the `configuration.json` file.

## **Data Handling**

The connector:  
- Executes SQL queries against your specified table
- Properly formats datetime values for consistent representation
- Tracks the latest created_at timestamp to enable incremental syncs

The schema used in the example is as follows:

```
{
  "table": "sample_table",
  "primary_key": ["id"]
}
```

## **Error Handling**

The connector implements error handling for:  
- Database connection failures with detailed error logging
- Datetime conversion issues with graceful fallback to string representation
- Missing configuration parameters with clear error messages

## **Additional Considerations**

> NOTE : This example was tested using the IBM Informix developer edition local server. If you face any difficulties while writing your connector, please connect with [our professional services](https://support.fivetran.com/hc/en-us/requests/new?isSdkIssue=true).

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

## Troubleshooting

**Error: `ImportError: DLL load failed while importing ibm_db` on Windows**

Issue: This error occurs on Windows because the Python interpreter cannot find the required library files (`clidriver` DLLs) needed by the `ibm_db` package.

Resolution:

You must explicitly provide the path to the `clidriver\\bin` directory before the `ibm_db` module is imported. We recommend to add the path to the conditional logic in the code.

- Update `connector.py` file : In your connector file, add logic to check if the operating system is Windows. If it is, construct the path to the bin directory and add it to the DLL search path. This code must run before import ibm_db.

    ```python
    import os
    import sys
    # Check if the platform is Windows
    if sys.platform == 'win32':
        # Add the path to the clidriver\\bin directory before importing ibm_db library
        os.add_dll_directory("C:\\path\\to\\your\\python\\env\\Lib\\site-packages\\clidriver\\bin")
    
    # Now it is safe to import ibm_db
    import ibm_db
    ```

This ensures the connector works for local debugging on Windows and the logic is safely ignored when deployed in Fivetran's production environment.
