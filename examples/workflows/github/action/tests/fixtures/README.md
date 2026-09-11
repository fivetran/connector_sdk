Fixtures for `.github/workflows/test-deploy-action.yml`, the smoke test that
runs the composite action for real (`uses: ./examples/workflows/github/action`)
against every branch of its create/retry/redeploy logic -- without a Fivetran
account, API key, or network access to Fivetran.

- `connector/` is a normal-looking connector directory (`pyproject.toml` +
  `configuration.example.json`), except its one dependency is
  `fake_fivetran_cli/` instead of `fivetran-connector-sdk`. There's no
  `connector.py` -- nothing here ever runs one, since the fake CLI never
  actually syncs data.
- `fake_fivetran_cli/` installs a `fivetran` console script
  (`fake_fivetran.py`) in its place. `action.yml`'s install step only falls
  back to installing the real SDK when `uv sync` didn't already produce a
  `fivetran` executable (see action.yml's "Install connector dependencies"
  step) -- since this fixture's `uv sync` does, the real SDK, and the real
  Fivetran CLI, are never installed or invoked.

This exercises real `uv sync`, the composite action's real env-var wiring,
`deploy_connector.py`'s subprocess/regex parsing of the CLI's stdout, and its
`$GITHUB_OUTPUT` writes -- exactly the class of bugs that
`../test_deploy_connector.py`'s unit tests can't reach, since those call
`deploy_connector.py`'s functions directly rather than going through
`action.yml`.

Note: whenever a connection ID is known, `deploy_connector.py` always makes
one real HTTP call to `https://api.fivetran.com/v1/connectors/{id}` to read
back the connection's active state (`report_active_state`). The dummy API key
used in the workflow makes that call fail with a real 401 from Fivetran's
actual API, which `deploy_connector.py` handles as a warning, not a failure --
so this doesn't require credentials, but it does mean the smoke test isn't
fully network-isolated.
