<p align="center">
  <a href="https://www.fivetran.com/">
    <img src="https://cdn.prod.website-files.com/6130fa1501794ed4d11867ba/63d9599008ad50523f8ce26a_logo.svg" alt="Fivetran">
  </a>
</p>

<p align="center">
  Fivetran Connector SDK allows Real-time, efficient data replication to your destination of choice.
</p>

<p align="center">
  <a href="https://github.com/fivetran/fivetran_connector_sdk/stargazers" target="_blank"><img src="https://img.shields.io/github/stars/fivetran/fivetran_connector_sdk?style=social&label=Star"></a>
  <a href="https://github.com/fivetran/fivetran_connector_sdk/blob/main/LICENSE" target="_blank"><img src="https://img.shields.io/badge/License-MIT-blue" alt="License"></a>
  <a href="https://pypi.org/project/fivetran-connector-sdk/" target="_blank"><img src="https://img.shields.io/pypi/v/fivetran-connector-sdk" alt="PyPI Release"></a>
  <a href="https://pepy.tech/project/fivetran-connector-sdk" target="_blank"><img src="https://static.pepy.tech/badge/fivetran-connector-sdk" alt="PyPI Downloads"></a>
<a href="https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md" target="_blank"><img src="https://img.shields.io/badge/Managed-Yes-green/" alt="Managed"></a>
</p>

# Overview
Explore practical examples and helpful resources for building custom data connectors with the Fivetran [Connector SDK](https://fivetran.com/docs/connectors/connector-sdk). Learn how to develop and deploy [custom data connectors](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) in Python, and extend Fivetran’s capabilities to fit your data integration needs.

You’ll also find tips on [using AI to help you build a Connector SDK connection](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/README.md) quickly.

## Why Connector SDK?
Fivetran Connector SDK allows you to code a custom data connector using Python and deploy it as an extension of Fivetran. Fivetran automatically manages running Connector SDK connections on your scheduled frequency and manages the required compute resources, eliminating the need for a third-party provider.

Connector SDK provides native support for many Fivetran features and relies on existing Fivetran technology. It also eliminates timeout and data size limitations seen in AWS Lambda.

## Requirements
- Python version ≥3.10 and ≤3.13
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

See [Setup guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

Run the `.github/scripts/setup-hooks.sh` script from the root of the repository to set up pre-commit hooks. This ensures that your code is formatted correctly and passes all tests before you commit them.

## Repository Structure

```
fivetran_connector_sdk/
├── all_things_ai/                          # AI-assisted development: tutorials and agent configs
├── connectors/                             # Community connectors — ready-to-use source-specific implementations
├── examples/
│   ├── common_patterns_for_connectors/     # Reusable building blocks: auth, pagination, sync strategies, error handling
│   ├── private_preview_features/           # Examples for features currently in private preview
│   ├── quickstart_examples/                # Getting-started examples — from hello world to a first REST API connector
│   └── workflows/                          # CI/CD and deployment workflow examples
├── fivetran_platform_features/             # Native Fivetran platform feature examples
└── template_connector/                     # Default template for new projects — used by `fivetran init` (no --template flag)
```

## Examples

> Note: To simplify the processes of building and maintaining connectors with Connector SDK, we've removed the need to use the Python generator pattern with Connector SDK operations, `yield`, starting with Connector SDK version 2.0.0. This change is fully backward compatible, so your existing Connector SDK connections will continue to function without modification. For more information, refer to our [Connector SDK release notes](https://fivetran.com/docs/connector-sdk/changelog#august2025).

### Community connectors

These are ready-to-use connectors, requiring minimal modifications to get started.
There are many Community Connectors (nearly 100) and we are adding more all the time. You can find these connectors under `/connectors/`.

<details class="details-heading" open="open">
<summary>List of community connectors</summary>

- Apache Druid
  - [using_sql](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_druid/sql_api_connector) - This example shows how to sync data from Apache Druid datasources using Druid's SQL API with time-based pagination and incremental sync to efficiently replicate event and analytics data.
  - [using_pydruid](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_druid/pydruid_connector) - This example demonstrates syncing from Apache Druid using the PyDruid library for native query capabilities, retry logic with exponential backoff, and optimized data retrieval for enhanced performance.
- [apache_hbase](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_hbase) - This example shows how to connect and sync data from Apache HBase by using Connector SDK. It uses happybase and thrift libraries to connect to HBase and fetch data.
- [apache_hive/using_pyhive](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_hive/using_pyhive) - This example shows how you can sync data from Apache Hive by using Connector SDK and PyHive.
- [apache_pulsar](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_pulsar) - This example demonstrates how to fetch data from Apache Pulsar topics and sync it to a data warehouse using Connector SDK. It supports multiple topics, uses Pulsar's Reader API for message consumption, and implements proper checkpointing for incremental syncs.
- [arango_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/arango_db) - This example demonstrates how to sync data from ArangoDB, a native multi-model database combining document, graph, and key-value capabilities. The connector syncs document collections (airports, points-of-interest) and edge collections (flights) with offset-based pagination and checkpointing. You need to provide your ArangoDB credentials for this example to work.
- [apache_hive/using_sqlalchemy](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/apache_hive/using_sqlalchemy) - This example shows how you can sync data from Apache Hive by using Connector SDK and SQLAlchemy with PyHive.
- [awardco](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/awardco) - This example shows how to sync data from Awardco with the Connector SDK. You will need to provide an API key for this example to work.
- [aws_athena/using_boto3](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/aws_athena/using_boto3) - This is an example of how we can sync data from AWS Athena by using Connector SDK using Boto3.
- [aws_athena/using_sqlalchemy](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/aws_athena/using_sqlalchemy) - This is an example of how we can sync data from AWS Athena by using Connector SDK using SQLAlchemy with PyAthena.
- [aws_dynamo_db_authentication](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/aws_dynamo_db_authentication) - This is an example of how we can connect and sync data from AWS DynamoDB by using Connector SDK.
- [aws_rds_oracle](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/aws_rds_oracle) - This is an example of how we can connect and sync data from AWS Oracle by using Connector SDK.
- [betterstack](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/betterstack) - This example shows how to sync uptime monitoring data from Better Stack's Uptime API by using Connector SDK. It retrieves monitors, status pages, monitor groups, heartbeats, heartbeat groups, incidents, and on-call calendars. You need to provide your Better Stack API key for this example to work.
- [cassandra](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/cassandra) - This is an example of how we can connect and sync data from Cassandra database by using Connector SDK. You need to provide your Cassandra credentials for this example to work.
- [checkly](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/checkly) - This example shows how to sync monitoring check data and analytics from Checkly's API by using Connector SDK. You need to provide your Checkly API key and account ID for this example to work.
- [clerk](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/clerk) - This example shows how to sync user data from a Clerk database by using Connector SDK. You need to provide your Clerk API key for this example to work.
- [clickhouse](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/clickhouse) - This example shows how to sync data from ClickHouse database using Connector SDK. You need to provide your ClickHouse credentials for this example to work.
- [commonpaper](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/commonpaper) - This example shows how to sync agreement data from Common Paper using Connector SDK. You need to provide your Common Paper credentials for this example to work.
- [cority](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/cority) - This example shows how to sync user reports from a Cority EHS tenant via the MRWPService SOAP API by using Connector SDK. The connector is configuration-driven and supports any number of user reports; you need to provide your Cority tenant base URL, an integration username and password, and one or more report descriptors mapping `userReportId` to a destination table.
- [courier](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/courier) - This example shows how to sync data from the Courier API, a multi-channel notification platform. It fetches audit events, brand configurations, audience segments, message logs, subscriber lists, and notification templates. You need to provide your Courier API key for this example to work.
- [couchbase_capella](https://github.com/fivetran/fivetran_connector_sdk/blob/main/connectors/couchbase_capella) - This example shows how to sync data from Couchbase Capella using Connector SDK. You need to provide your Couchbase Capella credentials for this example to work.
- [customer_thermometer](https://github.com/fivetran/fivetran_connector_sdk/blob/main/connectors/customer_thermometer) - This example shows how to sync customer feedback data from Customer Thermometer's API by using Connector SDK. You need to provide your Customer Thermometer API key for this example to work.
- [couchbase_magma](https://github.com/fivetran/fivetran_connector_sdk/blob/main/connectors/couchbase_magma) - This example shows how to sync data from a self-managed Couchbase Server using the Magma storage engine with Connector SDK. You need to provide your Couchbase credentials for this example to work.
- [datacamp](https://github.com/fivetran/fivetran_connector_sdk/blob/main/connectors/data_camp) - This example shows how to sync course catalog data from DataCamp's LMS Catalog API by using the Connector SDK. You need to provide your DataCamp bearer token for this example to work.
- [dgraph](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/dgraph) - This example shows how to sync e-commerce product catalog data from Dgraph graph databases using Connector SDK. It demonstrates true incremental sync with timestamp-based filtering, graph relationship preservation via an edges table, and per-table state checkpointing. You need to provide your Dgraph GraphQL endpoint URL and API key for this example to work.
- [discord](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/discord) - This example shows how to sync data from Discord using Connector SDK. You need to provide your Discord Bot credentials for this example to work.
- [docusign](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/docusign) - This example shows how to sync data from the Docusign eSignature API using Connector SDK. You need to provide your Docusign API credentials for this example to work.
- [dolphin_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/dolphin_db) - This example shows how to sync data from DolphinDB database using Connector SDK. You need to provide your DolphinDB credentials for this example to work.
- [documentdb](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/documentdb) - This example shows how to connect to AWS DocumentDB and sync data from DocumentDB collections using Connector SDK. This Python-based connector is specifically intended for [Hybrid Deployment (HD)](https://fivetran.com/docs/deployment-models/hybrid-deployment) scenarios, as the native DocumentDB connector does not support Hybrid Deployment. You need to provide your DocumentDB credentials and ensure proper network connectivity for this example to work.
- [dragonfly_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/dragonfly_db) - This example shows how to sync high-performance in-memory data from DragonflyDB using Connector SDK. It demonstrates incremental sync with hash-based change detection, deletion tracking, TimeSeries support, and handles all Redis-compatible data types (strings, hashes, lists, sets, sorted sets). You need to provide your DragonflyDB credentials for this example to work.
- [ehi](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/ehi) - This example shows how to sync EHI tables such as Caboodle using Connector SDK. It connects to Microsoft SQL server to sync the data. You need to provide your server credentials for this example to work.
- [elastic_email](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/elastic_email) - This example shows how to sync email marketing data from Elastic Email using Connector SDK. It retrieves campaigns, contacts, lists, segments, templates, events, statistics, files, domains, and suppression data. You need to provide your Elastic Email API key for this example to work.
- [firebird_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/firebird_db) - This example shows how to sync data from Firebird DB using Connector SDK. You need to provide your Firebird DB credentials for this example to work.
- [fleetio](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/fleetio) - This example shows how to sync data from Fleetio using Connector SDK. You need to provide your Fleetio API Token for this example to work.
- [fred](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/fred) - This example shows how to sync economic data from the Federal Reserve Economic Data (FRED) API using the Connector SDK. It retrieves series metadata, time series observations, categories, and releases. You need to provide your FRED API key and series IDs for this example to work.
- [gcp_pub_sub](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/gcp_pub_sub) - This example shows how to sync data from Google Cloud Pub/Sub using the Connector SDK.
- [grey_hr](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/grey_hr) - This example shows how to sync data from the greytHR API using the Connector SDK. Provide your greytHR API credentials for this example to work.
- [greenplum_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/greenplum_db) - This example shows how to sync data from Greenplum database using Connector SDK. You need to provide your Greenplum credentials for this example to work.
- [gnews](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/gnews) - This is a simple example of how to sync data from the GNews API using Connector SDK.
- [harness_io](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/harness_io) - This example shows how to connect and sync data from Harness.io using Connector SDK. You need to provide your Harness API token and account ID for this example to work.
- [healthchecks](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/healthchecks) - This example shows how to sync health check monitoring data from Healthchecks.io by using the Connector SDK. You need to provide your Healthchecks.io API key for this example to work.
- [hubspot](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/hubspot) - This example shows how to connect and sync specific event type Event data from Hubspot using Connector SDK
- [ibm_db2](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/ibm_db2) - This example shows how to connect and sync data from IBM Db2 using Connector SDK. It uses the `ibm_db` library to connect to the database and fetch data.
- [ibm_db2_log_based_replication](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/ibm_db2_log_based_replication) - This example demonstrates log-based Change Data Capture (CDC) for IBM Db2 using the ASN SQL Replication framework. The `asncap` daemon reads the Db2 transaction log and writes every INSERT, UPDATE, and DELETE to a Change Data table; the connector reads exclusively from that table after the initial load, making this genuine log-based replication without polling the source.
- [ibm_informix_using_ibm_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/ibm_informix_using_ibm_db) - This example shows how to connect and sync data from IBM Informix using Connector SDK. This example uses the `ibm_db` library to connect to the Informix database and fetch data.
- [influx_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/influx_db) - This example shows how to sync data from InfluxDB using Connector SDK. It uses the `influxdb3_python` library to connect to InfluxDB and fetch time-series data from a specified measurement.
- [iterate](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/iterate) - This example shows how to sync NPS survey data from the Iterate REST API and load it into your destination using Connector SDK. The connector fetches NPS surveys and their individual responses, providing complete survey analytics data for downstream analysis.
- [janus_graph](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/janus_graph) - This example shows how to sync data from the Janus Graph database using the Connector SDK. You need to provide your Janus Graph credentials for this example to work.
- [keycloak](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/keycloak) - This example shows how to sync identity and access management data from Keycloak Admin API, including users, groups, roles, clients, and authentication events using the Connector SDK. You need to provide your Keycloak server URL, realm, and OAuth2 client credentials for this example to work.
- [leavedates](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/leavedates) - This example shows how to sync leave report data from LeaveDates API by using the Connector SDK. You need to provide your LeaveDates API token and company ID for this example to work.
- [microsoft_excel](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/microsoft_excel) - This example shows how to sync data from Microsoft Excel using Connector SDK. It shows three different ways to sync data from Excel files using `pandas`, `python-calamine` and `openpyxl`.
- [microsoft_intune](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/microsoft_intune/) - This example shows how to connect to Microsoft Intune and retrieve all managed devices using the Connector SDK.
- [n8n](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/n8n) - This example shows how to sync workflow automation data from n8n, including workflows and executions, using the Connector SDK. The connector implements incremental sync with cursor-based pagination and automatic retry logic with exponential backoff. You need to provide your n8n API key and base URL for this example to work.
- [newsapi](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/newsapi) - This is a simple example of how to sync data from NewsAPI using Connector SDK.
- [neo4j](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/neo4j) - This example shows how to extract data from Neo4j graph databases and upsert it using Fivetran Connector SDK.
- [netlify](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/netlify) - This example shows how to sync sites, deploys, forms, and form submissions from the Netlify API using Connector SDK. It implements incremental syncing with pagination support and retry logic. You need to provide your Netlify API token for this example to work.
- [noaa](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/noaa) - This example shows how to sync weather observations and active alerts from the National Weather Service (NOAA) API using the Connector SDK. The connector supports state-based station discovery, manual station specification, and incremental syncing with automatic retry logic. No authentication required as the NOAA API is public.
- [npi_registry](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/npi_registry) - This example shows how to sync healthcare provider data from the National Plan and Provider Enumeration System (NPPES) NPI Registry API using the Connector SDK. The NPI Registry, maintained by the Centers for Medicare & Medicaid Services (CMS), contains public information about healthcare providers and organizations, including demographics, addresses, taxonomies, identifiers, endpoints, and practice locations.
- [oauth2_and_accelo_api_connector_multithreading_enabled](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/oauth2_and_accelo_api_connector_multithreading_enabled) - This example shows how to sync data from the Accelo API. It uses OAuth 2.0 Client Credentials flow authentication, rate limiting, and multithreading, which allows to make API calls in parallel to pull data faster. You need to provide your Accelo OAuth credentials for this example to work. Refer to the Multithreading Guidelines in `api_threading_utils.py`.
- [github](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/github) - This example shows how to sync repository data, commits, and pull requests from GitHub REST API using Connector SDK. It implements GitHub App authentication with JWT, supports both on-premises and cloud (github.com) instances, uses incremental sync with per-repository state tracking, and handles pagination automatically with robust retry logic. You need to provide your GitHub App credentials (App ID, private key, installation ID, and organization name) for this example to work.
- [github_traffic](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/github_traffic) - This example shows how to sync GitHub repositories traffic data using Connector SDK via REST API. You need to provide your GitHub Personal access token and specify the repositories you want to track.
- [goshippo](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/goshippo) - This example shows how to sync shipment data from the Goshippo API using Connector SDK. It demonstrates incremental sync, pagination, retry logic, and handling of related data (rates, parcels, and messages). You need to provide your Goshippo API token for this example to work.
- [google_trends](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/google_trends) - This example shows how to sync search interest data from Google Trends using the Connector SDK. It implements full-refresh syncing with exponential retry logic, supports multiple keywords, regions, and timeframes, and tracks historical changes in search trends using an append-only design.
- [gumroad](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/gumroad) - This example shows how to sync sales, products, subscribers, and payout data from Gumroad's API using the Connector SDK. It supports incremental syncing for sales and payouts, handles pagination automatically, and flattens nested JSON objects into relational tables. You need to provide your Gumroad access token for this example to work.
- [mastertax](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/mastertax) - This example shows how to sync data from MasterTax API using Connector SDK.
- [mailerlite](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/mailerlite) - This example shows how to sync email marketing data from MailerLite using the Connector SDK. It demonstrates syncing subscribers, groups, campaigns, and custom fields with both cursor-based and page-based pagination, client-side incremental sync using timestamps, and comprehensive error handling with exponential backoff. You need to provide your MailerLite API key for this example to work.
- [meilisearch](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/meilisearch) - This example shows how to sync index metadata and document data from MeiliSearch using the Connector SDK. It fetches all indexes and their documents from your MeiliSearch instance, enabling analytics on search data, product catalogs, and user reviews. Provide your MeiliSearch API URL and API key for this example to work.
- [oktopost](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/oktopost) - This example shows how to sync exports from the Oktopost BI Exports API using Connector SDK. You need to provide your oktopost API key for the example to work.
- [owasp_api_vulns](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/owasp_api_vulns) - This example shows how to sync OWASP-related API vulnerability data from the NVD 2.0 API using Connector SDK. You need to provide your NVD API key for this example to work.
- [oop_example](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/oop_example) - This example shows how to use object-oriented programming to build a connector for the National Parks Service API. It demonstrates how to create a class that encapsulates the logic for fetching data from the API and processing it.
- [oura_ring](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/oura_ring) - This example shows how to sync health and wellness data from the Oura Ring API v2 using Connector SDK. It syncs daily activity, sleep, readiness, stress, and heart rate data with incremental syncing, cursor-based pagination, automatic flattening of nested contributor objects, and date-range chunking for high-volume heart rate data. You need to provide your Oura Personal Access Token for this example to work.
- OData APIs
  - [odata_version_2_using_pyodata](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/odata_api/odata_version_2_using_pyodata) - This is an example of how to sync data from an OData API version 2 using Connector SDK.
  - [odata_version_4](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/odata_api/odata_version_4) - This is an example of how to sync data from an OData API version 4 using Connector SDK.
  - [odata_version_4_using_python_odata](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/odata_api/odata_version_4_using_python_odata) - This is an example of how to sync data from an OData API version 4 using python-odata python library.
- [partech](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/partech) - This example shows how to sync location configuration and program metadata from the Partech (previously Punchh) Point of Sale API using Connector SDK. It demonstrates fetching location settings, loyalty program rules, redeemables, and redemption priorities. You need to provide your Partech location key and business key for this example to work.
- [pindrop](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/pindrop) - This is an example of how to sync nightly report data from Pindrop using Connector SDK. You need to provide your Pindrop client ID and client Secret for this example to work.
- [prefect](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/prefect) - This example shows how to sync workflow orchestration data from Prefect Cloud using the Connector SDK. It fetches flows, deployments, work pools, work queues, flow runs, task runs, artifacts, and variables from the Prefect Cloud API with incremental syncing support. You need to provide your Prefect API key, account ID, and workspace ID for this example to work.
- [prometheus](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/prometheus) - This example demonstrates how to sync metrics metadata and time series data from Prometheus, an open-source monitoring and alerting system. The connector syncs data with support for incremental syncs, multiple authentication methods (none, basic, bearer token), and configurable metric filtering. You need to provide your Prometheus server URL and optional authentication credentials for this example to work.
- [quest_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/quest_db) - This example shows how to sync high-performance time series data from QuestDB using Connector SDK. It demonstrates pagination for large datasets, retry logic with exponential backoff, state management with checkpointing, and dynamic schema discovery. You need to provide your QuestDB connection details for this example to work.
- [rabbitmq](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/rabbitmq) - This example shows how to sync messages from RabbitMQ queues using Connector SDK. It uses the `pika` library to connect to RabbitMQ and fetch messages from specified queues. You need to provide your RabbitMQ connection URL for this example to work.
- [raven_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/raven_db) - This example shows how to sync document data from a RavenDB NoSQL database using the Connector SDK. It demonstrates incremental sync of data using RavenDB's `@last-modified` metadata field, certificate-based authentication, and efficient pagination for large document collections. You need to provide your RavenDB Cloud credentials and base64-encoded PEM certificate for this example to work.
- [redis](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/redis) - This example shows how to sync gaming leaderboards, player statistics, and real-time engagement data from Redis to Fivetran. Designed for gaming platforms and competitive applications that use Redis with persistence (AOF/RDB) as their primary database. You need to provide your Redis credentials for this example to work.
- [resend](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/resend) - This example shows how to sync email data from Resend's API using Connector SDK with incremental syncing, pagination handling, and error handling with exponential backoff. You need to provide your Resend API token for this example to work.
- Redshift
  - [simple_redshift_connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/redshift/simple_redshift_connector) - This example shows how to sync records from Redshift by using Connector SDK. You need to provide your Redshift credentials for this example to work.
  - [large_data_volumes](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/redshift/large_data_volume) - This example shows how to sync large data volumes from Redshift by using Connector SDK. You need to provide your Redshift credentials for this example to work.
  - [using_unload](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/redshift/using_unload) - This example shows how to sync data from Redshift with Connector SDK using Redshift's UNLOAD to S3 feature. You need to provide your Redshift and S3 credentials for this example to work.
- [rethink_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/rethink_db) - This example shows how to sync data from RethinkDB, an open-source database designed for real-time applications, using Connector SDK. It features automatic schema discovery, intelligent incremental syncing using timestamp fields, and complex data type handling. You need to provide your RethinkDB connection details for this example to work.
- [s3_csv_validation](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/s3_csv_validation) - This is an example of how to read .CSV file from Amazon S3 and validate the data. You need to provide your AWS S3 credentials for this example to work.
- [sam_gov](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sam_gov) - This example shows how to sync government contracting opportunities from the SAM.gov (System for Award Management) API using the Connector SDK. It demonstrates incremental sync with a sliding-window strategy, pagination for large datasets, and a normalized data structure with breakout tables. You need to provide your SAM.gov API key for this example to work.
- [SAP HANA SQL](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sap_hana_sql) - This example uses hdbcli to connect to SAP HANA SQL Server for syncing data using Connector SDK. You need to provide your SAP HANA SQL Server credentials for this example to work.
- [sap_ariba](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sap_ariba) - This example shows how to use the Connector SDK to integrate with SAP Ariba and sync procurement data for your organization. You need to provide your SAP Ariba API key for this example to work.
- [sendcloud](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sendcloud) - This example shows how to sync shipment data from Sendcloud's API by using Connector SDK. It fetches shipment information including packages, delivery times, parcels, shipping carriers, and customs information. You need to provide your Sendcloud API credentials for this example to work.
- [sensor_tower](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sensor_tower) - This example shows how to use the Connector SDK to integrate with Sensor Tower and sync market intelligence data for mobile apps of your choice.
- [sensource](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sensource) - This example shows how to use the Connector SDK to obtain traffic and occupancy metrics for physical spaces from SenSource.
- [similarweb](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/similarweb) - This example shows how to use the Connector SDK to get website and app performance metrics from similarweb for domains of your choice.
- [smartsheets](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/smartsheets) - This is an example of how we can sync Smartsheets sheets and reports by using the Connector SDK. You need to provide your Smartsheets `api_key` for this example to work.
- [snipeitapp](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/snipeitapp) - This example shows how to sync IT asset management data from Snipe-IT's REST API by using the Connector SDK. It tracks hardware assets, users, companies, locations, categories, manufacturers, suppliers, models, status labels, and departments. You need to provide your Snipe-IT API token and base URL for this example to work.
- [suitedash](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/suitedash) - This example shows how to sync CRM data from SuiteDash's API by using Connector SDK. You need to provide your SuiteDash Public ID and Secret Key for this example to work.
- [solace](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/solace): This example demonstrates how to sync messages from a Solace queue. To run it, you must provide your Solace broker credentials, including the host, username, password, and queue name.
- [sql_server](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/sql_server) - This example uses pyodbc to connect to SQL Server for syncing data using Connector SDK. You need to provide your SQL Server credentials for this example to work.
- [statuscake](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/statuscake) - This example shows how to sync uptime monitoring data from StatusCake's API by using Connector SDK. It fetches uptime test configurations, historical performance data, downtime periods, and alert information. You need to provide your StatusCake API key for this example to work.
- [supabase](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/supabase) - This example shows how to sync employee data from a Supabase database by using Connector SDK. You need to provide your Supabase project URL and API key for this example to work.
- [talon_one](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/talon_one) - This is an example of how we can sync Talon.one events data using Connector SDK. You need to provide your Talon.one base url and api key for this example to work.
- [temporal_cloud](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/temporal_cloud) - This example shows how to sync workflow execution and schedule data from Temporal Cloud using Connector SDK. It retrieves workflow metadata, as well as schedule configurations. The connector uses async operations for efficient data retrieval and implements streaming to handle large datasets. You need to provide your Temporal Cloud host, namespace, and API key for this example to work.
- [teradata](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/teradata) - This example shows how to sync data from Teradata Vantage database using Connector SDK. It uses the `teradatasql` library to connect to Teradata and fetch data from a specified table. You need to provide your Teradata credentials for this example to work.
- [tidb](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/tidb) - This is an example source connector that demonstrates incremental replication from TiDB databases into Fivetran destinations. It supports schema declaration, stateful checkpointing via `created_at`, and optional vector-column parsing for JSON/vector payloads.
- [timescale_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/timescale_db) - This example shows how to sync data from TimescaleDb using Connector SDK. It uses the `psycopg2` library to connect to TimescaleDb and fetch time-series and vector data from specified tables. You need to provide your TimescaleDb credentials for this example to work.
- [toast](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/toast) - This is an example of how we can sync Toast data using the Connector SDK. You would need to provide your Toast credentials for this example to work.
- [tulip_interfaces](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/tulip_interfaces) - Syncs data from Tulip Tables to Fivetran destinations. You need a Tulip instance with permissions to create API keys for the example to work.
- veeva vault
  - [basic_auth](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/veeva_vault/basic_auth) - This example shows how to authenticate to Veeva Vault using basic authentication and sync records from Veeva Vault. You need to provide your Veeva Vault credentials for this example to work.
  - [session_id_auth](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/veeva_vault/session_id_auth) - This example shows how to authenticate to Veeva Vault using session id authentication and sync records from Veeva Vault. You need to provide your Veeva Vault credentials for this example to work.
- [vercel](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/vercel) - This example shows how to sync deployment data from Vercel's REST API by using the Connector SDK, focusing on a single endpoint (/v6/deployments). You need to provide your Vercel API token for this example to work. Optionally, you can also provide a Team ID to access team resources instead of personal account deployments.
- [weights_and_biases](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/weights_and_biases) - This example shows how to sync machine learning experiment tracking data from Weights & Biases (W&B), including projects, runs (experiments), and artifacts (models and datasets), using the Fivetran Connector SDK The connector uses the W&B Python SDK to retrieve data and implements robust error handling. You need to provide your W&B API key and entity name for this example to work.
- [yugabyte_db](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/yugabyte_db) - This example shows how to sync data from a YugabyteDB database using Connector SDK. YugabyteDB is a distributed SQL database that is PostgreSQL-compatible. The connector automatically discovers tables, detects primary keys, and performs incremental syncs using the `updated_at` column when available. You need to provide your YugabyteDB credentials for this example to work.
- [zigpoll](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/zigpoll) - This is an example of how to sync Zigpoll data using Connector SDK. You need to provide your Zigpoll API key for this example to work.

</details>

### Quickstart examples

These examples are designed to help you get started with the Connector SDK quickly. There are about a dozen examples available under `/examples/quickstart_examples`.

<details class="details-heading" open="open">
<summary>List of quickstart examples</summary>

- [hello](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/hello) - This is the simplest, append-only example.

- [simple_three_step_cursor](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/simple_three_step_cursor) - This is an emulated source, without any calls out to the internet.

- [configuration](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/configuration) - This example shows how to use secrets.

- [multiple_code_files_with_sub_directory_structure](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/multiple_code_files_with_sub_directory_structure) - This example shows how you can write a complex connector comprising multiple `.py` files.

- [using_pd_dataframes](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/using_pd_dataframes) - This example shows the use of Pandas DataFrames to manipulate data prior to sending to Fivetran.

- [large_data_set](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/large_data_set) - This example shows how to handle large data from API responses with pagination and without pagination.

- [weather_with_configuration](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/weather_with_configuration) - This is a real-life example which uses two different public APIs to fetch data from the National Oceanic and Atmospheric Administration (NOAA) for multiple ZIP codes.

- [weather_with_xml_api](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/weather_xml_api) - This is a real-life example which uses a public API to fetch weather data from the National Oceanic and Atmospheric Administration (NOAA) for multiple ZIP codes. The API returns XML responses, which are parsed using the `xml.etree.ElementTree` library.

- [base_64_encoding_decoding](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/base_64_encoding_decoding) - This example shows how to use base64 encoding and decoding in your connector code.

- [parsing_json_response_in_class](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/parsing_json_response_in_class) - This example shows how to fetch JSON data from a public API and map it into a Python dataclass (POJO-style object) for easy parsing and transformation.

- [pyproject_toml](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/quickstart_examples/pyproject_toml) - This example shows how to use `pyproject.toml` for dependency management instead of `requirements.txt`. It fetches exchange rates from the Frankfurter API and uses the `tenacity` library (declared in `pyproject.toml`) for retry logic with exponential backoff.

</details>

### Common Connector SDK patterns

These examples demonstrate common patterns and best practices for building connectors using the Connector SDK. They cover various aspects such as authentication, error handling, data extraction, and more. You can find these examples under `/examples/common_patterns_for_connectors`.

<details class="details-heading" open="open">
<summary>List of connectors for common Connector SDK patterns</summary>

#### Authentication
- [api_key](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/api_key) - This is a simple example of how to work with API key authentication for a REST API.
- [certificate](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/certificate) - Certificate-based client authentication examples
  - [using_base64_encoded_certificate](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/certificate/using_base64_encoded_certificate) - It is an example of using base64-encoded strings for certificate-based authentication. The script includes functions to decode the certificate and key and use them to authenticate API requests.
  - [retrieve_from_aws](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/certificate/retrieve_from_aws) - It is an example of how to retrieve the certificate from AWS S3 bucket and use it for certificate-based authentication.
- [http_basic](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/http_basic) - This is a simple example of how to work with HTTP BASIC authentication for a REST API.
- [http_bearer](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/http_bearer) - This is a simple example of how to work with HTTP BEARER authentication for a REST API.
- [oauth2_with_token_refresh](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh) - It is an example of using OAuth 2.0 client credentials flow, and the refresh of Access token from the provided refresh token. Refer to the OAuth Refresh flow in its `readme.md`.
- [session_token](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/session_token) - This is a simple example of how to work with Session Token authentication for a REST API.

#### Configuration and secret management
- [complex_configuration_options](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/complex_configuration_options) - This example shows how to cast configuration fields to LIST, INTEGER, BOOLEAN, and DICT for use in connector code. This example also demonstrates how to define static values in a separate Python file and import them in `connector.py`.
- [azure_keyvault_for_secret_management](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/azure_keyvault_for_secret_management) - This example shows how to use Azure Key Vault to securely manage credentials. It retrieves credentials from Azure Key Vault and connects to a postgresql database.
- [environment_driven_connectivity](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/environment_driven_connectivity) - This example shows how to use the `FIVETRAN_DEPLOYMENT_MODEL` environment variable to determine the deployment model and connect to different data sources accordingly.

#### Sync strategies and cursors
- [incremental_sync_strategies](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies) - This example demonstrates multiple ways to perform incremental syncs with different state management strategies: keyset pagination, offset-based pagination, timestamp-based sync, step-size sync (for APIs without pagination), and replay sync (with buffer for read-replica scenarios).
- [priority_first_sync_for_high_volume_initial_syncs](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/priority_first_sync_for_high_volume_initial_syncs) - A priority-first sync (PFS), is very helpful for high-volume historical syncs. It is a sync strategy that prioritises fetching the most recent data first so that fresh data is ready for you to use more quickly. This is a simple example of how you could implement the priority-first sync strategy in a `connector.py` file for your connection.
- [marketstack](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/marketstack) - This code retrieves different stock tickers and the daily price for those tickers using Marketstack API. Refer to Marketstack's [documentation](https://polygon.io/docs/stocks/getting-started).
- [multiple_tables_with_cursors](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/multiple_tables_with_cursors) - The parent-child relationship between tables from incremental API endpoints, with the complex cursor.
- [time_window](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/time_window) - This is an example of how to move the state forward in time by a set number of days until current time is reached.
- [records_with_no_created_at_timestamp](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/records_with_no_created_at_timestamp) - This example shows how to work with records where the source does not provide a `created_at` (or equivalent) field. It is useful when it's desired to keep track of when the record was first observed.

#### Export

- [csv](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/export/csv) - This is a simple example of how to work with .CSV file response for a REST API of export type.
- [high_volume_csv](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/high_volume_csv) - This example shows how to handle high-volume CSV files from an API. It demonstrates efficient reading, processing, and upserting of large CSV files into the destination using the Connector SDK.
- [extracting_data_from_pdf](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/extracting_data_from_pdf) - This example shows how to extract data from PDF files stored in an AWS S3 bucket. It uses the `pdfplumber` library to extract text and tables from PDF documents.
- [gpg_private_keys](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/gpg_private_keys) - This example shows how to use GPG private keys to sign data.
- [hashes](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/hashes) - This example shows how to calculate a hash of fields to be used as primary key. This is useful in scenarios where the incoming rows do not have any field suitable to be used as a Primary Key.
- [parallel_fetching_from_source](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/parallel_fetching_from_source) - This example shows how to fetch multiple files from an AWS S3 bucket in parallel and upsert them into destination using the Connector SDK. It uses the `concurrent.futures` module to create a thread pool and fetch files concurrently.

#### Pagination patterns

- [keyset](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/keyset) - This is a simple example of how to work with key-based pagination for a REST API.
- [next_page_url](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/next_page_url) - This is a simple example for how to work with next-page-url pagination for a REST API.
- [offset_based](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/offset_based) - This is a simple example of how to work with offset-based pagination for a REST API.
- [page_number](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/page_number) - This is a simple example for how to work with page-number-based pagination for a REST API.
- [complex_error_handling_multithreading](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/complex_error_handling_multithreading) - This example demonstrates how to implement next-page URL pagination with multithreading for parallel record processing. It includes comprehensive error handling strategies such as circuit breaker pattern, retry logic with exponential backoff, error categorization, graceful degradation, and thread-safe operations for building resilient connectors.

#### Database-specific patterns

- [key_based_replication](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/key_based_replication) - This example shows key-based replication from database sources. Replication keys are columns that are used to identify new and updated data for replication. When you set a table to use Incremental Replication, you’ll also need to define a replication key for that table.
- [schema_from_database](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/schema_from_database) - This example shows how to extract tables (columns, data types, etc.) from a schema present in Snowflake database and use this to generate the connector schema. This approach ensures that the tables in your connector match those in your source database without having to manually define each field.
- [server_side_cursors](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/server_side_cursors) - This example shows how to use server-side cursors to efficiently fetch large datasets from a PostgreSQL database without loading all the data into the memory at once. You need to provide your PostgreSQL credentials for this example to work.

#### Schema and typing

- [specified_types](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/specified_types) - This example declares a schema and upserts all data types.
- [unspecified_types](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/unspecified_types) - This example upserts all data types without specifying a schema.
- [schema_change](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/schema_change) - This is an example that illustrates how a deployed Connector SDK connection uses Fivetran's native [data type changes](https://fivetran.com/docs/core-concepts#changingdatatype) to change data types in the destination if they are changed in the source data.


#### Error handling and resilience

- [error_handling](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/errors) - This example shows how to handle errors throughout the Connector SDK process and is driven by the configuration.json error_simulation_type value.
- [update_and_delete](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/update_and_delete) - This example shows how to handle composite primary keys while using update and delete operations with a PostgreSQL database as the data source.


#### SSH Tunnels

- [Key-based Authentication](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/ssh_tunnels/key_based_authentication) - This example demonstrates how to connect to an SSH server using key-based authentication with the Fivetran Connector SDK. The connector securely establishes an SSH session to a remote EC2 instance running the fivetran-api-playground server and facilitates data interaction over the SSH tunnel.
- [Password-based Authentication](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/ssh_tunnels/password_based_authentication) - This example demonstrates how to connect to an SSH server using password-based authentication with the Fivetran Connector SDK. The connector securely establishes an SSH session to a remote EC2 instance running the fivetran-api-playground server and facilitates data interaction over the SSH Tunnel. This setup uses passwords for authentication.
- [using_bastion_server](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/ssh_tunnels/using_bastion_server) - This example shows how to connect to a database server behind a bastion server using SSH tunneling. It uses the `sshtunnel` library to create an SSH tunnel and `psycopg2-binary` to connect to a PostgreSQL database through the tunnel.

#### Data handling

- [data_handling_patterns](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/data_handling_patterns) - This example demonstrates three common patterns for handling nested API data: flattening a single nested object into individual columns, breaking a nested list into parent and child tables, and storing a complex or variable-structure object as a JSON blob column.
- [three_operations](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/three_operations) - This example shows how to use upsert, update and delete operations.
- [tracking_tables](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/tracking_tables) - This example shows how to track tables that have already been synced in order to be able add new tables and have them automatically sync back to an initial timestamp.
- [update_configuration_during_sync](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/update_configuration_during_sync) - This example shows how to update the configuration of the connector during a sync. It demonstrates how to modify the configuration values based on certain conditions using the Fivetran REST API.

#### Workflows

- [github](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/workflows/github) - This is an example of a GitHub workflow to deploy a hello connector after a push to the hello directory. It uses GitHub secrets and environment variables to create a configuration.json file that is included in the deployment.
</details>

### Private Preview examples

These examples rely on features that are currently in Private preview. To enable these features for your connector, please contact Fivetran professional services.

<details open>
<summary>List of Private Preview examples</summary>

- [Importing External Libraries and Drivers](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/private_preview_features/importing_external_drivers)
  - This feature enables you to install drivers in your connector environment by writing a `installation.sh` file in the `drivers` folder, in the same directory as your connector.py file. This script will be executed at the time of deploying your connector, before your connector.py is run to sync your data.
- [Sybase IQ](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/private_preview_features/sybase_iq)
  - This feature enables you to connect to Sybase IQ database using the `FreeTDS` driver and `PyODBC` by writing a `installation.sh` file in the `drivers` folder. This script will be executed at the time of deploying your connector, before your connector.py is run to sync your data.
- [Sybase ASE](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/private_preview_features/sybase_ase)
  - This feature enables you to connect to Sybase ASE database using the `FreeTDS` driver and `PyODBC` by writing a `installation.sh` file in the `drivers` folder. This script will be executed at the time of deploying your connector, before your connector.py is run to sync your data.
- [ibm_infomix_using_jaydebeapi](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/private_preview_features/ibm_infomix_using_jaydebeapi)
  - This example shows how to connect and sync data from IBM Informix using Connector SDK. This example uses the `jaydebeapi` library with external JDBC Informix driver, using `installation.sh` file in the `drivers` folder, to connect to the Informix database and fetch data.

</details>

## AI and Connector SDK
- [Readme](https://github.com/fivetran/fivetran_connector_sdk/blob/main/all_things_ai/tutorials/README.md) - This is an introduction to using AI tools to leverage Connector SDK.
- [agents.md](https://github.com/fivetran/fivetran_connector_sdk/blob/main/all_things_ai/ai_agents/AGENTS.md) - This is a system instruction file that can be used in any IDE, API call or conversation with AI to rapidly develop Connector SDK solutions while following best practice.
- [claude_pokeapi tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/claude/pokeapi_tutorial) - This example contains the code produced by Claude AI to build a custom connector using our Connector SDK. See our [blog article](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai) for more details.
- [claude_fda_drug tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/claude/fda_drug_tutorial) - This example demonstrates how to use Claude to create a CSDK connector to get data from the FDA drug API.
- [cursor_fda_food tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/cursor/fda_food_tutorial/fda_food_connector) - This example demonstrates how to use Cursor to create a CSDK connector to get data from the FDA food API.
- [vscode_fda_tobacco tutorial](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/vscode/fda_tobacco_tutorial/fda_tobacco_connector) - This example demonstrates how to use VSCode to create a CSDK connector to get data from the FDA tobacco API.

- [snowflake-cortex-livestock-weather-intelligence](https://github.com/fivetran/fivetran_connector_sdk/tree/main/all_things_ai/tutorials/snowflake-cortex-livestock-weather-intelligence) - This example demonstrates real-time AI enrichment via Snowflake Cortex Agent REST API during Fivetran data ingestion. It syncs weather forecasts and enriches them with livestock health risk assessments using Snowflake's llama3.3-70b model with Cortex Analyst. It shows how to integrate Snowflake Intelligence into Fivetran pipelines for any industry vertical.
> Note: As of Connector SDK version 2.0.0, `yield` is no longer required for Connector SDK operations. This folder contains examples that still use `yield`, but we recommend using the latest version of Connector SDK and avoiding `yield` in your connector code. For more information, refer to our [Connector SDK release notes](https://fivetran.com/docs/connector-sdk/changelog#august2025).

## Issue
Found an issue? Submit the [issue](https://github.com/fivetran/fivetran_connector_sdk/issues) and get connected to a Fivetran developer.

## Support
Learn how we [support Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk#support).

## Contributing

We welcome contributions to the Fivetran Connector SDK repository. 

This repository is open source and intended specifically for Connector SDK examples. We encourage the community to contribute by suggesting improvements, bug fixes, new examples, and additional use cases that expand and strengthen the collection.

### How to contribute

Please read the [CONTRIBUTING.md](https://github.com/fivetran/fivetran_connector_sdk/blob/main/CONTRIBUTING.md) guide for detailed information on contributing to this repository.

We appreciate all contributions, whether they're small bug fixes or major new features.

## Additional considerations

We provide examples to help you effectively use Fivetran's Connector SDK. While we've tested the code provided in these examples, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples.

Note that API calls made by your Connector SDK connection may count towards your service’s API call allocation. Exceeding this limit could trigger rate limits, potentially impacting other uses of the source API.

It's important to choose the right design pattern for your target API. Using an inappropriate pattern may lead to data integrity issues. We recommend that you review all our examples carefully to select the one that best suits your target API. Keep in mind that some APIs may not support patterns for which we currently have examples.

As with other new connections, Connector SDK connections have a [14-day trial period](https://fivetran.com/docs/getting-started/free-trials#newconnectorfreeuseperiod) during which your usage counts towards free [MAR](https://fivetran.com/docs/usage-based-pricing). After the 14-day trial period, your usage counts towards paid MAR. To avoid incurring charges, pause or delete any connections you created to run these examples before the trial ends.

## Maintenance
The `fivetran_connector_sdk` repository is actively maintained by Fivetran Developers. Reach out to our [Support team](https://support.fivetran.com/hc/en-us) for any inquiries.
