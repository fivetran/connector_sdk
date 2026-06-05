# Claude Code Agent for Fivetran Connector SDK

This folder is designed to help you use Claude Code with the Fivetran Connector SDK to build custom connectors efficiently.

## Getting started with Claude Code

1. Start Claude Code in this folder - This ensures Claude picks up the `CLAUDE.md` instructions automatically.
2. Browse connector examples - Check ../../../examples/ for connector patterns and implementation and ../../../connectors/ for connector examples
3. Utilize specialized agents - The `.claude/agents` folder contains Connector SDK specific sub-agents.

## Folder structure

```
claude_code/
├── CLAUDE.md          # AI instructions for Claude Code
├── README.md          # This file - instructions for humans
└── .claude/
    └── agents/        # Specialized Claude Code sub-agents

# Examples are located at: ../../../examples/
```

## How to use

### 1. Initialize Claude Code
Start Claude Code in this folder:
```bash
cd all_things_ai/ai_agents/claude_code
claude-code
```

### 2. Build your first connector
Claude Code will automatically use the `CLAUDE.md` instructions to help you:
- Generate complete connector code
- Follow Fivetran best practices
- Handle authentication and data operations
- Implement proper error handling and logging

### 3. Example commands
Try these commands with Claude Code:
- "Create a connector for <API name>"
- "Help me build a connector that fetches data from [source]"
- "Debug my existing connector"
- "Add incremental sync to my connector"

## Key features

- No Yield Required: Modern SDK patterns without yield statements
- Complete Solutions: Get connector.py, requirements.txt, and configuration.json
- Best Practices: Automatic implementation of Fivetran coding standards
- AI/ML Focus: Optimized for AI and ML data ingestion patterns
- Enterprise Ready: Production-quality code generation

## Video tutorials

See our [Claude Code video tutorial](https://fivetran.com/docs/connector-sdk/tutorials/claude-ai-terminal-video).

## Specialized sub-agents

The `.claude/agents` folder contains specialized agents for:
- ft-csdk-test: Testing and validation
- ft-csdk-fix: Debugging and error resolution
- ft-csdk-revise: Code review and improvements
- ft-csdk-ask: Q&A about Connector SDK

These agents are automatically orchestrated by Claude Code when needed.

## Documentation

- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Best Practices Guide](https://fivetran.com/docs/connector-sdk/best-practices)
- [Connector SDK Repository](https://github.com/fivetran/connector_sdk)

## Support

If you encounter issues:
1. Browse ../../../examples/ for similar connector patterns.
2. Ask Claude Code for help with debugging.
3. Refer to the official Fivetran documentation.