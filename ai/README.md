# Tutorials for Fivetran Connector SDK

This directory contains tutorials created by Fivetran to help you learn how to build custom connectors with Fivetran's Connector SDK.

## Disclaimer
The content and sample code in tutorials folder — including the README.md, connector.py, and requirements.txt files were generated as batched outputs from a single AI conversation. While a Fivetran employee has tested the functionality for demonstration purposes, the code has not been polished or reviewed for production use. It remains unedited AI output and should be treated as illustrative only.

## ChatGPT
ChatGPT can be effectively used to help you leverage our Connector SDK to build custom connectors. This was achieved by passing examples from this repository along with the full [technical reference](https://fivetran.com/docs/connector-sdk/technical-reference) documentation to ChatGPT. When tested, it does require some manual adjustments of the created code.


## IDE & AI Assistant Support

Learn about using various IDEs and AI assistants with the Fivetran Connector SDK. Each section includes a summary and links to relevant sub-guides, sample content, and a short video.

- [Cursor](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/cursor)
- [Windsurf](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/windsurf)
- [Visual Studio Code](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/vscode_with_github_copilot)
- [Claude](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/claude_code)

---

## Cursor

Summary:  
Cursor is an AI-powered code editor designed for productivity, smart completion, and real-time collaboration, with robust Python support.

Contents:
- [Fivetran Connector SDK AI System Instructions {Notepad}](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/AGENTS.md)
- [Installation Guide](https://www.cursor.com/)
- [Using Cursor with Fivetran Connector SDK](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/cursor/README.md)

---

## Windsurf

Summary:  
Windsurf is a lightweight, cloud-based IDE for rapid prototyping and collaboration, supporting live sharing and direct browser development.

Contents:
- [Fivetran Connector SDK AI System Instructions](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/AGENTS.md)
- [Getting Started](https://docs.windsurf.com/windsurf/getting-started)
- [Context Awareness](https://docs.windsurf.com/context-awareness/windsurf-overview)

---

## Visual Studio Code

Summary:  
Visual Studio Code (VS Code) is a widely-used, open-source code editor with Python support, advanced debugging, and a rich extension library.

Contents:
- [Fivetran Connector SDK AI System Instructions](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/AGENTS.md)
- [Getting Started](https://code.visualstudio.com/docs/getstarted/getting-started)
- [Copilot in VS Code](https://code.visualstudio.com/docs/copilot/getting-started)

---

## Claude

Summary:  
Claude is an AI assistant by Anthropic, capable of generating and editing Python code for Fivetran connectors. Claude can automate and accelerate connector development and has been used to generate connectors with multi-table schemas.

## Claude Code
Claude Code has proved to be capable of successfully generating a connector capable of populating a multi-table schema during its initial run. The [CLAUDE.md File](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/claude_code/CLAUDE.md) in this folder contains instructions for Claude to be able to successfully build and debug connectors using Fivetran's Connector SDK. Start Claude Code in this folder so that it can pick up the CLAUDE.md content when generating responses. You can swap in the contents from agents.md into CLAUDE.md to see how the model behaves with different contexts, iterate and improve as you develop solutions!

We also have [published a blog post](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai) about our experiences and included the code as Claude generated it in the folder tutorials/claude/pokeapi_tutorial with the output of our exploration with Claude. The [warehouse.db](https://github.com/fivetran/connector_sdk/tree/main/ai/claude/pokeapi_tutorial/pokeapi_connector/files/warehouse.db) and [state.json](https://github.com/fivetran/connector_sdk/tree/main/ai/claude/pokeapi_tutorial/pokeapi_connector/files/state.json) files are included here so you can easily review the output of the first sync. Note that these files are not required for Connector SDK - they are only temporary files created during testing.

## Claude Code subagents
We created Connector SDK specific Claude Code agents that can help you build connectors. These agents are orchestrated by Claude Code when it identifies a task that is better accomplished using them.

To start using these agents, you will need to make sure your Claude Code is up-to-date. Subagents became available in late July with version 1.0.62. Please start Claude Code in the all_things_ai/ai_agents/claude_code folder so that Claude Code can automatically detect them and start using them.

You can verify that Claude Code is able to find them by calling `/agents` from within Claude Code and checking that the agents are listed.

Contents:
- [Fivetran Connector SDK AI System Instructions](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/AGENTS.md)
- [CLAUDE.md File](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/ai_agents/claude_code/CLAUDE.md)
- [Getting Started with Claude](https://docs.anthropic.com/en/docs/get-started)
- [Blog Post: Building a Fivetran Connector in 1 Hour with Claude AI](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai)
  
---
