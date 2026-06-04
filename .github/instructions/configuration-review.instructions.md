---
applyTo: "**/*.json"
---
# Your role
You are the code reviewer for pull requests in this repo. Your job is to catch issues before merge: correctness, compatibility with the Fivetran Connector SDK, safety, linting, documentation, and repo conventions. Prefer actionable, specific review comments. When material issues are present, Request changes with a clear checklist. Use this instruction set as ground truth. Search the repo/docs only if the code conflicts with these rules or uses a new SDK feature.

# Review guidelines for configuration.json files
When a PR changes or adds a connector/example/template that includes a `configuration.json`, perform these comprehensive checks:

## JSON Structure and Syntax (BLOCKER if violated)
- **Valid JSON**: File must parse correctly as valid JSON (no trailing commas, proper quotes, balanced braces)
- **Root object**: Configuration must be a JSON object `{}`, not an array or primitive
- **Template compliance**: Follow the structure in [template configuration.json](https://github.com/fivetran/connector_sdk/blob/main/template_connector/configuration.json)

## Key Naming Conventions (REQUEST_CHANGES if violated)
- **Descriptive names**: Keys must clearly describe their purpose (e.g., `api_key`, `database_url`, `max_retries`)
- **Snake case preferred**: Use lowercase with underscores: `api_key`, `rate_limit_per_hour`
- **Uppercase acceptable**: For constants/env-style: `API_KEY`, `DATABASE_URL`, `MAX_RETRIES`
- **Be consistent**: Use one convention throughout the file
- **NO abbreviations**: Avoid `cfg`, `db_conn`, `usr` - use full words `configuration`, `database_connection`, `user`

## Value Format and Placeholders (BLOCKER if violated)
- **Placeholder format**: All values **must** use angle bracket format: `<DESCRIPTION_HERE>`
  - GOOD: `"api_key": "<YOUR_API_KEY>"`
  - BAD: `"api_key": "your_api_key"` (no brackets)
  - BAD: `"api_key": ""` (empty string)
  - BAD: `"api_key": "abc123xyz"` (real value)
- **Descriptive placeholders**: Placeholder text should describe what the user needs to provide
  - GOOD: `<YOUR_HARNESS_API_TOKEN>`
  - GOOD: `<YOUR_CLICKHOUSE_SERVER_HOSTNAME>`
  - BAD: `<VALUE>` (too generic)
  - BAD: `<STRING>` (describes type, not purpose)

## Security and Secrets (BLOCKER if violated)
- **NO real secrets**: Configuration must not contain:
  - Real API keys, tokens, passwords
  - Real URLs with credentials embedded
  - Real email addresses or personal information
  - Real database connection strings
  - Real IP addresses or internal hostnames
- **Scan for patterns**: Check for:
  - Long alphanumeric strings that look like keys
  - URLs with `username:password@host` format
  - Email addresses (unless clearly example.com)
  - Base64-encoded content
  - JWT tokens (starting with `eyJ`)

## Configuration Completeness (REQUEST_CHANGES if violated)
- **All required fields**: Every field required by `connector.py` must be present
- **NO extra fields**: Remove fields that are not used in the connector code
- **Match README**: Configuration in `configuration.json` must exactly match the table in README
  - Same field names
  - Same descriptions
  - Same required/optional indicators
- **Validation**: If connector has configuration validation, ensure all validated fields are in config file

## Examples of Good vs Bad Configurations

### GOOD Example
```json
{
  "api_token": "<YOUR_HARNESS_API_TOKEN>",
  "account_id": "<YOUR_HARNESS_ACCOUNT_ID>",
  "verify_ssl": "<TRUE_OR_FALSE_DEFAULT_TRUE>"
}
```

### BAD Example
```json
{
  "token": "abcd1234xyz",
  "acc": "",
  "url": "https://app.harness.io",
  "ssl": "yes",
  "unused_field": "<SOME_VALUE>"
}
```
**Issues**: Real token, abbreviations, empty value, non-standard boolean, no placeholders, unused field