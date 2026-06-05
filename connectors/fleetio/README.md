# Fleetio Connector Example

The Fleetio Connector allows Fleetio customers to easily pull their data into their destination databases with Fivetran.
For more information about Fleetio, check out [Fleetio site](https://www.fleetio.com) or [contact Fleetio](https://www.fleetio.com/contact)!
If you need more details about the endpoints pulled by the connector, visit Fleetio's [API docs](https://developer.fleetio.com/docs/category/api).

## Connector overview

This connector allows Fleetio customers on a [Professional Plan](https://www.fleetio.com/pricing) or above to bring in their most crucial data into any destination systems.
With their data all in one place, a customer can create custom reporting for insight into the operation of their fleets.

## Accreditation

This example was contributed by [Fleetio](https://www.fleetio.com/).


## Requirements

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/fleetio
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Configuration file

To authenticate to your fleet data, update the configuration file with your details.
The Fleetio API is authenticated by API Key.
You can generate your Account Token and API Key [here](https://secure.fleetio.com/api_keys).

```
{
    "Account-Token": "<accountToken>",
    "Authorization": "Token <ApiKey>"
}
```

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The requirements file imports any libraries necessary for our connector to work.
We currently only need a package for flattening the JSON information that's returned by the Fleetio API.

```
flatten_json==0.1.14
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Pagination

The connector paginates by checking whether `next_cursor` is returned by the endpoint and then calling the API with `start_cursor` set to that. 
The connector stops once `next_cursor` is null.
See the function `continue_pagination` from lines 176-185 for more details on implementation.

## Data handling

All data that comes in through the Fleetio API is flattened by one level before being upserted into the destination table.
The primary key for all tables for the upsert is the `id` field. 
There are certain columns that are kept as JSON or lists that mainly hold custom fields and labels; if you're interested in finding out which columns are kept nested, i.e., which are set to the JSON data type, please check the base_schema defined from lines 17-160.

## Error handling

From lines 189-197 in `connector.py`, there's a try block when making the call to the Fleetio API. 
If the API returns any errors, they are recorded in the Fivetran log and displayed in the Fivetran dashboard.

## Tables Created
The following tables are synced to the destination:
* `contacts`
    * A Contact is a person employed by your organization or a person with whom your organization does business.
* `expense_entries`
    * An Expense Entry is a record of a cost associated with a Vehicle. 
* `fuel_entries`
    * Fuel Entries represent a fuel transaction in Fleetio and are an important feature to maximize your data. 
    They contain all of the relevant information for the fuel-up, such as vendor and odometer information.
* `issues`
    * Issues in Fleetio allows users to log and track unexpected, unplanned, or "one-time" problems and repairs.
* `parts`
    * Parts management is key to running an efficient fleet. 
    Fleetio makes it easy to keep track of Parts data, including Part Manufacturer, Vendor, and Location. 
* `purchase_orders`
    * Purchase Orders in Fleetio are designed to help standardize Parts procurement through a purchasing workflow.
* `service_entries`
    * Service Entries are a simple way to log completed Service Tasks and Issues-the routine Preventative Maintenance and one-time repairs that are performed on Vehicles in Fleetio.
* `submitted_inspection_forms`
    * Submitted Inspection Forms are Inspection Forms that have been completed and submitted. 
* `vehicles`
    * A "vehicle" represents any asset or unit of equipment-moving or otherwise-managed in Fleetio.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.