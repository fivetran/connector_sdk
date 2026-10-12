# Composite Action: Deploy a Connector SDK Connector

This is a generic composite action for deploying any Connector SDK connector
to Fivetran. It does not know any connector's specific field names. You supply
`configuration_json` through your own caller workflow, or omit it if you do
not want to push configuration on this run.

Reference it from your repository's workflow as:

```yaml
- uses: fivetran/connector_sdk/examples/workflows/github/action@main
  with:
    connector_dir: path/to/your/connector
    fivetran_api_key: ${{ secrets.FIVETRAN_API_KEY }}
    # ...see Inputs below
```

> **Important:** Pin `@main` to a specific tag or commit SHA once one exists,
> the same way you would for any other third-party action. Using `@main` means
> your workflow picks up any changes to this action automatically, which may
> break your deployment unexpectedly. See
> [`../deploy-single-connector.yml`](../deploy-single-connector.yml) for a
> full example.

## What it does

| Scenario | Behavior |
|---|---|
| `configuration_json` is set | Pushes it to Fivetran, creating the connection if it does not exist or overwriting the stored configuration if it does. The presence of `configuration_json` is the only signal this action uses to decide whether to push configuration. |
| `configuration_json` is not set, connection exists | Runs a code-only deploy. |
| `configuration_json` is not set, connection does not exist | Code-only deploy fails. The action retries once with a placeholder configuration file. The placeholder path is set by `empty_config_path`, which defaults to `configuration.example.json`. The action creates the connection in a paused state with its setup form ready for someone to fill in real values in the Fivetran dashboard. |
| Placeholder setup tests fail | Prints a warning. Does not fail the job. A real failure still fails the job. |
| `activate_on_create` is `"true"`, connection was just created with real configuration (status `created`) | Makes a follow-up API call to unpause the connection. One-time effect only. Has no effect on redeploys of an existing connection (status `updated`). |
| `activate_on_create` is `"true"`, connection was created with placeholder configuration (status `created_needs_setup`) | The action always leaves it paused, since it has no real credentials yet. |

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `connector_dir` | yes | | Path to the connector project directory. Must contain `connector.py`. |
| `destination` | no | `""` | Fivetran destination name. Auto-selected if you have exactly one destination. |
| `connection_name` | no | `""` | Name of the Fivetran connection. Derived from `connector_dir`'s folder name if left empty. |
| `configuration_json` | no | `""` | Full `configuration.json` content as a string, only if you want to push configuration on this run. **Sensitive.** See [Security](#security). |
| `empty_config_path` | no | `"configuration.example.json"` | Path to the placeholder configuration file, relative to `connector_dir`, used for a first deploy without real configuration. |
| `python_version` | no | `""` | Optional `--python-version` override for the Fivetran runtime. |
| `fivetran_sdk_version` | no | `""` | Pins `fivetran-connector-sdk` to a specific version (for example, `"2.11.0"`). Left unpinned if empty. Always applies for `requirements.txt`-only connectors. For `pyproject.toml` connectors, this is only used as a fallback when `uv sync` did not already provide a `fivetran` CLI. A connector that pins its own version through `uv.lock` keeps that pin. |
| `activate_on_create` | no | `"false"` | Set to `"true"` to unpause the connection immediately after this run creates it with real configuration. One-time effect only. Ignored on redeploys and on placeholder-configuration creations. See [Security](#security) for details on the API call this makes. |
| `fivetran_api_key` | yes | | Your Fivetran API key. For example: `${{ secrets.FIVETRAN_API_KEY }}`. |

## Outputs

| Output | Notes |
|---|---|
| `connection_id` | ID of the deployed Fivetran connection. |
| `dashboard_url` | Direct URL to the connection in the Fivetran dashboard. |
| `status` | Result of this deploy run. One of: `created`, `created_needs_setup`, `updated`. |
| `active` | Paused state of the connection, read fresh from the Fivetran API after each deploy. `"true"` if active, `"false"` if paused. Useful on redeploys where `status` alone does not indicate whether the connection is paused. Empty string if the connection ID could not be determined. |

## Security

- `configuration_json` typically contains real credentials. GitHub only masks
  values that exactly match a registered secret in the logs. Merging multiple
  secrets into a single JSON string can change the bytes enough that the match
  no longer applies. The example caller workflow re-masks the assembled JSON
  explicitly using `::add-mask::` to cover this gap. Do the same in any caller
  workflow you write, and never print `configuration_json`.
- `FIVETRAN_API_KEY` needs permission to manage connections and read
  destinations. Set it once as a repository-level secret so every caller
  workflow can use it.
- `activate_on_create` reuses the same `FIVETRAN_API_KEY` for a direct
  `PATCH /v1/connectors/{id}` call with `paused: false`. No separate secret or
  permission is needed.

## Set up your deployment workflow

Each connector needs its own workflow file, called a caller workflow, that
references this action and supplies connector-specific inputs. Copy
[`../deploy-single-connector.yml`](../deploy-single-connector.yml) into your
repository's `.github/workflows/` and adapt it for your connector.

In each caller workflow, specify:

- **`on:` trigger**: When to deploy. The example triggers on push to `main`
  under your connector's path and supports manual `workflow_dispatch`. Adapt
  this to your branch and path.
- **`configuration_json`**: How to supply credentials. The example assembles
  this from GitHub Secrets. Secrets from any source work, including Vault,
  AWS/GCP Secrets Manager, and 1Password, since the action only sees the
  resulting JSON string. Not every field needs to be a secret. The example's
  `non_sensitive_setting` is a plain literal. Pushing secrets on every deploy
  is safe because it overwrites with the same values.
- **`runs-on`**: Which runner to use. Use whatever runner your repo's other
  workflows use.

If you have more than a few connectors,
[`../deploy-matrix.yml`](../deploy-matrix.yml) shows an alternative approach:
one workflow with a matrix built dynamically from changed paths, covering
multiple connectors. The `regional_usage` entries in `deploy-matrix.yml` show
how to deploy one connector to multiple destinations. Use per-connector
workflows for a small number of connectors, and switch to the matrix once the
per-connector approach becomes repetitive.

## Tests

`tests/test_deploy_connector.py` covers the create, retry, and redeploy decision
logic by mocking the `fivetran` subprocess call. No real Fivetran account is
needed. Run with:

```
uv run --with pytest --with requests pytest examples/workflows/github/action/tests
```

[`.github/workflows/test-deploy-action.yml`](../../../../.github/workflows/test-deploy-action.yml)
is a smoke test that runs this composite action against a real runner (`uses: ./...`) on
every PR that includes changes to it, across every create, retry, redeploy, and failure
scenario, and asserts on its actual outputs. It catches issues the unit tests
cannot, such as `action.yml`'s own environment variable configuration,
`$GITHUB_OUTPUT` writes, and the install step's shell logic. It does this by
swapping in a fake `fivetran` CLI instead of the real one. For details on how the
fake CLI works, see [`tests/fixtures/README.md`](tests/fixtures/README.md). No Fivetran account or credentials are needed.

## Known limitations

- The `requirements.txt`-only dependency install fallback is not covered by
  the smoke test above. The smoke test fixture uses `pyproject.toml`, and this
  fallback has not been tested against a real connector. The optional
  `fivetran_sdk_version` pin only prevents the SDK version from changing during
  a single deploy. It does not catch a future SDK version's breaking changes
  when you next update the SDK version, since nothing here runs the real CLI
  against a real destination.
- Detecting "this is a first deploy" and "placeholder setup tests failed as
  expected" both rely on matching substrings in the CLI's log output, since
  the SDK does not expose distinct exit codes for either case. If a future SDK
  version changes that wording, this action stops detecting these edge cases
  and reports a failure instead.
