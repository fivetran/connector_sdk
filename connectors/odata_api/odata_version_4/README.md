## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/odata_api/odata_version_4
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Syncing data from OData version 4

This connector allows you to sync data from OData version 4 services to your Fivetran destination. OData (Open Data Protocol) is a REST-based protocol for querying and updating data, and version 4 is the latest version offering enhanced flexibility and features.

## Basic Usage

### Initialization

```python
from ODataClient import ODataClient
import requests
session = requests.Session()

odata_client = ODataClient(
    service_url="https://services.odata.org/V4/Northwind/Northwind.svc/", 
    session=session,
    state=state  # Pass the state from update function parameter
)
```

Parameters:
- `service_url`: URL endpoint of the OData service
- `session`: requests.Session object for maintaining connection state
- `state`: Dictionary containing checkpoint state (optional)
> NOTE : If your OData service requires authentication, you can set the authentication in the session object. Refer to the [requests documentation](https://requests.readthedocs.io/en/latest/user/advanced) for more information.

### Fetching data

```python
# Define entity and query configuration
entity = {
    "entity_set": "Products",
    "query_options": {
        'select': ['ProductID', 'ProductName', 'UnitPrice'],
        'filter': "UnitPrice gt 20.0"
    },
    "table": "Products"
}

# Execute the query and upsert data
state = odata_client.upsert_entity(entity=entity)
```

#### Query Options

The `query_options` dictionary supports these parameters:
- `select`: List of fields to retrieve
- `filter`: OData filter expression as string
- `orderby`: Field(s) to order results by
- `top`: Maximum number of records to retrieve
- `skip`: Number of records to skip from beginning
- `expand`: Dictionary defining related entities to expand

## Advanced Usage

### Expanded Relationships

Fetch related entities along with the main entity:

```python
query_options = {
    'select': ['OrderID', 'CustomerID', 'OrderDate'],
    'expand': {
        'Order_Details': {
            'select': ['ProductID', 'UnitPrice', 'Quantity']
        }
    }
}

entity = {
    "entity_set": "Orders",
    "query_options": query_options,
    "table": "Orders"
}

odata_client.upsert_entity(entity=entity)
```

### Incremental Sync

For efficient syncs that only fetch new or changed data:

```python
# Get last synced value from state
last_order_date = state.get("lastOrderDate", '1990-01-01T00:00:00')

# Define query with filter using the state value
entity = {
    "entity_set": "Orders",
    "query_options": {
        'select': ['OrderID', 'CustomerID', 'OrderDate'],
        'filter': f"OrderDate gt datetime'{last_order_date}'"
    },
    "table": "Orders_Inc",
    "update_state": {
        "lastOrderDate": "OrderDate"  # Maps state variable to record field
    }
}

# Execute incremental sync
state = odata_client.upsert_entity(entity=entity)
```

### Multiple Entity Operations

Sync data from multiple entity sets:

```python
entity_list = [
    {
        "entity_set": "Customers",
        "query_options": {"select": ["CustomerID", "CompanyName", "Country"]},
        "table": "Customers_Multiple"
    },
    {
        "entity_set": "Products",
        "query_options": {"select": ["ProductID", "ProductName", "UnitPrice"]},
        "table": "Products_Multiple"
    }
]

state = odata_client.upsert_multiple_entity(entity_list=entity_list, state=state)
```

### Batch Operations

For more efficient data retrieval, use batch operations to combine multiple requests:

```python
# Add requests to batch (supports method chaining)
odata_client.add_batch(
    entity={
        "entity_set": "Customers",
        "query_options": {'select': ['CustomerID', 'CompanyName']},
        "table": "Customers_batch"
    }
).add_batch(
    entity={
        "entity_set": "Orders",
        "query_options": {'select': ['OrderID', 'OrderDate']},
        "table": "Orders_batch",
        "update_state": {
            "lastOrderDate": "OrderDate"  # Track last order date
        }
    }
)

# Execute batch and process results
state = odata_client.upsert_batch(state=state)
```

## State Management

State management enables incremental syncs by tracking progress:

```python
# Get last synced date from state
last_order_date = state.get("lastOrderDate", '1990-01-01T00:00:00')

update_state = {
    "lastOrderDate": "OrderDate"  # Maps state variable to record field
}

entity = {
    "entity_set": "Orders",
    "query_options": {
        'select': ['OrderID', 'CustomerID', 'OrderDate'],
        'filter': f"OrderDate gt datetime'{last_order_date}'"
    },
    "table": "Orders_Inc",
    "update_state": update_state
}

state = odata_client.upsert_entity(entity=entity)
```

The client will:
- Update the `lastOrderDate` state variable with the highest value from the `OrderDate` field
- Automatically checkpoint the state after processing

> **Note**: If no `update_state` is provided, a full sync will be performed without tracking progress.

## Customizing the Connector for Your OData Service

Many OData services have unique requirements or behaviors. Here's how to customize the connector for your specific use case:

### Step 1: Set Up Authentication

If your OData service requires authentication:

```python
session = requests.Session()

# Basic Authentication
session.auth = ('username', 'password')

# OR OAuth/Bearer token
session.headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_TOKEN'
}

# OR Custom Headers
session.headers.update({
    'Custom-Header': 'value'
})
```

For more details on authentication, refer to the [requests library documentation](https://requests.readthedocs.io/en/latest/user/authentication.html).

### Step 2: Adjust Response Format Handling

If your OData service returns data in a non-standard structure, modify the `_standardize_output` method in `ODataClient.py`:

```python
def _standardize_output(self, response: Dict) -> Dict:
    # Create custom handling for your specific OData provider
    result = {
        "data": [],
        "count": 0,
        "success": False
    }
    
    # Example: Service returns data in a custom format
    if "results" in response:
        result["data"] = ODataClient.clean_odata_fields(data=response["results"])
    elif "value" in response:
        result["data"] = ODataClient.clean_odata_fields(data=response["value"])
    
    # Custom count handling
    result["count"] = len(result["data"])
    result["success"] = True
    
    return result
```

### Step 3: Customize Metadata Handling

Modify the `clean_odata_fields` method if your service has specific metadata fields:

```python
@staticmethod
def clean_odata_fields(data):
    # Keep specific metadata fields if needed
    if isinstance(data, dict):
        return {k: ODataClient.clean_odata_fields(v) for k, v in data.items()
                if not (isinstance(k, str) and k.startswith('@') and k != '@myServiceMetadata')}
    # Rest of implementation...
```

You can also add custom handling for specific data types or formats in this function. This can include date formats, nested objects, or other transformations.

### Step 4: Customize Pagination Handling

If your service uses different pagination patterns:

```python
def _handle_pagination(self, initial_url: str, table: str = None, update_state: Dict = None):
    next_link = initial_url
    
    while next_link:
        current_page = self._make_request(url=next_link)
        formatted_data = self._standardize_output(response=current_page)
        
        self._upsert_formatted_data(formatted_data=formatted_data, 
                                              table=table, 
                                              update_state=update_state)
        
        # Custom pagination format
        if "__next" in current_page:
            next_link = current_page["__next"]
        elif "pagination" in current_page:
            next_link = current_page["pagination"].get("nextPage")
        else:
            next_link = None
```

### Step 5: Define Your Schema

Update the schema function in connector.py:

```python
def schema(configuration: dict):
    return [
        {
            "table": "YourEntityName", 
            "primary_key": ["YourPrimaryKeyField"], 
            "columns": {
                "FieldName1": "DATA_TYPE",
                "FieldName2": "DATA_TYPE",
                # Define complex types as JSON
                "ComplexField": "JSON",
            },
        },
        # Add more tables as needed
    ]
```

### Step 6: Configure Entity Operations

In the update function, define entities for each table you want to sync:

```python
entity = {
    "entity_set": "YourEntitySet",  # Name in OData service
    "query_options": {
        'select': ['Field1', 'Field2', 'Field3'],
        'filter': "YourFilterCondition",
        'expand': {
            'RelatedEntity': {
                'select': ['RelatedField1', 'RelatedField2']
            }
        }
    },
    "table": "YourDestinationTable",  # Name in destination
    "update_state": {
        "stateVariableName": "FieldToTrack"  # For incremental sync
    }
}
```

Repeat this for each entity you want to sync. Ensure to adjust the `entity_set` and `table` names to match your service and destination.

You can modify the methods in `ODataClient.py` to handle specific cases for your service. The above examples provide a starting point for common scenarios. You can refer to the comments in the code for more details.
