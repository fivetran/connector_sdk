#!/usr/bin/env python3
"""
SDK Marketplace: AI-powered configuration form generator.

Reads a connector.py file and uses Claude to auto-generate a configuration_form.json
with rich field metadata — labels, descriptions, types, required flags, and placeholders.

Usage:
    python tools/generate_form.py --connector-dir connectors/neo4j
    python tools/generate_form.py --connector-dir connectors/neo4j --dry-run

Requirements:
    pip install anthropic
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic

SYSTEM_PROMPT = """You are an expert at analyzing Fivetran Connector SDK connectors written in Python.
Your job is to generate a configuration_form.json file that describes the setup form a customer
would see in the Fivetran UI when configuring this connector.

The form definition must be valid JSON matching this schema:
{
  "connector_name": "Human-readable connector name",
  "description": "One or two sentences describing what data this connector syncs and why customers use it",
  "category": "One of: Database, API, Analytics, CRM, Marketing, Finance, Learning & Development, DevOps, Other",
  "tags": ["lowercase-tag1", "lowercase-tag2"],
  "fields": [
    {
      "name": "config_key_name",          // must match the key used in configuration.get()
      "label": "Human-readable Label",
      "description": "What this field is and where to find it",
      "type": "text|password|dropdown|toggle",
      "required": true|false,
      "placeholder": "example value or format hint",  // optional
      "options": ["opt1", "opt2"]                     // only for dropdown type
    }
  ]
}

Rules:
- "type" must be "password" for any field that looks like a secret, token, key, or credential
- "type" must be "dropdown" when there are a fixed set of valid values
- "type" must be "toggle" for boolean on/off settings
- "type" must be "text" for everything else
- Set "required": true for fields that appear in validate_configuration() or that the connector will fail without
- Write "description" from the customer's perspective — where do they find this value?
- "placeholder" should be a realistic example of the expected format, not the field name
- Do not include fields for internal state or computed values
- Output ONLY valid JSON, no markdown fences, no explanation"""

USER_PROMPT_TEMPLATE = """Analyze this Fivetran Connector SDK connector and generate configuration_form.json.

connector.py:
{connector_code}

configuration.json (current placeholder values):
{configuration_json}

Generate the configuration_form.json now."""


def load_connector_files(connector_dir: Path) -> tuple[str, str]:
    connector_py = connector_dir / "connector.py"
    configuration_json = connector_dir / "configuration.json"

    if not connector_py.exists():
        print(f"Error: connector.py not found in {connector_dir}", file=sys.stderr)
        sys.exit(1)

    connector_code = connector_py.read_text()
    config_json = configuration_json.read_text() if configuration_json.exists() else "{}"
    return connector_code, config_json


def generate_form(connector_dir: Path, dry_run: bool = False) -> dict:
    connector_code, config_json = load_connector_files(connector_dir)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Analyzing {connector_dir}/connector.py with Claude...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    connector_code=connector_code,
                    configuration_json=config_json,
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown fences if the model included them despite instructions
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    form_definition = json.loads(raw)

    output_path = connector_dir / "configuration_form.json"

    if dry_run:
        print("\nDry run — generated form (not saved):")
        print(json.dumps(form_definition, indent=2))
    else:
        output_path.write_text(json.dumps(form_definition, indent=2) + "\n")
        print(f"Saved: {output_path}")
        _print_summary(form_definition)

    return form_definition


def _print_summary(form: dict) -> None:
    print(f"\nConnector: {form.get('connector_name', 'Unknown')}")
    print(f"Category:  {form.get('category', 'Unknown')}")
    fields = form.get("fields", [])
    print(f"Fields:    {len(fields)}")
    for f in fields:
        required_marker = "*" if f.get("required") else " "
        print(f"  {required_marker} {f['name']} ({f['type']}) — {f['label']}")
    print("\nDone. Deploy with: fivetran deploy --connector-dir <dir>")


def main():
    parser = argparse.ArgumentParser(
        description="Generate configuration_form.json for a Fivetran SDK connector using AI"
    )
    parser.add_argument(
        "--connector-dir",
        required=True,
        help="Path to connector directory containing connector.py",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated form without saving it",
    )
    args = parser.parse_args()

    connector_dir = Path(args.connector_dir)
    if not connector_dir.is_dir():
        print(f"Error: {connector_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    generate_form(connector_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
