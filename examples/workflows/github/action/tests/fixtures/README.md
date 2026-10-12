Fixtures for `.github/workflows/test-deploy-action.yml`, the smoke test that
runs the composite action (`uses: ./examples/workflows/github/action`) against
every create, retry, and redeploy scenario without a Fivetran account, API
key, or network access to Fivetran.

- `connector/` is a normal-looking connector directory with `pyproject.toml`
  and `configuration.example.json`, except its one dependency is
  `fake_fivetran_cli/` instead of `fivetran-connector-sdk`. There's no
  `connector.py`. Nothing here ever runs one, since the fake CLI never
  actually syncs data.
- `fake_fivetran_cli/` installs a `fivetran` console script, `fake_fivetran.py`,
  in its place. The install step in `action.yml` only falls back to installing
  the real SDK when `uv sync` didn't already produce a `fivetran` executable.
  See the "Install connector dependencies" step in `action.yml` for details.
  Since this fixture's `uv sync` does produce one, the real SDK and the real
  Fivetran CLI are never installed or invoked.

This exercises real `uv sync`, the composite action's real env-var wiring, the
subprocess and regex parsing of the CLI's stdout in `deploy_connector.py`, and
its `$GITHUB_OUTPUT` writes. This covers exactly the class of bugs that
`../test_deploy_connector.py`'s unit tests can't reach, since those call
`deploy_connector.py`'s functions directly rather than going through
`action.yml`.

> **Note:** Whenever a connection ID is known, `deploy_connector.py` always
> makes one real HTTP call to `https://api.fivetran.com/v1/connectors/{id}` to
> read back the connection's active state using `report_active_state`. The dummy
> API key used in the workflow makes that call fail with a real 401 from the
> Fivetran API. The script handles this as a warning, not a failure. This means
> the smoke test doesn't require credentials, but it isn't fully
> network-isolated.
