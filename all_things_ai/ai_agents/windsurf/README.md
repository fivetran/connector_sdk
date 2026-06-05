# Windsurf Agent for Fivetran Connector SDK

This folder is designed to help you use Windsurf with the Fivetran Connector SDK to build custom connectors efficiently in a cloud-based collaborative environment.

## Getting started with Windsurf

1. Access Windsurf - Go to [windsurf.com](https://windsurf.com) and create an account.
2. Open this project in Windsurf - Import or clone this repository.
3. Use the AGENTS.md file - Copy its contents into Windsurf's AI assistant for specialized help.
4. Browse our examples - Check ../../../examples/ for connector patterns and implementations and ../../../connectors for connector examples.

## Folder structure

```
windsurf/
├── AGENTS.md          # AI instructions for Windsurf assistant
└── README.md          # This file - instructions for humans

# Examples are located at: ../../../examples/
```

## How to use with Windsurf

### 1. Cloud Setup
- Access Windsurf through your web browser
- No local installation required
- Built-in Python environment ready for development
- Integrated terminal for testing and debugging

### 2. Configure AI Assistant
- Copy the contents of `AGENTS.md` into Windsurf's AI chat
- This provides Windsurf with Fivetran SDK expertise
- Use the AI assistant for code generation and debugging
- Leverage collaborative AI features for team development

### 3. Development environment
- Built-in Editor: Full-featured code editor in the browser
- Terminal Access: Integrated terminal for testing connectors
- Git Integration: Built-in version control
- Live Sharing: Real-time collaboration with team members

### 4. Building your connector
Use Windsurf's features:
- AI Assistant: Get help with connector development
- Code Generation: Generate complete connector implementations
- Real-time Collaboration: Work with team members simultaneously
- Cloud Testing: Test connectors directly in the cloud environment

## Key features

- Cloud-Based Development: No local setup required
- Real-time Collaboration: Multiple developers can work simultaneously
- AI-Powered: Built-in AI assistance for code generation and debugging
- No Yield Required: Modern SDK patterns without yield statements
- Complete Solutions: Generate connector.py, requirements.txt, and configuration.json
- Enterprise Ready: Production-quality code generation

## Video tutorials

See our [Windsurf AI IDE video tutorial](https://fivetran.com/docs/connector-sdk/tutorials/windsurf-ai-video).

## Development workflow

### 1. Planning phase
- Use Windsurf's collaborative features to plan with team
- Review API documentation using built-in browser
- Design table structure and primary keys collaboratively
- Plan error handling strategy with team input

### 2. Implementation phase
- Use Windsurf AI to generate initial connector structure
- Follow Fivetran SDK patterns from ../../../examples/
- Collaborate in real-time with team members
- Test API integration using cloud-based tools

### 3. Testing phase
- Use integrated terminal for connector testing
- Run `fivetran debug --configuration config.json`
- Share testing results with team in real-time
- Debug collaboratively using shared environment

## Cloud development best practices

### 1. Collaboration
- Use clear commit messages for team transparency
- Structure code in modular functions for easy collaboration
- Add comprehensive comments for team understanding
- Use shared configuration for consistent development

### 2. Performance
- Minimize large file operations in cloud environment
- Use efficient data processing patterns
- Implement proper error handling for network issues
- Test with various network conditions

### 3. Security
- Never commit sensitive credentials
- Use environment variables for configuration
- Follow cloud security best practices
- Implement proper authentication handling

## Example prompts for Windsurf AI

Try these with Windsurf's AI assistant:
- "Create a connector for <API name> using Fivetran SDK patterns"
- "Help me implement pagination with error handling"
- "Generate a complete connector with proper logging"
- "Debug this API integration and fix network issues"
- "Add incremental sync capability to my connector"

## Testing your connector

```bash
# In Windsurf terminal
fivetran debug --configuration configuration.json

# Check output
ls -la warehouse.db

# View logs (appear in terminal during debug run)
```

## Collaborative features

### 1. Live editing
- Multiple team members can edit files simultaneously
- Real-time cursor tracking and change highlighting
- Integrated chat for immediate communication
- Shared terminal for collaborative testing

### 2. Version control
- Built-in Git integration
- Easy branching and merging
- Shared commit history
- Conflict resolution tools

### 3. Sharing and review
- Easy project sharing with team members
- Built-in code review features
- Commenting and suggestion system
- Live presentation mode for demonstrations

## Troubleshooting

### Common cloud issues
1. Network connectivity: Check internet connection.
2. Performance: Use efficient code patterns for cloud execution.
3. Collaboration conflicts: Use proper Git workflow.
4. Resource limits: Monitor cloud resource usage.

### Solutions
- Use Windsurf's built-in debugging tools
- Leverage AI assistant for error diagnosis
- Collaborate with team for complex issues
- Reference ../../../examples/ for proven connector patterns

## Resources

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [Connector SDK Repository](https://github.com/fivetran/connector_sdk)
- [Windsurf Documentation](https://docs.windsurf.com/)
- [Windsurf Getting Started](https://docs.windsurf.com/windsurf/getting-started)

## Support

If you encounter issues:
1. Check ../../../examples/ for similar connector patterns.
2. Use Windsurf's AI assistant with AGENTS.md context.
3. Collaborate with team members for help.
4. Refer to official Fivetran and Windsurf documentation.

## Advantages of Cloud Development

- No Setup Required: Start coding immediately
- Team Collaboration: Real-time collaborative development
- Cross-platform: Access from any device with a browser
- Integrated Testing: Cloud-based testing environment
- AI-Powered: Built-in AI assistance for development
- Version Control: Integrated Git workflow
- Scalability: Cloud resources scale with your needs