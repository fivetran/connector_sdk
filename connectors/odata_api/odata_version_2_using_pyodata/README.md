## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/odata_api/odata_version_2_using_pyodata
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

## Syncing data from OData version 2

This connector allows you to sync data from OData version 2 APIs to your chosen destination through Fivetran. While OData version 4 is recommended for newer implementations, this connector supports legacy systems still using OData V2.

## Basic Usage

### Initialization

```python
from ODataClient import ODataClient
import requests
session = requests.Session()

odata_client = ODataClient(
    service_url="https://services.odata.org/V2/Northwind/Northwind.svc/", 
    session=session,
    state=state  # Pass the state from update function parameter
)
```

Parameters:
- `service_url`: URL endpoint of the OData service
- `session`: requests.Session object for maintaining connection state
- `state`: Dictionary containing checkpoint state (optional)
> NOTE: If your OData service requires authentication, set it up in the session object. Refer to the [requests documentation](https://requests.readthedocs.io/en/latest/user/advanced) for more information.

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

Query Options:

The query_options dictionary supports these parameters:
- `select`: List of fields to retrieve
- `filter`: OData filter expression as string
- `orderby`: Field(s) to order results by
- `top`: Maximum number of records to retrieve
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
        "table": "Orders_batch"
    }
)

# Execute batch and process results
state = odata_client.upsert_batch(state=state)
```

## State Management

State management is essential for efficient incremental syncs:

- Stores the last synced value in state
- Uses that value in a filter expression
- Defines which field to track with `update_state`

The client handles state management automatically when you provide the update_state parameter:

```python
update_state = {
    "lastOrderDate": "OrderDate"  # Maps state variable to record field
}
```

This configuration:  
- Updates the lastOrderDate state variable with the value from the OrderDate field
- Uses the highest value found during the current sync
- Automatically checkpoints the state after processing

```python
# Get last synced date from state
last_order_date = state.get("lastOrderDate", '1990-01-01T00:00:00')

entity = {
    "entity_set": "Orders",
    "query_options": {
        'select': ['OrderID', 'CustomerID', 'OrderDate'],
        'filter': f"OrderDate gt datetime'{last_order_date}'"
    },
    "table": "Orders_Inc",
    "update_state": update_state # Maps state variable to record field
}

# Execute incremental sync
state = odata_client.upsert_entity(entity=entity)
```

If no `update_state` is provided, a full sync will be performed without tracking progress.

> NOTE: The client automatically filters out OData metadata fields (containing `@odata`) from results.

## Customizing the Connector for Your Service

Follow these steps to adapt this connector for your specific OData V2 service:

### Step 1: Identify Your Service Requirements
1. Determine the service URL endpoint
2. Identify authentication requirements (Basic, OAuth, API keys)
3. Identify the entities (tables) you need to sync
4. Note any special handling requirements for data types or relationships

### Step 2: Configure Authentication

If your service requires authentication:

```python
session = requests.Session()

# Basic authentication
session.auth = ('username', 'password')

# OR API key in header
session.headers.update({'API-Key': 'your-api-key'})

# OR OAuth token
session.headers.update({'Authorization': 'Bearer your-oauth-token'})
```

For more details on authentication, refer to the [requests library documentation](https://requests.readthedocs.io/en/latest/user/authentication.html).

### Step 3: Define Your Schema

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

### Step 4: Configure Entity Operations

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

### Step 5: Handling Special Cases

#### Custom Date/Time Formats

If your service uses non-standard datetime formats, modify the `clean_odata_fields` method in `ODataClient.py`:

```python
@staticmethod
def clean_odata_fields(data):
    # Add custom date handling
    if isinstance(data, datetime.datetime):
        return data.strftime('%Y-%m-%d %H:%M:%S')  # Custom format
    # Rest of the method...
```

Ensure that you handle the custom format in the state as well if you're using it for incremental sync.
You can also handle other data as applicable in a similar way.

#### Handling Rate Limits

If your service has rate limits, add retry logic:

```python
def upsert_entity(self, entity, state: Dict = None):
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Existing code...
            return self.state
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                retry_count += 1
                time.sleep(60)  # Wait before retrying
            else:
                raise
```

You can modify the methods in `ODataClient.py` to handle specific cases for your service. The above examples provide a starting point for common scenarios. You can refer to the comments in the code for more details.