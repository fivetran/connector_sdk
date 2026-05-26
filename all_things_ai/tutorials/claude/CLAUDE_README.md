# Fivetran Connector SDK Development Guide with Claude AI

A comprehensive guide for building production-ready Fivetran data connectors using the Fivetran Connector SDK with Claude AI assistance. This guide follows industry best practices and ensures reliable, maintainable data pipelines.

## Overview

This guide provides a structured approach to developing Fivetran connectors using Claude AI, ensuring:
- **Production-ready code** following Fivetran's best practices
- **Reliable data pipelines** with proper error handling and logging
- **Maintainable solutions** with clear documentation and testing
- **Scalable architecture** supporting both full and incremental syncs

## Accessing Claude AI for Development

### Claude AI Access Options

#### 1. **Claude Desktop Application**
- **Download**: [claude.ai/download](https://claude.ai/download)
- **Platforms**: Windows, macOS, Linux
- **Features**: 
  - Full conversation history
  - File upload and analysis
  - Code generation and editing
  - Local development environment integration

#### 2. **Claude Web Interface**
- **URL**: [claude.ai](https://claude.ai)
- **Features**:
  - Browser-based access
  - Real-time code assistance
  - Prompt templates and examples
  - Conversation sharing capabilities

#### 3. **Claude API Integration**
- **Documentation**: [docs.anthropic.com](https://docs.anthropic.com)
- **Use Cases**:
  - Automated code generation
  - CI/CD pipeline integration
  - Custom development tools
  - Batch processing workflows

### Getting Started with Claude AI

#### Step 1: Choose Your Access Method
- **For individual development**: Use Claude Desktop or web interface
- **For team collaboration**: Consider Claude Team plans
- **For automation**: Use Claude API with proper authentication

#### Step 2: Set Up Your Development Environment
```bash
# Ensure you have the required tools
python --version  # Should be 3.10-3.13
pip install fivetran-connector-sdk
```

#### Step 3: Prepare Your Project Context
- **Upload existing code**: Share your current connector implementation
- **Provide API documentation**: Include source system API docs
- **Define requirements**: Specify data needs and constraints
- **Share configuration**: Include sample configuration files

#### Step 4: Use Structured Prompts
Follow the prompt templates provided in the Claude AI Prompt Templates section below for optimal results.

### Best Practices for Claude AI Usage

#### **Effective Prompting**
- **Be specific**: Include exact API endpoints, data types, and requirements
- **Provide context**: Share relevant documentation and examples
- **Iterate gradually**: Start with basic functionality, then enhance
- **Validate output**: Always test generated code before production use

#### **Code Quality Assurance**
- **Review generated code**: Check for security, performance, and best practices
- **Test thoroughly**: Validate with both CLI and Python testing methods
- **Document changes**: Keep track of modifications and improvements
- **Version control**: Use Git for tracking code evolution

#### **Learning Resources**
- **Claude Documentation**: [help.anthropic.com](https://help.anthropic.com)
- **Fivetran SDK Examples**: [GitHub Repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples)
- **Community Support**: [Fivetran Community Forum](https://community.fivetran.com)

### Security and Privacy

#### **Data Protection**
- **Local processing**: Claude Desktop processes data locally when possible
- **Encrypted communication**: All API calls use HTTPS encryption
- **Data retention**: Review Claude's data retention policies
- **Sensitive information**: Never share production credentials in conversations

#### **Best Practices**
- **Use environment variables**: Keep credentials out of code
- **Review generated code**: Check for hardcoded secrets
- **Test in isolation**: Validate connectors in safe environments
- **Monitor usage**: Track API calls and resource consumption

## Prerequisites

### System Requirements
- **Python**: 3.10-3.13 (as specified in [Fivetran SDK Requirements](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements))
- **Operating System**: 
  - Windows 10 or later
  - macOS 13 (Ventura) or later
- **Fivetran Connector SDK**: Latest version
- **Claude AI Access**: For code generation and assistance

### Required Knowledge
- Python programming fundamentals
- REST API integration concepts
- JSON data handling
- Basic understanding of data pipelines

## Architecture Overview

### Core Components
```python
# Standard connector structure
from fivetran_connector_sdk import Connector, Logging as log, Operations as op
import json

# Required functions
def schema(configuration: dict):
    """Define table schemas - only table names and primary keys"""
    return [
        {"table": "table_name", "primary_key": ["key"]}
    ]

def update(configuration: dict, state: dict):
    """Main data processing logic with proper operations"""
    # Data fetching and processing
    yield op.upsert("table_name", processed_data)
    yield op.checkpoint(state=new_state)

# Connector initialization
connector = Connector(update=update, schema=schema)
```

## Development Workflow

### 1. Planning Phase
- **API Analysis**: Review source system documentation
- **Schema Design**: Map API responses to Fivetran tables
- **Authentication**: Determine required credentials
- **Data Volume**: Assess sync frequency and data size

### 2. Implementation Phase
- **Code Generation**: Use Claude AI with structured prompts
- **Testing**: Validate with both CLI and Python methods
- **Iteration**: Refine based on testing results

### 3. Quality Assurance
- **Error Handling**: Test various failure scenarios
- **Performance**: Optimize for data volume and rate limits
- **Documentation**: Complete setup and troubleshooting guides

## Project Structure

```
connector-project/
├── connector.py          # Main connector implementation
├── requirements.txt      # Python dependencies
├── configuration.json    # Connector configuration
├── README.md            # Project documentation
└── tests/               # Test files (optional)
    └── test_connector.py
```

## Implementation Guidelines

### Schema Definition
```python
def schema(configuration: dict):
    """
    Define table schemas - ONLY table names and primary keys
    Fivetran automatically infers column types from data
    """
    return [
        {"table": "users", "primary_key": ["id"]},
        {"table": "orders", "primary_key": ["order_id"]},
        {"table": "products", "primary_key": ["product_id"]}
    ]
```

### Data Operations
```python
# Upsert - Creates or updates records
yield op.upsert("table_name", processed_data)

# Update - Updates existing records only
yield op.update("table_name", modified_data)

# Delete - Marks records as deleted
yield op.delete("table_name", keys_to_delete)

# Checkpoint - Saves sync state for incremental syncs
yield op.checkpoint(state=new_state)
```

### State Management
```python
# Example state structure for incremental syncs
state = {
    "cursor": "2024-03-20T10:00:00Z",
    "offset": 100,
    "table_cursors": {
        "users": "2024-03-20T10:00:00Z",
        "orders": "2024-03-20T09:00:00Z"
    }
}
```

### Logging Standards
```python
# INFO - Status updates, cursors, progress
log.info(f'Processing batch {batch_number}, cursor: {current_cursor}')

# WARNING - Potential issues, rate limits
log.warning(f'Rate limit approaching: {remaining_calls} calls left')

# ERROR - Errors, failures, critical issues
log.error(f"API request failed: {error_details}")
```

## Configuration Management

### Configuration.json Template
```json
{
    "api_key": "your_api_key_here",
    "base_url": "https://api.example.com",
    "rate_limit": "1000",
    "start_date": "2023-01-01"
}
```

### Configuration Rules
- **All values must be strings** (Fivetran requirement)
- **Never commit sensitive data** to version control
- **Use environment variables** for production deployments
- **Document validation rules** for each parameter

## Testing and Validation

### Testing Methods
```bash
# CLI Testing
fivetran debug --configuration config.json

# Python Testing
python connector.py
```

### Validation Checklist
- [ ] **DuckDB Output**: Verify `warehouse.db` contains expected data
- [ ] **Operation Counts**: Check operation summary in logs
- [ ] **Data Completeness**: Validate all expected records are present
- [ ] **Error Handling**: Test various failure scenarios
- [ ] **Performance**: Monitor sync duration and resource usage

### Expected Log Output
```
Operation     | Calls
------------- + ------------
Upserts       | 44
Updates       | 0
Deletes       | 0
Truncates     | 0
SchemaChanges | 1
Checkpoints   | 1
```

## Security Best Practices

### Authentication
- **Secure Storage**: Never hardcode credentials
- **Token Management**: Implement proper token refresh logic
- **Access Control**: Use least-privilege API access
- **Environment Variables**: Use for production deployments

### Data Protection
- **PII Handling**: Follow data privacy regulations
- **Encryption**: Use HTTPS for all API communications
- **Audit Logging**: Track access and modifications

## ⚡ Performance Optimization

### Rate Limiting
```python
# Example rate limit handling
import time

def handle_rate_limit(response):
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 60))
        log.warning(f"Rate limited, waiting {retry_after} seconds")
        time.sleep(retry_after)
        return True
    return False
```

### Batch Processing
- **Optimal Batch Sizes**: Balance memory usage and API efficiency
- **Parallel Processing**: Use threading for independent API calls
- **Caching**: Cache frequently accessed data when appropriate

### Memory Management
- **Streaming**: Process data in chunks for large datasets
- **Cleanup**: Properly close connections and release resources
- **Monitoring**: Track memory usage during syncs

## Error Handling

### Common Error Scenarios
```python
# API Errors
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    log.error(f"API request failed: {e}")
    raise

# Data Validation
def validate_record(record):
    required_fields = ['id', 'name', 'created_at']
    missing_fields = [field for field in required_fields if field not in record]
    if missing_fields:
        log.warning(f"Record missing required fields: {missing_fields}")
        return False
    return True
```

### Retry Logic
```python
import time
from functools import wraps

def retry_on_failure(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    log.warning(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay * (2 ** attempt))  # Exponential backoff
            return None
        return wrapper
    return decorator
```

## Claude AI Prompt Templates

### Basic Connector Generation
```markdown
Task: Create a Fivetran connector for [API_NAME] that fetches [DATA_TYPE]

Technical Details:
- Language: Python 3.10+
- Framework: Fivetran Connector SDK
- API: [API_ENDPOINT]
- Data Target: [TABLE_NAME] table

Requirements:
1. Core Functionality:
   - Fetch data from [API_ENDPOINT]
   - Transform response into tabular format
   - Store in '[TABLE_NAME]' table
   - Support incremental updates

2. Technical Requirements:
   - Handle HTTP errors gracefully
   - Log sync progress
   - Define schema with proper types
   - Validate response data

3. Implementation Details:
   Required Functions:
   - schema(): Define table structure with primary keys only
   - update(): Fetch and process data with proper operations
   - Connector initialization with debug support

4. Expected Output:
   - connector.py with complete implementation
   - requirements.txt with necessary dependencies
   - configuration.json template
   - Error handling and logging

Additional Context:
- Authentication: [AUTH_TYPE]
- Rate limiting: [RATE_LIMIT_INFO]
- Data structure: [DATA_STRUCTURE_DETAILS]
```

### Advanced Connector Enhancement
```markdown
Task: Enhance existing Fivetran connector with [FEATURE]

Current Implementation:
- [DESCRIBE_CURRENT_FEATURES]

Enhancement Requirements:
1. New Features:
   - [FEATURE_1]
   - [FEATURE_2]

2. Technical Improvements:
   - [IMPROVEMENT_1]
   - [IMPROVEMENT_2]

3. Quality Assurance:
   - [TESTING_REQUIREMENTS]
   - [PERFORMANCE_GOALS]

Expected Output:
- Updated connector.py with new functionality
- Modified configuration.json if needed
- Updated documentation
- Test cases for new features
```

## Troubleshooting Guide

### Common Issues

#### 1. Authentication Failures
```python
# Debug authentication
log.info(f"Attempting authentication with client_id: {configuration.get('client_id')}")
# Check token response
log.info(f"Token response status: {response.status_code}")
```

#### 2. Data Type Mismatches
```python
# Validate data types before upsert
def sanitize_data(record):
    for key, value in record.items():
        if isinstance(value, (list, dict)):
            record[key] = json.dumps(value)
    return record
```

#### 3. Rate Limit Issues
```python
# Monitor rate limits
remaining_calls = int(response.headers.get('X-RateLimit-Remaining', 0))
if remaining_calls < 10:
    log.warning(f"Rate limit approaching: {remaining_calls} calls left")
```

### Debug Steps
1. **Check Configuration**: Verify all required fields are present
2. **Test API Access**: Validate credentials and permissions
3. **Review Logs**: Look for error messages and warnings
4. **Validate Data**: Check API response format and content
5. **Monitor Resources**: Ensure sufficient memory and network capacity

## Additional Resources

### Official Documentation
- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [SDK Examples Repository](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)

### Community Resources
- [GitHub Issues](https://github.com/fivetran/fivetran_connector_sdk/issues)

## Important Notes

### Limitations
- **API Constraints**: Respect source system rate limits and quotas
- **Data Volume**: Consider memory usage for large datasets
- **Network Dependencies**: Handle connectivity issues gracefully
- **Version Compatibility**: Ensure SDK version compatibility

### Best Practices Summary
- **Always use yield** for operations (upsert, update, delete, checkpoint)
- **Implement proper state management** for incremental syncs
- **Log comprehensively** for debugging and monitoring
- **Handle errors gracefully** with appropriate retry logic
- **Test thoroughly** before production deployment
- **Document everything** for maintainability

---

**Disclaimer**: This guide is intended to help you effectively use Fivetran's Connector SDK with Claude AI assistance. While we've tested the patterns and examples, Fivetran cannot be held responsible for any unexpected consequences that may arise from using these examples. For technical support, please reach out to our Support team.

**Last Updated**: June 2025
**SDK Version**: Latest
**Python Compatibility**: 3.10-3.13 
