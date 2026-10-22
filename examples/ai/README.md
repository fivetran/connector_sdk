# Tutorials for Fivetran Connector SDK

This directory contains tutorials created by Fivetran to help you learn how to build custom connectors with Fivetran's Connector SDK.

## Disclaimer
The content and sample code in tutorials folder — including the README.md, connector.py, and requirements.txt files were generated as batched outputs from a single AI conversation. While a Fivetran employee has tested the functionality for demonstration purposes, the code has not been polished or reviewed for production use. It remains unedited AI output and should be treated as illustrative only.

## ChatGPT
ChatGPT can be effectively used to help you leverage our Connector SDK to build custom connectors. This was achieved by passing examples from this repository along with the full [technical reference](https://fivetran.com/docs/connector-sdk/technical-reference) documentation to ChatGPT. When tested, it does require some manual adjustments of the created code.


## IDE & AI Assistant Support

Learn about using various IDEs and AI assistants with the Fivetran Connector SDK. Each section includes a summary and a list of relevant example connectors, system instruction files, and resources. For general guidance on using AI tools to build connectors, see [Building Connectors with AI Tools](https://fivetran.com/docs/connector-sdk/building-connectors/ai-tools).

> You can simplify AI coding agent setup with our [Connector SDK AI plugins](https://github.com/fivetran/connector_sdk_tools). They integrate with Claude Code, Codex CLI, GitHub Copilot CLI, and Gemini CLI, and provide skills for building, testing, deploying, and evaluating connectors.

---

## Cursor

Summary:  
Cursor is an AI-powered code editor designed for productivity, smart completion, and real-time collaboration, with robust Python support.

Contents:
- [AGENTS.md for Cursor](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/cursor/fda_food_tutorial/AGENTS.md)
- [Example: FDA Food connector with Cursor](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/cursor/fda_food_tutorial)
- [Tutorial: Build a connector with Cursor AI](https://fivetran.com/docs/connector-sdk/tutorials/cursor-ai-video)
- [Installation Guide](https://www.cursor.com/)

---

## Windsurf

Summary:  
Windsurf is a lightweight, cloud-based IDE for rapid prototyping and collaboration, supporting live sharing and direct browser development.

Contents:
- [AGENTS.md for Windsurf](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/windsurf/fda_vet_tutorial/AGENTS.md)
- [Example: FDA Vet connector with Windsurf](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/windsurf/fda_vet_tutorial)
- [Getting Started](https://docs.windsurf.com/windsurf/getting-started)
- [Context Awareness](https://docs.windsurf.com/context-awareness/windsurf-overview)

---

## Visual Studio Code

Summary:  
Visual Studio Code (VS Code) is a widely-used, open-source code editor with Python support, advanced debugging, and a rich extension library.

Contents:
- [AGENTS.md for VS Code with GitHub Copilot](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/vscode/fda_tobacco_tutorial/AGENTS.md)
- [Example: FDA Tobacco connector with VS Code](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/vscode/fda_tobacco_tutorial)
- [Tutorial: Build a connector with GitHub Copilot](https://fivetran.com/docs/connector-sdk/tutorials/github-copilot)
- [Getting Started](https://code.visualstudio.com/docs/getstarted/getting-started)
- [Copilot in VS Code](https://code.visualstudio.com/docs/copilot/getting-started)

---

## Claude

Summary:  
Claude is an AI assistant by Anthropic, capable of generating and editing Python code for Fivetran connectors. Claude can automate and accelerate connector development and has been used to generate connectors with multi-table schemas.

## Claude Code

We have [published a blog post](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai) about our experiences and included the code as Claude generated it in the folder tutorials/claude/pokeapi_tutorial with the output of our exploration with Claude. The [warehouse.db](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/claude/pokeapi_tutorial/pokeapi_connector/files/warehouse.db) and [state.json](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/claude/pokeapi_tutorial/pokeapi_connector/files/state.json) files are included here so you can easily review the output of the first sync. Note that these files are not required for Connector SDK - they are only temporary files created during testing.

Contents:
- [Example: PokeAPI connector with Claude](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/claude/pokeapi_tutorial)
- [Example: FDA Drug connector with Claude](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/claude/fda_drug_tutorial)
- [Claude Code instructions and agents](https://github.com/fivetran/connector_sdk/tree/main/examples/ai/claude)
- [Getting Started with Claude](https://docs.anthropic.com/en/docs/get-started)
- [Blog Post: Building a Fivetran Connector in 1 Hour with Claude AI](https://www.fivetran.com/blog/building-a-fivetran-connector-in-1-hour-with-anthropics-claude-ai)
  
---
