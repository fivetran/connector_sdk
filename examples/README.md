# Overview

This section brings together working Connector SDK examples organized by use case, so you can quickly find the right starting point for your custom connector.

Use these examples to learn core implementation patterns, adapt common approaches, and build custom connectors faster. 

## Quickstart examples

These are graded examples designed to help you get started with the Connector SDK quickly.

<details class="details-heading" open="open">
<summary>List of quickstart examples</summary>

- [hello](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/hello) - This is the simplest, append-only example.

- [simple_three_step_cursor](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/simple_three_step_cursor) - This is an emulated source, without any calls out to the internet.

- [configuration](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/configuration) - This example shows how to use secrets.

- [configuration_form](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/configuration_form) - This example shows how to define a connector setup form using `ConfigurationForm`, `form_field`, and `Test`. It demonstrates all available field types (plain text, password, dropdown, toggle, and descriptive dropdown) and how to register a connection test.

- [multiple_code_files](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/multiple_code_files_with_sub_directory_structure) - This example shows how you can write a complex connector comprising multiple `.py` files.

- [using_pd_dataframes](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/using_pd_dataframes) - This example shows the use of Pandas DataFrames to manipulate data prior to sending to Fivetran.

- [large_data_set](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/large_data_set) - This example shows how to handle large data from API responses with pagination and without pagination.

- [weather_with_configuration](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/weather_with_configuration) - This is a real-life example which uses two different public APIs to fetch data from the National Oceanic and Atmospheric Administration (NOAA) for multiple ZIP codes.

- [weather_with_xml_api](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/weather_xml_api) - This is a real-life example which uses a public API to fetch weather data from the National Oceanic and Atmospheric Administration (NOAA) for multiple ZIP codes. The API returns XML responses, which are parsed using the `xml.etree.ElementTree` library.

- [complex_configuration_options](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/complex_configuration_options) - This example shows how to cast configuration fields to LIST, INTEGER, BOOLEAN, and DICT for use in connector code.

- [base_64_encoding_decoding](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/base_64_encoding_decoding) - This example shows how to use base64 encoding and decoding in your connector code.

- [parsing_json_response_in_class](https://github.com/fivetran/connector_sdk/tree/main/examples/quickstart/parsing_json_response_in_class) - This example shows how to fetch JSON data from a public API and map it into a Python dataclass (POJO-style object) for easy parsing and transformation.

</details>


## Common SDK patterns

These examples demonstrate common patterns and best practices for building connectors using the Connector SDK. They cover various aspects such as [authentication](https://fivetran.com/docs/connector-sdk/connector-sdk-concepts/authentication), [data handling](https://fivetran.com/docs/connector-sdk/connector-sdk-concepts/data-handling), [schema management](https://fivetran.com/docs/connector-sdk/connector-sdk-concepts/schema-management), pagination, [state management](https://fivetran.com/docs/connector-sdk/connector-sdk-concepts/state-management), and error handling.

<details class="details-heading" open="open">
<summary>List of connectors for common SDK patterns</summary>

### Authentication
- [api_key](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/api_key) - This is a simple example of how to work with API Key authentication for a REST API.
- [certificate](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/certificate) - Certificate-based client authentication examples
  - [using_base64_encoded_certificate](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/certificate/using_base64_encoded_certificate) - It is an example of using base64-encoded strings for certificate-based authentication. The script includes functions to decode the certificate and key and use them to authenticate API requests.
  - [retrieve_from_aws](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/certificate/retrieve_from_aws) - It is an example of how to retrieve the certificate from AWS S3 bucket and use it for certificate-based authentication.
- [http_basic](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/http_basic) - This is a simple example of how to work with HTTP BASIC authentication for a REST API.
- [http_bearer](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/http_bearer) - This is a simple example of how to work with HTTP BEARER authentication for a REST API.
- [oauth2_with_token_refresh](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/oauth2_with_token_refresh) - It is an example of using OAuth 2.0 client credentials flow, and the refresh of Access token from the provided refresh token. Refer to the OAuth Refresh flow in its `readme.md`.
- [session_token](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/authentication/session_token) - This is a simple example of how to work with Session Token authentication for a REST API.

### Configuration and secret management
- [azure_keyvault_for_secret_management](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/azure_keyvault_for_secret_management) - This example shows how to use Azure Key Vault to securely manage credentials. It retrieves credentials from Azure Key Vault and connects to a postgresql database.
- [environment_driven_connectivity](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/environment_driven_connectivity) - This example shows how to use the `FIVETRAN_DEPLOYMENT_MODEL` environment variable to determine the deployment model and connect to different data sources accordingly.

### Sync strategies and cursors
- [incremental_sync_strategies](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/incremental_sync_strategies) - This example demonstrates multiple ways to perform incremental syncs with different state management strategies: keyset pagination, offset-based pagination, timestamp-based sync, step-size sync (for APIs without pagination), and replay sync (with buffer for read-replica scenarios).
- [priority_first_sync_for_high_volume_initial_syncs](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/priority_first_sync_for_high_volume_initial_syncs) - A priority-first sync (PFS), is very helpful for high-volume historical syncs. It is a sync strategy that prioritises fetching the most recent data first so that fresh data is ready for you to use more quickly. This is a simple example of how you could implement the priority-first sync strategy in a `connector.py` file for your connection.
- [marketstack](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/cursors/marketstack) - This code retrieves different stock tickers and the daily price for those tickers using Marketstack API. Refer to Marketstack's [documentation](https://polygon.io/docs/stocks/getting-started).
- [multiple_tables_with_cursors](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/cursors/multiple_tables_with_cursors) - The parent-child relationship between tables from incremental API endpoints, with the complex cursor.
- [time_window](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/cursors/time_window) - This is an example of how to move the state forward in time by a set number of days until current time is reached.
- [records_with_no_created_at_timestamp](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/cursors/records_with_no_created_at_timestamp) - This example shows how to work with records where the source does not provide a `created_at` (or equivalent) field. It is useful when it's desired to keep track of when the record was first observed.
- [importing_external_drivers](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/importing_external_drivers) - This example demonstrates how to install drivers in your connector environment by writing an `installation.sh` file in the `drivers` folder. This script will be executed at the time of deploying your connector, before your `connector.py` is run to sync your data.

### Export

- [csv](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/export/csv) - This is a simple example of how to work with .CSV file response for a REST API of export type.
- [extracting_data_from_pdf](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/extracting_data_from_pdf) - This example shows how to extract data from PDF files stored in an AWS S3 bucket. It uses the `pdfplumber` library to extract text and tables from PDF documents.
- [gpg_private_keys](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/gpg_private_keys) - This example shows how to use GPG private keys to sign data.
- [hashes](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/hashes) - This example shows how to calculate a hash of fields to be used as primary key. This is useful in scenarios where the incoming rows do not have any field suitable to be used as a Primary Key.
- [parallel_fetching_from_source](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/parallel_fetching_from_source) - This example shows how to fetch multiple files from an AWS S3 bucket in parallel and upsert them into destination using the Connector SDK. It uses the `concurrent.futures` module to create a thread pool and fetch files concurrently.

### Pagination patterns

- [keyset](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/pagination/keyset) - This is a simple example of how to work with key-based pagination for a REST API.
- [next_page_url](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/pagination/next_page_url) - This is a simple example for how to work with next-page-url pagination for a REST API.
- [offset_based](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/pagination/offset_based) - This is a simple example of how to work with offset-based pagination for a REST API.
- [page_number](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/pagination/page_number) - This is a simple example for how to work with page-number-based pagination for a REST API.
- [complex_error_handling_multithreading](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/complex_error_handling_multithreading) - This example demonstrates how to implement next-page URL pagination with multithreading for parallel record processing. It includes comprehensive error handling strategies such as circuit breaker pattern, retry logic with exponential backoff, error categorization, graceful degradation, and thread-safe operations for building resilient connectors.

### Database–specific patterns

- [key_based_replication](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/key_based_replication) - This example shows key-based replication from database sources. Replication keys are columns that are used to identify new and updated data for replication. When you set a table to use Incremental Replication, you’ll also need to define a replication key for that table.
- [schema_from_database](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/schema_from_database) - This example shows how to extract tables (columns, data types, etc.) from a schema present in Snowflake database and use this to generate the connector schema. This approach ensures that the tables in your connector match those in your source database without having to manually define each field.
- [server_side_cursors](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/server_side_cursors) - This example shows how to use server-side cursors to efficiently fetch large datasets from a PostgreSQL database without loading all the data into the memory at once. You need to provide your PostgreSQL credentials for this example to work.

### Schema and typing

- [specified_types](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/specified_types) - This example declares a schema and upserts all data types.
- [unspecified_types](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/unspecified_types) - This example upserts all data types without specifying a schema.

### Error handling and resilience

- [error_handling](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/errors) - This example shows how to handle errors throughout the Connector SDK process and is driven by the configuration.json error_simulation_type value.
- [update_and_delete](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/update_and_delete) - This example shows how to handle composite primary keys while using update and delete operations with a PostgreSQL database as the data source.


### SSH Tunnels

- [Key-based Authentication](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/ssh_tunnels/key_based_authentication) - This example demonstrates how to connect to an SSH server using key-based authentication with the Fivetran Connector SDK. The connector securely establishes an SSH session to a remote EC2 instance running the fivetran-api-playground server and facilitates data interaction over the SSH tunnel.
- [Password-based Authentication](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/ssh_tunnels/password_based_authentication) - This example demonstrates how to connect to an SSH server using password-based authentication with the Fivetran Connector SDK. The connector securely establishes an SSH session to a remote EC2 instance running the fivetran-api-playground server and facilitates data interaction over the SSH Tunnel. This setup uses passwords for authentication.
- [using_bastion_server](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/ssh_tunnels/using_bastion_server) - This example shows how to connect to a database server behind a bastion server using SSH tunneling. It uses the `sshtunnel` library to create an SSH tunnel and `psycopg2-binary` to connect to a PostgreSQL database through the tunnel.

### Data handling

- [three_operations](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/three_operations) - This example shows how to use upsert, update and delete operations.
- [tracking_tables](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/tracking_tables) - This example shows how to track tables that have already been synced in order to be able add new tables and have them automatically sync back to an initial timestamp.
- [update_configuration_during_sync](https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns/update_configuration_during_sync) - This example shows how to update the configuration of the connector during a sync. It demonstrates how to modify the configuration values based on certain conditions using the Fivetran REST API.

### Workflows

- [github](https://github.com/fivetran/connector_sdk/tree/main/examples/workflows/github) - This is an example of a GitHub workflow to deploy a hello connector after a push to the hello directory. It uses GitHub secrets and environment variables to create a configuration.json file that is included in the deployment.
</details>

## AI and Connector SDK
- [Readme](https://github.com/fivetran/connector_sdk/blob/main/ai/README.md) - This is an introduction to using AI tools to leverage Connector SDK.
- [agents.md](https://github.com/fivetran/connector_sdk/blob/main/all_things_ai/ai_agents/AGENTS.md) - This is a system instruction file that can be used in any IDE, API call or conversation with AI to rapidly develop Connector SDK solutions while following best practice.
- [claude_pokeapi tutorial](https://github.com/fivetran/connector_sdk/tree/main/ai/claude/pokeapi_tutorial) - This example contains the code produced by Claude AI to build a custom connector using our Connector SDK. See our [blog article](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai) for more details.
- [claude_fda_drug tutorial](https://github.com/fivetran/connector_sdk/tree/main/ai/claude/fda_drug_tutorial) - This example demonstrates how to use Claude to create a CSDK connector to get data from the FDA drug API.
- [cursor_fda_food tutorial](https://github.com/fivetran/connector_sdk/tree/main/ai/cursor/fda_food_tutorial/fda_food_connector) - This example demonstrates how to use Cursor to create a CSDK connector to get data from the FDA food API.
- [vscode_fda_tobacco tutorial](https://github.com/fivetran/connector_sdk/tree/main/ai/vscode/fda_tobacco_tutorial/fda_tobacco_connector) - This example demonstrates how to use VSCode to create a CSDK connector to get data from the FDA tobacco API.
