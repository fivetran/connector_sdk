# OData API Connector using python_odata

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/odata_api/odata_version_4_using_python_odata
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

This connector demonstrates how to fetch data from an OData v4 API and sync it to the destination using the python_odata library.

### Overview

This connector:
- Connects to the Northwind OData v4 sample service
- Fetches customers and orders data
- Supports filtering and incremental syncs
- Demonstrates how to query OData v4 endpoints


### Schema Definition

The connector defines three tables:
- `Customers`: All customer data
- `Filtered_Customers`: Customers whose contact name starts with 'S'
- `Orders`: Order data with incremental sync support

You can customize the schema to match your OData service and destination tables. For more reference about the schema method, see the [Fivetran Connector SDK documentation](https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema).


### Key Functions

- `setup_odata_service()`: Establishes a connection to the OData service using `requests.Session()` to maintain the connection state, headers, and authentication. Additional headers can be added as needed, and the authentication method can be configured using this method.

- `upsert_all_customers()`: Fetches all customers data from the OData service and upserts them into the destination. For your use case, this method can be modified to include additional logic.

Similarly, other methods like `upsert_all_orders` and `upsert_customer_name_starting_with_s` use python_odata library to query the odata api and sync the data to the destination.


### Customizing for Your OData API

To adapt this connector for your own OData service:

1. **Update the service URL**:
   ```python
   service_url = 'https://your-odata-service-url/'
   ```

2. **Add authentication** if required:

   ```python
   session = requests.Session()
   session.auth = ('username', 'password')  # Basic auth
   # OR
   session.headers.update({'Authorization': 'Bearer your_token'})  # OAuth
   ```
   
    For more details on authentication, refer to the [requests library documentation](https://docs.python-requests.org/en/latest/user/advanced/#session-objects).

3. **Modify the schema function** to match your data structure:

   ```python
   def schema(configuration: dict):
       return [
           {
               "table": "YourEntityName",
               "primary_key": ["YourPrimaryKeyField"],
               "columns": {
                   # Column definitions (optional)
               },
           },
       ]
   ```

4. **Update entity queries** in the functions:

   ```python
   entity = service.entities['YourEntityName']
   query = service.query(entity)
   ```
   
   Replace `YourEntityName` with the actual entity name you want to query.

5. **Adjust filters** for your specific requirements:

   ```python
   query = query.filter(entity.YourField > 'YourValue')
   # OR
   query = query.filter(entity.YourField.startswith('Value'))
   ```
   
   Replace `YourField` and `YourValue` with the actual field names and values you want to filter by.


### Additional Resources

- [Python OData Documentation](https://tuomur-python-odata.readthedocs.io/en/latest/)
- [OData Protocol Documentation](https://www.odata.org/documentation/)
- [Fivetran Connector SDK Technical Reference](https://fivetran.com/docs/connectors/connector-sdk/technical-reference)
- [Fivetran Connector SDK Best Practices](https://fivetran.com/docs/connector-sdk/best-practices)