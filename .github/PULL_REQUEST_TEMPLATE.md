### Jira ticket
Closes `<ADD TICKET LINK HERE, EACH PR MUST BE LINKED TO A JIRA TICKET>`

### Description of Change
`<MENTION A SHORT DESCRIPTION OF YOUR CHANGES HERE>`

### Testing
`<MENTION ABOUT YOUR TESTING DETAILS HERE, ATTACH SCREENSHOTS IF NEEDED (WITHOUT PII)>`

### Checklist
Check the section below that matches this PR. Delete the section that doesn't apply.

**If this PR adds or changes an example connector (`examples/`):**
- [ ] Tested the connector with `fivetran debug` command.
- [ ] Added/Updated example-specific README.md file, see [the README template](https://github.com/fivetran/connector_sdk/tree/main/template_connector/README_template.md) for the required structure and guidelines.
- [ ] Ran `./.github/scripts/fix-python-formatting.sh` and resolved any flake8 issues.

**If this PR changes the `fivetran-connector-sdk` package itself (`src/`, `tests/`):**
- [ ] Ran `pytest` locally and all tests pass.
- [ ] Ran `./.github/scripts/fix-python-formatting.sh` and resolved any flake8 issues.
