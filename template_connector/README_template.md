# Connector SDK Individual Example README.md Structure Template

*Instructions: Every example added to the repository should have a comprehensive README.md to make it easy for users landing directly on the README to understand what the example does, how to configure it for their own use, and how to find more information about working with Connector SDK.*

*For source examples, the top-level (H1) heading must be in the following format: "# <source-name> Connector Example" (e.g. "# GitHub Connector Example").*

*To use the template, replace the italicized text with your own description. Non-italicized text is common to all READMEs and can be left as is.*

*If a particular section is not relevant to your example (e.g. Error Handling \- your example doesn’t have any special error handling, Additional Files \- your example doesn’t have any additional files), delete that heading from the README.*

*Notate what section relates to what function in the connector.py using the function name (e.g. Error handling \- Refer to `def handle_critical_error(error_message, error_details=None)`)*

*Do not use Title Case for any heading level other than H1 (a single top-level heading with a single `#`).*
*Do not use Title Case in plain text that is used as unformatted subheading or item title, only capitalize the first word of subheading/item title (e.g., \- Rate limit errors – The connector automatically retries with exponential backoff, \- Data volume – Large accounts may require longer sync times, Incremental sync:).*
*Do not use **bold** text anywhere except for UI elements controls like tabs, menus, buttons, fields, etc.*
*Do not use nested bulleted lists for descriptions - write the description inline, for example, "- `mock\_api.py` – A simulated API for testing data retrieval."*
*Use the following format for notes: "Note: note text"; omit the double quotes.*
*Use numbered lists only where the order is important, for example, for a sequence of user actions. Every item in numbered lists should end with full stop.*
*Complex sequences of user actions should use numbers for parent items and Roman notation for child items, with blank lines between the lines with Roman numerals.*
*Use bulleted lists where the items are listed without any particular order or where alternatives are presented.*
*Do not duplicate the content in several sections. For example, do not add a Schema Definition section since the Tables Created section should include schema-related information.*
*Do create additional sections decribing example-specific areas if the sections present in this template do not cover them.*
*Use hyphen (-) in bulleted lists instead of asterisk (*).*
*Enclose file names in backticks, for example, `configuration.json`, `requirements.txt`, `connector.py`, `mock\_api`.*
*Do not use emojis.*



## Connector overview
*Provide a detailed overview of the connector, including its functionality, the data source it connects to, and the use cases it addresses.*


## Accreditation
*The connectors contributed by third parties may include an accreditation section to credit the contributor. If this is a Fivetran-authored example, delete this section.*

This example was contributed by [Contributor Name/Organization](link-to-profile-or-website).

*Optionally, add a brief note about the contributor's expertise or the context in which this connector was developed.*

*If the contributor prefers to remain anonymous, use: "This example was contributed by an anonymous community member."*


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/<connector-name>
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory. 
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

_Include the following note only if the connector requires a `configuration.json` file to run._
> Note : Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features
- *List key features of the connector, such as supported endpoints, data replication methods, and any special capabilities.*


## Configuration file
*Detail the configuration keys defined for your connector, which are uploaded to Fivetran from the configuration.json file.* 

```
{
  "api_key": "YOUR_API_KEY",
  "base_url": "https://api.example.com",
  "start_date": "2023-01-01"
}
```

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
*Explain the role of the `requirements.txt` file in specifying the Python libraries required by the connector.*

*Example content of `requirements.txt`:*

```
pandas
```

> Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
*Explain the authentication mechanism used to access the source (e.g., API Key, OAuth2) and provide steps to obtain necessary credentials.*


## Pagination
*Describe how the connector handles pagination when retrieving data from the source.*


## Data handling
*Outline how data is processed, transformed, and delivered to Fivetran, including information on schema mapping and data types.*


## Error handling
*Explain the error-handling strategies implemented in the connector.*



## Tables created

*(Optional) If the ERD is available, add the ERD file to the same folder as the example's README.md and add the ERD link at beginning of this section using the below example as a template.* 
*Example: "The entity-relationship diagram (ERD) below shows how tables are linked in the <source-name> schema."*
*![<source-name>-ERD](<source-name-ERD>.png)*

*Summary of tables replicated.*

*(Optional) Screenshot of the schema objects generated*


## Additional files
*Some connectors include additional files to modularize functionality. Provide a description of each additional file and its purpose.*

- `mock\_api.py` – *A simulated API for testing data retrieval.*  
- `users\_sync.py` – *Handles user data synchronization logic.*  
- `api\_threading\_utils.py` – *Manages API request threading for performance optimization.*  
- `constants.py` – *Stores constant values used throughout the connector.*


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
