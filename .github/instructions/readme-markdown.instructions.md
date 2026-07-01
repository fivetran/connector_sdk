---
applyTo: "examples/source_examples/**/*README*.md,all_things_ai/ai_agents/**/*AGENTS*.md"
---

# Copilot Review Instructions for Fivetran Documentation

These rules override generic Copilot comments. Review all Markdown files that have "README" in their name against the following:

## Never use:
- Title Case in subheadings
- Nested bulleted lists where a simple list would be sufficient
- Bold text to stress important information. If you see bold text, you should flag this and request to change it to plain text unless this is a UI element name.
Example of wrong format and style:

"- **API example**
   - This example shows how to sync data using an API key and secret."

The correct format and style would be as follows:

"- API example - This example shows how to sync data using an API key and secret."

## Headings:

- There should be only one H1 heading in the file, and it should use Title Case, for example: # Connector SDK Somecompany API Connector Example
- All other headings should use Sentence case, for example: ## Requirements file
- Do not use numbers in headings: WRONG: "## 4. Best practices", CORRECT: "## Best practices"

## Lists:

Use bulleted lists when just listing items in no particular order or when listing the alternatives, for example:
"The management actions are as follows:
- Create connection
- Retrieve connection
- Delete connection"

Use numbered list for actions that need to be taken in a particular order, for example:
"To obtain your API key, do the following:
1. Log in to your DreemBleem account.
2. Go to **Settings > API Key**.
3. Make a note the API key and secret. You will need to add it to `configuration.json` file later."

## Comment and suggestions

The comments and suggestion you make should be deduplicated, for example - if you made a suggestion for one issue for lines 15 - 18, and then you want to post a suggestion for another issue for line 17, you should combine them in one suggestion.


---

The structure and rules below must only be honored during review for 'README.md' files, and they should be ignored for 'AGENTS*.md' and 'ft-csdk*.md' files. 

# Copilot Review Instructions: Connector SDK Example README.md

Apply these rules to every `README.md` file inside Connector SDK connector example folders.

---

## Structure

- Every README must begin with one H1 (`#`) heading in Title Case.
- All other headings must be sentence case.
- The order of the optional and required H2-level sections is as follows:

  1. Connector overview - this section is required.
  2. Requirements - this section is required.
  3. Getting started - this section is required.
  4. Features - this section is required.
  5. Configuration file - this section is optional and must be present if the `configuration.json` file is used by the connector. If this section is present, it must contain the JSON outlining the configuration parameters and that `configuration.json` should be not checked into version control to protect sensitive information.
  6. Requirements file - this section is optional and must be present if the `reqirements.txt` file is used by the connector. If this section is present, it must contain the list of imported packages that the connector requires. 
  7. Authentication - this section is optional and must be present if the connector requires authentication. If this section is present, it must mention the authentication method used, the required credentials and how to obtain the credentials as a numbered list of user actions. 
  8. Pagination - this section is optional and must be present if the connector uses pagination.
  9. Data handling - this section is required.
  10. Error handling - this section is required.
  11. Tables created - this sections is required. It needs to list all tables created in the destination, along with the list of columns and primary key for each table.
  12. Additional files - this section is optional and must be present if the connector requires additional Python files besides `connector.py`. If this section is present, it must list the additional files and their functions.
  13. Additional considerations - this section is required.

If a section is irrelevant (e.g., no error handling), the empty stub should be not present.

---
<!---
## Section Compliance

* **Connector overview** → Must explain purpose, data source, and use cases.
* **Requirements** → Must list OS and Python versions. Use provided bullet format. It is a fixed content, verbatim (no edits or omissions), as provided below:
  ```markdown
  ## Requirements
  - [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
  - Operating system:
    - Windows: 10 or later (64-bit only)
    - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
    - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
  ```   
* **Getting started** → Must include link to Connector SDK Setup Guide. It is a fixed content, verbatim (no edits or omissions), as provided below:
  ```markdown
  ## Getting started
  Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.
  ```
* **Features** → Must list concrete features (not left blank or italicized template text).
* **Configuration file** → Must include a JSON code block showing keys. Must mention that `configuration.json` should not be versioned, for example, as provided below:
  ```markdown
  ## Configuration file

  The connector requires the following configuration parameters:

  ```
  {
    "host": "<YOUR_REDSHIFT_HOST>",
    "database": "<YOUR_REDSHIFT_DATABASE>",
    "port": "<YOUR_REDSHIFT_PORT>",
    "user": "<YOUR_REDSHIFT_USER>",
    "password": "<YOUR_REDSHIFT_PASSWORD>"
  }
  ```

  Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.
  ```
  
* **Requirements file** → Must explain role of `requirements.txt` and remind that `fivetran_connector_sdk` and `requests` are excluded, for example, as provided below:
  ```markdown
  ## Requirements file
  The connector requires the `redshift_connector` package to connect to Redshift databases.

  ```
  redshift_connector
  ```

  Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.
  ```
* **Authentication** → Must specify auth method (API key, OAuth2, etc). For example, as provided below:
  ```markdown
  ## Authentication

  This connector uses username and password authentication to connect to Redshift. The credentials are specified in the configuration file and passed to the `redshift_connector.connect()` function (refer to the `connect_to_redshift()` function).

  To set up authentication:

  1. Create a Redshift user with appropriate permissions to access the required tables.
  2. Provide the username and password in the `configuration.json` file.
  3. Ensure the user has `SELECT` permissions on the tables that need to be synced.
  ```

* **Pagination / Data handling / Error handling** → Must either provide explanation + code reference (function name or line range in `connector.py`) or remove section entirely.
* **Tables created** → If ERD is present, must link to it with correct Markdown syntax and add summary of replicated tables. The table schemas should be presented as JSON or as a Markdown table, for example, as provided below:
  ```markdown
  ## Tables Created

  The connector creates a single table named `customers` with the following schema (refer to the `schema()` function):

  ```json
   {
    "table": "customers",
    "primary_key": ["customer_id"],
    "columns": {
      "customer_id": "INT",
      "first_name": "STRING",
      "last_name": "STRING",
      "email": "STRING",
      "updated_at": "UTC_DATETIME"
    }
  }
  ```
  ``` 
* **Additional files** → Must list additional Python files and explain purpose, for example, as provided below:
  ```markdown
  ## Additional files
  The connector uses the following additional files:
  - mock_api.py – A simulated API for testing data retrieval  
  - users_sync.py – Handles user data synchronization logic  
  - api_threading_utils.py – Manages API request threading for performance optimization 
  - constants.py – Stores constant values used throughout the connector
  ```
* **Additional considerations** → Must include Fivetran disclaimer about example code. It is a fixed content, verbatim (no edits or omissions):
  ```markdown
  ## Additional considerations
  The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
  ```
--->

---

## Formatting Rules

* Do not use Title Case for anything below H1.
* Use fenced code blocks with language hints (`json`, `sql`, `bash`, etc.) where relevant.
* Paths, filenames, and config keys must be inline code.
* Functions in `connector.py` must be referenced explicitly (e.g. *Refer to `def handle_error`*).
* Use bold for filenames in lists under *Additional files*.

---

## Prohibited

* Placeholder italic text like *Provide a detailed overview\...* must not remain.
* Do not copy the template verbatim without replacement.
* Do not leave empty sections with no explanation.

---

✅ **Reviewer Action**: Flag any README.md that:

* Misses a required section.
* Keeps italicized template text.
* Uses incorrect heading case.
* Omits required references to config, requirements, or connector functions.


