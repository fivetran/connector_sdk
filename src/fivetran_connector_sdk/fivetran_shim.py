"""Compatibility entrypoint for the ``fivetran`` console script."""


def main():
    """Run the unified CLI when installed; otherwise run the SDK CLI directly."""
    try:
        from fivetran_cli.cli import main as cli_main
    except ModuleNotFoundError as exc:
        if exc.name != "fivetran_cli":
            raise
        from fivetran_connector_sdk.cli import main as cli_main

    return cli_main()
