# Introduction

This document defines coding standards to ensure consistency and maintainability in our Connector SDK Python examples codebase. Adhering to these guidelines will make our code easier to read and understand and reduce the likelihood of errors and bugs.

## Coding style guide

Please refer to the official [PEP8 style guide](https://peps.python.org/pep-0008/) for detailed guidelines. PEP8 is continuously updated to reflect any new changes introduced to the Python programming language.

Make sure to also read [PEP257](https://peps.python.org/pep-0257/) for docstring conventions.

## Linting

We use [flake8](https://pypi.org/project/flake8/) for linting, i.e., analyzing source code to identify potential errors, stylistic issues, and deviations from coding standards.

You can install flake8 with:

```bash
pip install flake8
```

This repository, already contains the `.flake8` config file at the root level, which scans only relevant errors without too much noise.

The PRs also have an automation which prints the errors after each commit. This maintains the health of our examples in the repository.

## Formatting

We use [black](https://black.readthedocs.io/en/stable/index.html) for formatting the code. 
Run the `.github/scripts/setup-hooks.sh` script from the root of the repository to set up pre-commit hooks. This ensures that your code is formatted correctly and passes all tests before you commit them.

## Common naming principles

We follow these general principles for naming in our code:

### 1. A name expresses a single concept or intention

```python
# Bad: Does not express any concept
tmp = 42

# Good: Name expresses a clear concept
packet_size = 1024


# Bad: Expresses two intentions — fetch and process
def fetch_and_process_items():
    pass  # ambiguous: does too much

# Good: Expresses a single intention per name
def fetch_items():
    pass  # only fetches data

def process_items(items):
    pass  # only processes data

```

### 2. A name is as short as possible yet descriptive

```python
# Bad: Too long and hard to scan quickly
should_notify_if_last_seen_state_does_not_match_with_state_in_db = True

# Good: Shorter yet clearly conveys the same idea
should_notify_if_state_mutates = True

```

### 3. Abbreviations are avoided unless it's an industry standard abbreviation (such as HTTP, ELT, and DB)

```python
# Bad: Avoid non-standard abbreviations
intgr_repository = None          # unclear
oprn_timestamp = None            # unclear

# Good: Use full descriptive names or accepted abbreviations
http_client = HttpClient()              # HTTP is industry-standard
db_connection = get_database_connection()  # DB is acceptable
integration_repository = IntegrationRepository()
operation_timestamp = get_current_timestamp()

```

### 4. A name does not contain implementation details

```python
# Bad: Exposing implementation details (should be avoided)
table_definition_map = {}                 # "map" tells us it's a dict
table_refs_with_cache_fallback = []      # "cache" is internal logic
item_list = []                            # "list" leaks the container type

# Good naming: describes meaning, not implementation
table_definition_by_table_ref = {}       # tells us the relationship
table_refs = []                           # clear and simple
items = []                                # concise and descriptive

```

### 5. If an entity encapsulates a well-known pattern or algorithm, it is recommended to reflect it in its name

```python
# Bad: Generic helper name — hides the design intent
class TreeTraversalHelper:
    pass

# Good: Clearly communicates it's implementing the Visitor pattern
class TreeNodeVisitor:
    def visit(self, node):
        pass

# Good: Indicates this follows the Strategy pattern (e.g. pluggable merge behavior)
class MergeStrategy:
    def merge(self, a, b):
        pass

# Good: Suggests internal queuing, often tied to producer-consumer or worker patterns
class WriterQueue:
    def enqueue(self, data):
        pass

    def process(self):
        pass

```

### 6. Antonyms are used for opposing entities

```python
# Bad: Mismatched antonyms
begin = 0
last = 99               # should be "end"

first_element = items[0]
end_element = items[-1] # should be "last_element"

# Good: Correct antonym usage
begin_index = 0
end_index = len(items) - 1

first_element = items[0]
last_element = items[-1]

```

## Directories

Directories must be named in `lowercase_with_underscores`.

```python
# Bad: Names
examples/quickstart_examples/MultipleCode_Files_With_SubDirectory_Structure
examples/quickstart_examples/Multiple_Code_Files_With_Sub_Directory_Structure

# Good: Names
examples/quickstart_examples/multiple_code_files_with_sub_directory_structure
```

## Classes

### 1. Class names are UpperCamelCase

```python
# Bad: Not UpperCamelCase
class aws_credentials_provider:
    pass

class Aws_Credentials_Provider:
    pass

# Good: Correct
class AwsCredentialsProvider:
    pass

```

### 2. Class names are nouns

```python
# Bad: Verb-based name — not ideal
class ExecuteSchemaMigration:
    def execute(self):
        pass

# Good: Noun-based class name
class SchemaMigrationExecutor:
    def execute(self):
        pass

# Good: Other examples
class AzureStorageClient:
    def upload(self, file):
        pass

class S3TransferManager:
    def transfer(self, src, dest):
        pass

class StateService:
    def save_state(self):
        pass

```

### 3. Class names are singular; stateless utility class names can be plural

```python
# Bad: name is plural, but class likely holds state
class StoragePointers:
    def __init__(self, pointers):
        self._pointers = pointers

# Good: singular noun, reflects the nature of the object
class StoragePointerSet:
    def __init__(self):
        self._set = set()

# Good: stateless utility class (can also use a module instead)
class ExceptionUtils:
    @staticmethod
    def log_and_raise(exception):
        print("Logging:", exception)
        raise exception

```

## Methods

You should split the code into small methods which are easy to follow and maintain. Each function should have a proper name and PyDoc string describing its purpose along with parameters.

Aim for a [cylcomatic complexity](https://en.wikipedia.org/wiki/Cyclomatic_complexity) of less than 10 in the methods.

```python
Non-compliant Example:
def get_data(api_key, updated_at):
"""
    Fetch data from the Common Paper API.
"""
What data?
...


Compliant Example:
def fetch_agreements(api_key, updated_at):
    """
    Fetch agreements from the Common Paper API with updated_at filter.
    Implements retry logic with exponential backoff for up to 3 attempts.
    Args:
        api_key (str): The API key for authentication
        updated_at (str): ISO format timestamp to filter agreements updated after this time  
    Returns:
        dict: JSON response containing agreement data
    Raises:
        Exception: If the API request fails after 3 retry attempts
    """ 
```

### 1. Method names are snake_case

```python
# Bad:
def doSomethingImportant(): ...

# Good: Python-style (PEP 8)
def do_something_important(): ...
```

### 2. Method names are verbs or verb phrases (with nouns and adjectives if required)

```python
# Bad: Too generic or non-actionable
def data(): ...
def process(): ...

# Good Examples
def save_to_database(): ...
def fetch_items(): ...
def clear_cache(): ...
def normalize_text(): ...
```

### 3. Builder and factory method names may omit verbs

```python
class User:
    @classmethod
    def from_json(cls, data):  # No verb, yet clear from context
        ...

    @classmethod
    def create_anonymous(cls):  # Verb form also fine
        ...
```

### 4. Method names do not contain ambiguity in numerical ranges

```python
# Bad: Ambiguous
def get_first_n_items(n): ...

# Good: Clearer
def get_top_n_items(n): ...
def get_items_in_range(start_index, end_index): ...

```

### 5. Async methods should use suffix `*_async` or prefixes like `start_`, `begin_`

```python
# Good: Prefix or suffix to signal async
async def fetch_data_async(): ...
async def start_download(): ...
```

### 6. Getter methods for boolean fields have the same names as the fields

```python
class Feature:
    def __init__(self, is_enabled):
        self._is_enabled = is_enabled

    @property
    def is_enabled(self):  # Good: same name as field
        return self._is_enabled

```

### 7. Setter methods for boolean fields use set_ prefix and don’t repeat is/has/can

```python
class Feature:
    def __init__(self):
        self._is_enabled = False

    @property
    def is_enabled(self):  # Good: getter
        return self._is_enabled

    @is_enabled.setter
    def is_enabled(self, value):  # Good: no `set_is_enabled`
        self._is_enabled = value

```

## Variables

The sections below outline the general rules for working with variables.

### 1. Variables containing measurable values have their unit in the name

```python
# Bad: Ambiguous
max_wait_time = 1000
sync_period = 5

# Good: Clear units
max_wait_time_ms = 1000
sync_period_min = 5
```

### 2. Constant names are UPPER_SNAKE_CASE

```python
# Bad: Not a constant format
max_wait_time_ms = 1000

# Good: Python constant
MAX_WAIT_TIME_MS = 1000

```

### 3. Instance, loop counters, and parameters

Use snake_case for all variable and parameter names.

```python
# Bad:
ModifiedTimestamp = None

# Good: Python style
modified_timestamp = None
```

### 4. Short loop counters and exception variables

```python
# Bad: Loop counters
for i in range(10):
    total += i

# Good: Better loop counters
for index in range(10):
    total += index

# Good: Acceptable for exceptions
try:
    do_something()
except ValueError as e:
    print(e)

# Bad: Avoid obscure single-letter names in broader scopes
for c in customers:
    process(c)  # unclear

# Good:
for customer in customers:
    process(customer)

```

### 5. Boolean variables follow the same conventions as instance/static variables but also contain is, has, can, should, etc.

```python
# Bad: Vague
rebuild_row = True

# Good: Clear intent
should_rebuild_row = True
is_enabled = False
has_null_id = True
can_merge_rows = True
```

## Defining constants 

Do not leave constant values scattered in the code. Instead, define them at the top of the code with private visibility (unless they need more).

```python
Non-compliant Example:

    for attempt in range(3):
        try:
            response = requests.get(url, headers=get_headers(api_key))
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 502, 503, 504]:  # Retryable status codes
                if attempt < 3 - 1:  # Don't sleep on the last attempt
                    delay = 1 * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    log.warning(f"Request failed with status {response.status_code}, retrying in {delay} seconds (attempt {attempt + 1}/3)")
                    time.sleep(delay)
                    continue
                else:
                    log.error(f"Failed to fetch agreements after 3 attempts. Last status: {response.status_code} - {response.text}")
                    raise RuntimeError(f"API returned {response.status_code} after 3 attempts: {response.text}")


Compliant Example:

__MAX_RETRIES = 3  # Maximum number of retry attempts for API requests
__BASE_DELAY = 1  # Base delay in seconds for API request retries

    for attempt in range(__MAX_RETRIES):
        try:
            response = requests.get(url, headers=get_headers(api_key))
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 500, 502, 503, 504]:  # Retryable status codes
                if attempt < __MAX_RETRIES - 1:  # Don't sleep on the last attempt
                    delay = __BASE_DELAY * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    log.warning(f"Request failed with status {response.status_code}, retrying in {delay} seconds (attempt {attempt + 1}/{__MAX_RETRIES})")
                    time.sleep(delay)
                    continue
                else:
                    log.error(f"Failed to fetch agreements after {__MAX_RETRIES} attempts. Last status: {response.status_code} - {response.text}")
                    raise RuntimeError(f"API returned {response.status_code} after {__MAX_RETRIES} attempts: {response.text}")

```

## Templates

Refer to our `connector.py` template and `README.md` template in this repo ([https://github.com/fivetran/fivetran_connector_sdk/tree/main/template_connector](https://github.com/fivetran/fivetran_connector_sdk/tree/main/template_connector)).

It contains some ideas about structuring your code. Review it to get a general understanding of our example format.
