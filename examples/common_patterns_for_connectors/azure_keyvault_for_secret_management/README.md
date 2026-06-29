# **Azure Key Vault for Secret Management**

## **Connector Overview**

This connector demonstrates how to use Azure Key Vault to securely manage database credentials. It retrieves credentials from Azure Key Vault, connects to a database, fetches data from database and upserts the data. 

## **Requirements**

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating System:  
  * Windows 10 or later  
  * macOS 13 (Ventura) or later

## **Getting Started**

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/azure_keyvault_for_secret_management
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## **Features**

- Securely retrieves database credentials from Azure Key Vault
- Connects to the PostgreSQL database using retrieved credentials
- Verifies the connection by executing a simple query
- Upserts a record into a table to confirm successful connection

## **Configuration File**

The connector requires the following configuration parameters:

```
{
  "tenant_id": "<YOUR_AZURE_TENANT_ID>",
  "client_id": "<YOUR_APP_CLIENT_ID>",
  "client_secret": "<YOUR_APP_CLIENT_SECRET>",
  "vault_url": "<https://YOUR-VAULT-NAME.vault.azure.net/>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## **Requirements File**

This connector requires Azure SDK packages to access Key Vault and connect to PostgreSQL:

```
psycopg2-binary
azure-identity
azure-keyvault
azure-storage==0.36.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## **Authentication**

This connector uses service principal authentication to access Azure Key Vault. To create the necessary credentials:  
1. Register an application in Azure Active Directory  
   - Go to Azure Portal → Azure Active Directory → App registrations
   - Create a new registration with a name of your choice
   - Note the Application (client) ID and Directory (tenant) ID
2. Create a client secret  
   - In your app registration, go to Certificates & secrets
   - Create a new client secret and note its value immediately
3. Grant the application access to your Key Vault  
   - For role-based access control: Go to Key Vault → Access control (IAM) → Add role assignment
   - Assign the "Key Vault Secrets User" role to your application
   - For access policy: Go to Key Vault → Access policies → Add access policy
   - Grant "Get" and "List" permissions for secrets to your application


## **Data Handling**

The connector retrieves credentials from Azure Key Vault and uses them to establish a database connection. It then:  

1. Executes a simple query to verify connectivity and retrieve data from a table in the database.

2. Upserts the data in the `employees` table.
   
The connector expects the following secrets to be stored in the Key Vault:  
   - postgresHost
   - postgresPort
   - postgresDatabase
   - postgresUser
   - postgresPassword

## **Tables Created**
The connector creates the following table in the database:
- `employees` - This table is used to store employee data. The schema includes:
  - id (INT)
  - name (STRING)
  - department_id (INT)
  - employee_metadata (JSON)

The table in the destination looks like this:

| id | name      | department_id | employee_metadata    | _fivetran_deleted | _fivetran_synced              |
|----|-----------|---------------|----------------------|-------------------|-------------------------------|
| 1  | John Doe  | 1             | {"role": "Engineer"} | false             | 2025-05-11 19:53:33.959 +0000 |
| 2  | Berry Doe | 1             | {"role": "Engineer"} | false             | 2025-05-11 19:53:33.984 +0000 |

## **Additional Considerations**

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
