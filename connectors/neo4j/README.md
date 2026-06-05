# Neo4j Database Connector Example

## Connector Overview

This connector shows how to extract data from Neo4j graph databases and upsert it using Fivetran Connector SDK.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting Started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/neo4j
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features

- Connect to Neo4j graph databases using official Neo4j Python driver.
- Stream data with minimal memory usage through pagination techniques using `skip` and `batch_size` parameters.
- Uses Cypher queries to extract specific data patterns.
- Error handling for connection issues, authentication problems, and query failures.


## Configuration File

The connector requires the following configuration parameters:

```
{
  "neo4j_uri": "<YOUR_NEO4J_URI>",
  "username": "<YOUR_NEO4J_USERNAME>",
  "password": "<YOUR_NEO4J_PASSWORD>",
  "database": "<YOUR_NEO4J_DATABASE>"
}
```

- neo4j_uri: The URI to connect to your Neo4j database (supports bolt, bolt+s, neo4j, neo4j+s protocols)
- username: Neo4j database username
- password: Neo4j database password
- database: Name of the specific Neo4j database to connect to

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements File

The connector requires the following Python packages:


```
neo4j
neo4j-driver
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication

This connector uses basic authentication with Neo4j databases, requiring a username and password. You can also modify the code to allow authentication using the supported authentications methods provided by the Neo4j driver.

For testing the example, you can use the following public credentials provided by neo4j for their demo `twitter` database:

```
{
  "neo4j_uri": "neo4j+s://demo.neo4jlabs.com:7687",
  "username": "neo4j",
  "password": "password",
  "database": "neo4j"
}
```

## Pagination

The connector implements pagination strategies using the following:  
- Skip/Limit Pagination: Records are fetched in batches using `SKIP` and `LIMIT` Cypher query parameters.

Pagination batch sizes are configurable, allowing for customization based on your specific requirements.

## Data Handling

The connector processes Neo4j data as follows:  
- Data Extraction: Executes Cypher queries to extract data from Neo4j graph structures
- Type Conversion: Converts the datetime format from Neo4j to a standard format compatible with Fivetran

The current implementation supports the following tables:  
- users: User information including followers, following, and profile details
- tweet_hashtags: Relationships between tweets and hashtags

## Error Handling


The connector implements comprehensive error handling:  
- Connection Issues: Catches ServiceUnavailable exceptions when Neo4j is unreachable
- Authentication Problems: Handles AuthError exceptions for invalid credentials
- Query Errors: Captures and logs any issues with Cypher query execution
- Resource Management: Uses try/finally blocks to ensure driver connections are properly closed
- Detailed Logging: Provides informative log messages to aid in troubleshooting


## Tables created

### `USER`
The schema for the `USER` table is as follows:

```json
{
  "table": "user",
  "primary_key": ["username"],
  "columns": {
    "username": "STRING"
  }
}
```

### `TWEET_HASHTAG`
The schema for the `TWEET_HASHTAG` table is as follows:

```json
{
  "table": "tweet_hashtag",
  "primary_key": ["tweet_id"],
  "columns": {
    "tweet_id": "STRING"
  }
}
```


## Additional Considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
