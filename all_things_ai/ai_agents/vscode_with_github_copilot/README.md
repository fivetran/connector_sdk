# VS Code with GitHub Copilot Agent for Fivetran Connector SDK

This folder is designed to help you use Visual Studio Code with AI assistants like GitHub Copilot to build custom connectors with the Fivetran Connector SDK.

## Getting started with VS Code

1. Install VS Code - Download from [code.visualstudio.com](https://code.visualstudio.com/).
2. Install Required Extensions - See recommended extensions below.
3. Open this folder in VS Code - This gives you access to examples and instructions.
4. Configure AI assistant - Use AGENTS.md content with your preferred AI assistant.
5. Start building - Use ../../../examples/ as reference for connector patterns.

## Folder structure

```
vscode_with_github_copilot/
├── AGENTS.md          # AI instructions for assistants
└── README.md          # This file - instructions for humans

# Examples are located at: ../../../examples/
```

## Recommended extensions

### Essential extensions
- Python (Microsoft) - Core Python support
- GitHub Copilot - AI-powered code completion
- GitLens - Enhanced Git capabilities
- Error Lens - Inline error highlighting

### Optional but helpful
- Python Docstring Generator - Automatic docstring generation
- Pylint - Python linting
- Black Formatter - Python code formatting
- Thunder Client - API testing within VS Code

## Setup instructions

### 1. Install extensions
```bash
# Install VS Code extensions via command line
code --install-extension ms-python.python
code --install-extension GitHub.copilot
code --install-extension eamodio.gitlens
code --install-extension usernamehw.errorlens
```

### 2. Configure Python environment
```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Fivetran SDK
pip install fivetran_connector_sdk
```

### 3. Configure debugging
Create `.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Debug Connector",
            "type": "python",
            "request": "launch",
            "program": "connector.py",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}"
        }
    ]
}
```

## How to use

### 1. AI assistant configuration
- Copy contents of `AGENTS.md` into your preferred AI assistant (ChatGPT, Claude, etc.)
- This provides specialized knowledge about Fivetran SDK patterns
- Use this context for all connector development questions

### 2. Development with Copilot
- Copilot Chat: Use `Ctrl+Shift+I` to open chat interface
- Inline Suggestions: Copilot automatically suggests code as you type
- Code Generation: Use descriptive comments to guide code generation
- Debugging: Ask Copilot to explain errors and suggest fixes

### 3. Building your connector
1. Start with Examples: Browse ../../../examples/ for connector patterns.
2. Use AI Assistance: Get help with complex API integrations.
3. Test Frequently: Use integrated terminal for testing.

### 4. Example workflow
```python
# Start with this comment to get Copilot suggestions
# Create a connector for <API name> that fetches [data type]

# Copilot will suggest imports
from fivetran_connector_sdk import Connector, Logging as log, Operations as op
import json

# Continue with descriptive comments for better suggestions
# Define schema function with primary key for [table_name]
def schema(configuration: dict):
    # Copilot will suggest the schema structure
    return [
        {"table": "your_table", "primary_key": ["id"]}
    ]
```

## Key features

- No Yield Required: Modern SDK patterns without yield statements
- Copilot Integration: AI-powered code completion and suggestions
- Complete Solutions: Generate connector.py, requirements.txt, and configuration.json
- Best Practices: Automatic implementation of Fivetran coding standards
- Debugging Support: Built-in debugging and testing capabilities

## Video Tutorials

See our [VS Code with GitHub Copilot video tutorial](https://fivetran.com/docs/connector-sdk/tutorials/github-copilot-video).

## Development best practices

### 1. Code organization
- Keep connector files organized in project folders
- Use clear, descriptive function and variable names
- Add comprehensive docstrings for better Copilot suggestions
- Follow PEP 8 style guidelines

### 2. AI assistant usage
- Use the AGENTS.md context for specialized SDK knowledge
- Ask specific questions about Fivetran patterns
- Request code reviews and improvements
- Get help with error handling and edge cases

### 3. Testing strategy
- Use VS Code's integrated terminal for testing
- Set up debugging configurations for troubleshooting
- Test with various API scenarios and edge cases
- Validate logs and data output

## Common VS Code shortcuts

- `Ctrl+Shift+P` - Command Palette
- `Ctrl+Shift+I` - Copilot Chat
- `F5` - Start Debugging
- `Ctrl+` ` - Toggle Terminal
- `Ctrl+Shift+E` - Explorer
- `Ctrl+Shift+G` - Source Control

## Testing your connector

```bash
# In VS Code terminal
fivetran debug --configuration configuration.json

# Check output
ls -la warehouse.db

# View logs (appear in terminal during debug run)
```

## Troubleshooting

### Common issues
1. Python not found: Ensure Python extension is installed and interpreter is selected.
2. Import errors: Check virtual environment is activated.
3. Copilot not working: Verify Copilot subscription and authentication.
4. Debugging issues: Check launch.json configuration.

### Solutions
- Use `Ctrl+Shift+P` → "Python: Select Interpreter" to choose correct Python
- Restart VS Code if extensions aren't working properly
- Check terminal output for detailed error messages
- Use Copilot Chat to debug specific error messages

## Resources

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [Connector SDK Repository](https://github.com/fivetran/connector_sdk)
- [VS Code Python Documentation](https://code.visualstudio.com/docs/python/python-tutorial)
- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)

## Support

If you encounter issues:
1. Check ../../examples/ for similar connector patterns.
2. Use AI assistant with AGENTS.md context for help.
3. Refer to official Fivetran and VS Code documentation.
4. Use Copilot Chat for debugging assistance.