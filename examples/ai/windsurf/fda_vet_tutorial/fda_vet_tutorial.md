# FDA Veterinary API Connector Tutorial

## What This Tutorial Does

This tutorial walks you through building a **Fivetran Connector** that automatically syncs data from the FDA Veterinary API using **Windsurf IDE**. You'll learn how to:

- Connect to FDA's public veterinary adverse events database (no API key required to start)
- Automatically sync veterinary adverse event reports with proper data flattening
- Implement incremental syncing to only fetch new/updated data
- Handle rate limiting and API quotas gracefully
- Structure data for analytics with flattened tables
- Leverage Windsurf IDE's advanced AI capabilities for connector development

**Perfect for**: Data engineers, analysts, and developers who want to build reliable data pipelines for veterinary pharmaceutical data using modern AI-powered development tools.

## Prerequisites

### Technical Requirements
- **Python 3.10 - 3.13+** installed on your machine
- **Basic Python knowledge** (functions, dictionaries, loops)
- **Fivetran Connector SDK** (we'll install this)
- **Git** (optional, for version control)

### Development Environment
- **Windsurf IDE** installed and configured
  - Download from: https://windsurf.ai
  - Sign in with GitHub/Google account
  - Install Python extension (built-in)
- **Terminal/Command line** access within Windsurf
- **Internet connection** for API calls

### API Access
- **FDA API Key** (optional but recommended)
  - Free registration at: https://open.fda.gov/apis/authentication/
  - Without key: 1,000 requests/day limit
  - With key: 120,000 requests/day limit

## Required Files

You'll need these 4 core files to get started:

### 1. `connector.py` - Main Connector Logic
```python
# This is your main connector file
# Contains all the FDA Veterinary API integration logic
# Handles data fetching, flattening, and processing
# Leverages Windsurf's AI for code generation and optimization
```

### 2. `utils.py` - Utility Functions
```python
# Contains the flatten_dict function for processing nested JSON
# Handles data transformation and validation
# Optimized for veterinary adverse event data structure
```

### 3. `configuration.json` - Settings
```json
{
  "api_key": "",
  "base_url": "https://api.fda.gov/animalandveterinary/event.json",
  "requests_per_checkpoint": "1",
  "rate_limit_delay": "0.5",
  "flatten_nested": "true",
  "limit_per_request": "10"
}
```

### 4. `requirements.txt` - Dependencies
```
fivetran-connector-sdk
requests
```

## The Prompt

Here's the original prompt that created this connector using Windsurf IDE:

> "Create a Fivetran Connector SDK solution for the FDA Veterinary API that includes:
> 
> - Veterinary adverse events endpoint integration
> - Incremental syncing using date fields and unique identifiers
> - Configurable data flattening for nested JSON structures
> - Rate limiting and quota management
> - Support for both authenticated and unauthenticated access
> - Robust state management for reliable incremental syncs
> - Proper upserts based on unique_aer_id_number as primary key
> - Follow the best practices outlined in Windsurf IDE development guide
> - Include utility functions for data transformation
> 
> The connector should work with the FDA Veterinary API endpoint for adverse events and handle the complex nested structure of veterinary adverse event reports."

## Quick Start with Windsurf IDE

1. **Open Windsurf IDE** and create a new workspace:
   ```bash
   # In Windsurf terminal
   mkdir fda-vet-connector
   cd fda-vet-connector
   ```

2. **Use Windsurf AI** to generate the connector:
   - Press `Cmd/Ctrl + K` to open AI chat
   - Copy the prompt above into the chat
   - Ask Windsurf to generate the complete connector implementation

3. **Review and customize** the generated code:
   - Windsurf AI will create all necessary files
   - Review the code structure and make any customizations
   - Use `Cmd/Ctrl + L` for inline code generation if needed

4. **Install dependencies**:
   ```bash
   # In Windsurf terminal
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install fivetran-connector-sdk
   pip install -r requirements.txt
   ```

5. **Test the connector**:
   ```bash
   # In Windsurf terminal
   fivetran debug --configuration configuration.json
   ```

6. **Check your data**:
   ```bash
   # In Windsurf terminal
   duckdb warehouse.db ".tables"
   duckdb warehouse.db "SELECT COUNT(*) FROM events;"
   ```

## Windsurf IDE Features for This Project

### 1. AI-Powered Development
- **Multi-file Context**: Windsurf AI understands your entire project structure
- **Intelligent Code Generation**: Generate boilerplate code with `Cmd/Ctrl + L`
- **Real-time Suggestions**: Get context-aware code completion
- **Error Prevention**: AI warns about potential issues before they occur

### 2. Enhanced Debugging
- **AI-powered Debugging**: Ask AI to help identify and fix bugs
- **Real-time Log Analysis**: Monitor logs directly in Windsurf terminal
- **Performance Insights**: Get suggestions for optimizing code performance
- **Security Review**: AI can identify potential security issues

### 3. Collaboration Features
- **Real-time Pair Programming**: Share your workspace with team members
- **Code Review**: Use AI-powered code review suggestions
- **Knowledge Sharing**: Create and share coding patterns with your team
- **Project Templates**: Save and reuse project configurations

## What You'll Learn

- **API Integration**: How to work with REST APIs in data connectors
- **Incremental Sync**: Building efficient data pipelines that only fetch new data
- **Rate Limiting**: Respecting API limits while maximizing throughput
- **Data Transformation**: Flattening complex JSON structures for analytics
- **Error Handling**: Building resilient connectors that handle API failures
- **State Management**: Tracking sync progress across multiple runs
- **Windsurf IDE Workflow**: Leveraging AI for faster, more efficient development

## Code Structure Explanation

### Main Connector Logic (`connector.py`)
```python
# Standard imports with Fivetran SDK
from fivetran_connector_sdk import Connector, Logging as log, Operations as op

# Schema definition with primary key
def schema(configuration: dict):
    return [
        {"table": "events", "primary_key": ["unique_aer_id_number"]}
    ]

# Main update function with proper operations
def update(configuration: dict, state: dict = None):
    # Fetch data from FDA Veterinary API
    # Process and flatten each event
    # Yield upsert operations
    # Checkpoint after each record
```

### Utility Functions (`utils.py`)
```python
# Data transformation utilities
def flatten_dict(nested_dict, parent_key='', sep='_'):
    # Recursively flatten nested JSON structures
    # Handle veterinary adverse event data complexity
    # Return flattened dictionary for database storage
```

## Advanced Windsurf Features

### 1. Multi-file Context Understanding
- **Project-wide Analysis**: Windsurf AI understands relationships between `connector.py` and `utils.py`
- **Cross-file Refactoring**: Make changes across multiple files simultaneously
- **Dependency Tracking**: AI tracks imports and dependencies automatically
- **Pattern Recognition**: AI learns from your coding patterns

### 2. Intelligent Code Completion
- **Context-aware Suggestions**: AI suggests code based on your project context
- **API Integration Help**: Get suggestions for FDA API integration patterns
- **Error Prevention**: AI warns about potential issues before they occur
- **Best Practice Suggestions**: Receive recommendations for code improvements

### 3. Real-time Collaboration
- **Pair Programming**: Share your workspace with team members for real-time collaboration
- **Code Review**: Use AI-powered code review suggestions
- **Knowledge Sharing**: Create and share coding patterns with your team
- **Project Templates**: Save and reuse project configurations

## Testing and Validation

### 1. Local Testing
```bash
# Test the connector locally
fivetran debug --configuration configuration.json

# Check the generated database
duckdb warehouse.db ".tables"
duckdb warehouse.db "SELECT * FROM events LIMIT 5;"
```

### 2. Data Validation
```bash
# Verify data structure
duckdb warehouse.db "DESCRIBE events;"

# Check for data quality
duckdb warehouse.db "SELECT COUNT(*) FROM events WHERE unique_aer_id_number IS NULL;"
```

### 3. Performance Testing
```bash
# Monitor sync performance
time fivetran debug --configuration configuration.json

# Check memory usage and optimize if needed
```

## Troubleshooting with Windsurf

### 1. AI Not Responding
- **Check Internet Connection**: Windsurf requires internet for AI features
- **Restart Windsurf**: Close and reopen the application
- **Clear Cache**: Clear AI cache in settings
- **Update Windsurf**: Ensure you're using the latest version

### 2. Code Generation Issues
- **Provide More Context**: Give AI more details about your requirements
- **Use Specific Prompts**: Be specific about what you want to generate
- **Iterate**: Ask AI to refine or modify generated code
- **Check Dependencies**: Ensure all required packages are installed

### 3. Performance Issues
- **Close Unused Tabs**: Reduce memory usage by closing unnecessary files
- **Disable Heavy Extensions**: Temporarily disable resource-intensive extensions
- **Check System Resources**: Ensure adequate RAM and CPU availability
- **Optimize Project Size**: Remove unnecessary files from your workspace

## Next Steps

Once you've got the basic connector working:

1. **Get an API key** for higher rate limits
2. **Customize the configuration** for your data needs
3. **Add more endpoints** by extending the connector
4. **Implement custom data transformations** for your specific use case
5. **Deploy to production** with proper monitoring and alerting
6. **Leverage Windsurf's collaboration features** for team development

## Best Practices for Windsurf Development

### 1. Project Organization
- **Logical File Structure**: Organize connector files logically
- **Version Control**: Use built-in Git integration for version management
- **Configuration Management**: Keep configuration files separate and secure
- **Documentation**: Maintain README files with setup instructions

### 2. AI-Assisted Development
- **Clear Prompts**: Provide specific, detailed prompts for better AI responses
- **Iterative Development**: Use AI to refine and improve code incrementally
- **Code Review**: Ask AI to review your code for best practices
- **Documentation**: Use AI to generate documentation and comments

### 3. Testing and Quality Assurance
- **Comprehensive Testing**: Test all error scenarios and edge cases
- **Performance Monitoring**: Monitor sync performance and resource usage
- **Error Handling**: Implement robust error handling and recovery
- **Logging**: Use appropriate log levels for debugging and monitoring

## Resources and References

### Official Documentation
- **FDA Veterinary API**: https://open.fda.gov/apis/animalandveterinary/
- **Fivetran SDK Docs**: https://fivetran.com/docs/connector-sdk
- **API Status**: https://open.fda.gov/apis/status/

### Windsurf Resources
- **Windsurf Documentation**: https://windsurf.ai/docs
- **Windsurf AI Features**: https://windsurf.ai/features
- **Windsurf Keyboard Shortcuts**: https://windsurf.ai/docs/keyboard-shortcuts
- **Windsurf Collaboration Guide**: https://windsurf.ai/docs/collaboration

### Development Tools
- **Python Documentation**: https://docs.python.org/3/
- **Requests Library**: https://requests.readthedocs.io/
- **JSON Schema Validation**: https://json-schema.org/

## Quick Reference Commands

```bash
# Set up new connector project in Windsurf
mkdir fda-vet-connector && cd fda-vet-connector
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install fivetran-connector-sdk
pip install -r requirements.txt

# Test connector
fivetran debug --configuration configuration.json

# Check data
duckdb warehouse.db ".tables"
duckdb warehouse.db "SELECT COUNT(*) FROM events;"

# Windsurf AI shortcuts
# Cmd/Ctrl + K: Open AI chat
# Cmd/Ctrl + L: Inline code generation
# Right-click: AI-powered refactoring
```

## Need Help?

- **FDA Veterinary API Docs**: https://open.fda.gov/apis/animalandveterinary/
- **Fivetran SDK Docs**: https://fivetran.com/docs/connector-sdk
- **Windsurf Support**: https://windsurf.ai/support
- **API Status**: https://open.fda.gov/apis/status/

Happy building with Windsurf IDE! 
