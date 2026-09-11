# Deploy Fivetran CSDK Connector (composite action)

Generic composite action for deploying any Fivetran Connector SDK connector.
It doesn't know any connector's specific field names -- each connector
supplies its own `configuration_json` (or none) via its own caller workflow.
Reference it from your own repo's workflow as:

```yaml
- uses: fivetran/connector_sdk/examples/workflows/github/action@main
  with:
    connector_dir: path/to/your/connector
    fivetran_api_key: ${{ secrets.FIVETRAN_API_KEY }}
    # ...see Inputs below
```

Pin `@main` to a specific tag or commit SHA once one exists, the same way you
would for any other third-party action. See
[`../deploy-single-connector.yml`](../deploy-single-connector.yml) for a full
example.

## What it does

1. If `configuration_json` is set, pushes it -- creating the connection if it
   doesn't exist, or overwriting the existing one's stored config if it does.
   Its presence is the only signal this action looks at.
2. Otherwise, tries a code-only deploy. If that's rejected because the
   connection doesn't exist yet, retries once with a placeholder config
   (`empty_config_path`, default `configuration.example.json`) so the
   connection still gets created, paused, with its setup form ready for
   someone to fill in real values in the dashboard.
3. Prints a warning (not a failure) when the placeholder's setup tests fail as
   expected; a real failure still fails the job.
4. `fivetran deploy` always creates new connections paused -- there's no CLI
   flag for it. If `activate_on_create` is `"true"` **and** this run is the
   one that created the connection with real configuration (status
   `created`), the action makes a follow-up call to the Fivetran API to
   unpause it. This is a one-time effect, not a desired-state setting: it has
   no effect on redeploys of an already-existing connection (status
   `updated`), and a connection created with only placeholder configuration
   (status `created_needs_setup`) is always left paused regardless, since it
   has no real credentials yet.

## Inputs

| input | required | default | notes |
|---|---|---|---|
| `connector_dir` | yes | -- | path to the connector project (contains `connector.py`) |
| `destination` | no | `""` | Fivetran destination/group name; auto-selected if there's exactly one |
| `connection_name` | no | `""` | derived from `connector_dir`'s folder name if left empty |
| `configuration_json` | no | `""` | full `configuration.json` content as a string, only if you mean to push it now. **Sensitive** -- see [Security](#security) |
| `empty_config_path` | no | `"configuration.example.json"` | placeholder file (relative to `connector_dir`) for a first deploy without real config |
| `python_version` | no | `""` | optional `--python-version` override |
| `fivetran_sdk_version` | no | `""` | pins `fivetran-connector-sdk` (e.g. `"2.11.0"`); unpinned if left empty. Always applies for `requirements.txt`-only connectors. For `pyproject.toml` connectors it's only used as a fallback install when `uv sync` didn't already provide a `fivetran` CLI -- a connector that pins its own version via `uv.lock` keeps that pin |
| `activate_on_create` | no | `"false"` | if `"true"`, unpause the connection right after *this run* creates it with real config. One-time effect only -- ignored on redeploys and on placeholder-config creations. See [Security](#security) for the API call this makes |
| `fivetran_api_key` | yes | -- | e.g. `${{ secrets.FIVETRAN_API_KEY }}` |

## Outputs

`connection_id`, `dashboard_url`, `status` (`created` / `created_needs_setup` /
`updated`), `active` (`"true"` / `"false"`, read fresh from the Fivetran API
after the deploy -- useful on a redeploy of an already-existing connection,
where `status` alone doesn't tell you whether it's paused).

## Wiring up a connector

Each connector needs its own small caller workflow (not provided
automatically) -- copy
[`../deploy-single-connector.yml`](../deploy-single-connector.yml) into your
repo's `.github/workflows/` and adapt it. Once you have more than a few
connectors, [`../deploy-matrix.yml`](../deploy-matrix.yml) shows an
alternative: one workflow with a matrix built dynamically from changed paths,
covering several connectors (and, in the `regional_usage` entries, one
connector deployed to multiple destinations) from a single file. Either
pattern calls the same composite action -- pick per-connector workflows for a
couple of connectors, or the matrix once that gets repetitive.

A single caller workflow (`deploy-single-connector.yml`) owns:

- **The trigger** -- the example deploys on push to `main` under your
  connector's own path, plus manual `workflow_dispatch`. It assembles and
  pushes `configuration_json` every run: since the secrets *are* the source
  of truth, pushing them on every deploy is just idempotent config-as-code,
  not a risk to guard against.
- **Assembling `configuration_json`** from this connector's own secrets --
  plain GitHub Secrets in the example, but any source works (Vault, AWS/GCP
  Secrets Manager, 1Password, ...) since the action only ever sees the
  resulting JSON string. Not every field needs to be a secret either -- the
  example's `non_sensitive_setting` is a plain literal, since it isn't
  sensitive.
- **`runs-on`** -- pick whatever runner your repo's other workflows use.

## Security

- `configuration_json` typically carries real credentials. GitHub only masks
  values that still exactly match a registered secret in the logs -- merging
  several secrets into one JSON string (escaping newlines, etc.) can change
  the bytes enough that the match no longer applies. The example re-masks the
  assembled blob explicitly (`::add-mask::`) to cover that gap; do the same in
  any caller workflow you write, and never print `configuration_json`.
- `FIVETRAN_API_KEY` needs permission to manage connections and read
  destinations. Set it once as a repo-level secret; every caller workflow can
  use it, since it isn't connector-specific.
- `activate_on_create` reuses the same `FIVETRAN_API_KEY` for a direct
  `PATCH /v1/connectors/{id}` call (setting `paused: false`) -- no separate
  secret or permission is needed.

## Tests

`tests/test_deploy_connector.py` covers the create/retry/redeploy decision
logic by mocking the `fivetran` subprocess call -- no real Fivetran account
needed. Run with:

```
uv run --with pytest --with requests pytest examples/workflows/github/action/tests
```

[`.github/workflows/test-deploy-action.yml`](../../../../.github/workflows/test-deploy-action.yml)
is a smoke test that runs this composite action for real (`uses: ./...`) on
every PR touching it, across every create/retry/redeploy/failure branch, and
asserts on its actual outputs. It catches the class of bugs the unit tests
above can't -- `action.yml`'s own env-var wiring, `$GITHUB_OUTPUT` writes,
the install step's shell logic -- by swapping in a fake `fivetran` CLI (see
[`tests/fixtures/README.md`](tests/fixtures/README.md)) instead of the real
one, so it needs no Fivetran account or credentials either.

## Known limitations

- The `requirements.txt`-only dependency-install fallback (for a connector
  without `pyproject.toml`) isn't covered by the smoke test above (its
  fixture uses `pyproject.toml`) and hasn't been exercised against a real
  connector. It now accepts an optional `fivetran_sdk_version` pin (see
  Inputs), but that only protects a single deploy from drifting mid-flight --
  it doesn't catch a *future* SDK version's breaking changes on the next
  deliberate bump, since nothing here runs the real CLI against a real
  destination.
- Detecting "this is a first deploy" and "placeholder setup tests failed as
  expected" both rely on matching substrings in the CLI's log output, since
  the SDK doesn't expose distinct exit codes for either case. If a future SDK
  version changes that wording, this stops detecting the soft cases and just
  reports a hard failure instead.
