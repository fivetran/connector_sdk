import argparse
import os
import sys

from fivetran_connector_sdk.constants import (
    VALID_COMMANDS, DEFAULT_PYTHON_VERSION, SUPPORTED_PYTHON_VERSIONS, TEMPLATE_CONNECTOR_PATH
)
from fivetran_connector_sdk.helpers import print_library_log, suggest_correct_command
from fivetran_connector_sdk.logger import Logging

# Single source of truth for each command's one-line help text, so the argument
# parser and the fivetran_cli plugin adapter (plugin.py) can never drift apart.
COMMAND_DESCRIPTIONS = {
    "version": "Show fivetran_connector_sdk version and exit",
    "init": "Initialize a new connector project",
    "debug": "Run connector locally in debug mode",
    "deploy": "Deploy connector to Fivetran",
    "package": "Package connector code into a zip file",
    "reset": "Reset connector state",
    "configuration": "Interactively collect configuration values or run setup tests",
    "help": "Show this help message and exit",
}


class _UnsupportedDebugProxyAction(argparse.Action):
    """Reject proxy flags when they are passed to `fivetran debug`."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, "_reject_proxy_flags", False):
            parser.error(
                "Proxy Agent routing is not supported with `fivetran debug`. "
                f"`{option_string}` is only supported with `fivetran deploy`. "
                "Please run `fivetran debug` from a machine that can reach the source directly."
            )
        setattr(namespace, self.dest, values)


def _add_force(subparser):
    subparser.add_argument("-f", "--force", action="store_true", help=argparse.SUPPRESS)

def _add_yes(subparser):
    subparser.add_argument("--yes", action="store_true", help="Automatically answers yes to all confirmation prompts")

def _add_state(subparser, hidden=False):
    subparser.add_argument("--state", type=str, default=None, metavar="<state>",
                           help=argparse.SUPPRESS if hidden else "Path to state JSON file")

def _add_configuration(subparser, help_text=None):
    subparser.add_argument("--configuration", type=str, default=None, metavar="<configuration>",
                           help=help_text if help_text else "Path to configuration JSON file")

def _add_api_key(subparser):
    subparser.add_argument("--api-key", type=str, default=None, metavar="<api-key>",
                           help="Provide your base64-encoded API key for deployment")

def _add_destination(subparser):
    subparser.add_argument("--destination", type=str, default=None, metavar="<destination>",
                           help="Destination name (aka 'group name')")

def _add_connection(subparser):
    subparser.add_argument("--connection", type=str, default=None, metavar="<connection>",
                           help="Connection name (aka 'destination schema')")

def _add_python_version(subparser):
    subparser.add_argument("--python-version", "--python", type=str, metavar="<python-version>",
                           help=f"Supported Python versions you can use: {SUPPORTED_PYTHON_VERSIONS}. Defaults to {DEFAULT_PYTHON_VERSION}")

def _add_hd_agent_id(subparser):
    subparser.add_argument("--hybrid-deployment-agent-id", type=str, metavar="<hybrid-deployment-agent-id>",
                           help="Hybrid Deployment agent ID. Defaults to the destination's default agent.")

def _add_proxy_id(subparser, hidden=False):
    if subparser.get_default("_reject_proxy_flags"):
        subparser.add_argument(
            "--proxy-id",
            nargs="?",
            const="",
            default=None,
            metavar="<proxy-id>",
            action=_UnsupportedDebugProxyAction,
            help=argparse.SUPPRESS if hidden else "Proxy Agent ID for routing connector traffic through a Proxy Agent",
        )
        return

    subparser.add_argument("--proxy-id", type=str, default=None, metavar="<proxy-id>",
                           help=argparse.SUPPRESS if hidden else "Proxy Agent ID for routing connector traffic through a Proxy Agent")

def _add_proxy_host_config_key(subparser, hidden=False):
    if subparser.get_default("_reject_proxy_flags"):
        subparser.add_argument(
            "--proxy-host-config-key",
            nargs="?",
            const="",
            default=None,
            metavar="<proxy-host-config-key>",
            action=_UnsupportedDebugProxyAction,
            help=argparse.SUPPRESS if hidden else "Configuration key that contains the host details to proxy",
        )
        return

    subparser.add_argument("--proxy-host-config-key", type=str, default=None, metavar="<proxy-host-config-key>",
                           help=argparse.SUPPRESS if hidden else "Configuration key that contains the host details to proxy")


def _add_template(subparser):
    subparser.add_argument("--template", type=str, default=TEMPLATE_CONNECTOR_PATH, metavar="<template>",
                           help="Initialize a connector project from a template. Defaults to a path in fivetran/community_connectors. Use the examples/ prefix to reference a template from fivetran/connector_sdk")

def _add_project_path(subparser):
    subparser.add_argument("project_path", nargs='?', default=os.getcwd(),
                           help="Path to connector project directory (optional, defaults to current directory)")

def _add_naming(subparser):
    subparser.add_argument("--naming", type=str, default=None, metavar="<naming>",
                           help="Naming strategy for the connection schema. Options: FIVETRAN | SOURCE. Defaults to FIVETRAN.")

def _add_non_interactive(subparser):
    subparser.add_argument("--non-interactive", action="store_true", help="Automatically accepts the default choice for all confirmation prompts")

def _add_test(subparser):
    subparser.add_argument("--test", action="store_true",
                           help="Run all setup tests defined in configuration_form(). Only valid with the 'configuration' command.")

def _add_disable_encryption(subparser):
    subparser.add_argument("--disable-encryption", action="store_true",
                           help="Disable encryption for sensitive fields (not recommended when working with AI)")

def create_argument_parser():
    parser = argparse.ArgumentParser(
        prog="fivetran", allow_abbrev=False, add_help=True,
        usage="fivetran <command> <project_path> [options]",
        description="A command-line tool for developing and deploying Fivetran connectors.",
        epilog="For more information, refer to: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-commands",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--version", action="store_true",
                        help="Print the version of the fivetran_connector_sdk and exit")

    # Set a default at the top level so the attribute always exists on the namespace
    # subparsers that register --force override it when the user passes the flag.
    parser.set_defaults(force=False)
    parser.set_defaults(non_interactive=False)
    parser.set_defaults(yes=False)
    parser.set_defaults(test=False)

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    subparsers.add_parser("version", help=COMMAND_DESCRIPTIONS["version"],
                          usage="fivetran version")

    init_subparser = subparsers.add_parser("init", help=COMMAND_DESCRIPTIONS["init"],
                                           usage="fivetran init [project_path] [options]")
    _add_project_path(init_subparser)
    _add_template(init_subparser)
    _add_force(init_subparser)
    _add_non_interactive(init_subparser)
    _add_yes(init_subparser)

    debug_subparser = subparsers.add_parser("debug", help=COMMAND_DESCRIPTIONS["debug"],
                                            usage="fivetran debug [project_path] [options]")
    debug_subparser.set_defaults(_reject_proxy_flags=True)
    _add_project_path(debug_subparser)
    _add_configuration(debug_subparser)
    _add_state(debug_subparser)
    _add_naming(debug_subparser)
    _add_proxy_id(debug_subparser, hidden=True)
    _add_proxy_host_config_key(debug_subparser, hidden=True)

    deploy_subparser = subparsers.add_parser("deploy", help=COMMAND_DESCRIPTIONS["deploy"],
                                             usage="fivetran deploy [project_path] [options]")
    _add_project_path(deploy_subparser)
    _add_api_key(deploy_subparser)
    _add_destination(deploy_subparser)
    _add_connection(deploy_subparser)
    _add_configuration(deploy_subparser, "Path to configuration JSON file. On redeploy, existing configuration is preserved if none is provided.")
    _add_python_version(deploy_subparser)
    _add_hd_agent_id(deploy_subparser)
    _add_proxy_id(deploy_subparser, hidden=True)
    _add_proxy_host_config_key(deploy_subparser, hidden=True)
    _add_state(deploy_subparser, hidden=True)
    _add_naming(deploy_subparser)
    _add_force(deploy_subparser)
    _add_non_interactive(deploy_subparser)
    _add_yes(deploy_subparser)

    package_subparser = subparsers.add_parser("package", help=COMMAND_DESCRIPTIONS["package"],
                                              usage="fivetran package [project_path] [options]")
    _add_project_path(package_subparser)
    _add_force(package_subparser)
    _add_non_interactive(package_subparser)
    _add_yes(package_subparser)

    reset_subparser = subparsers.add_parser("reset", help=COMMAND_DESCRIPTIONS["reset"],
                                            usage="fivetran reset [project_path] [options]")
    _add_project_path(reset_subparser)
    _add_force(reset_subparser)
    _add_non_interactive(reset_subparser)
    _add_yes(reset_subparser)

    configuration_subparser = subparsers.add_parser(
        "configuration",
        usage="fivetran configuration [project_path] [options]",
    )
    _add_project_path(configuration_subparser)
    _add_test(configuration_subparser)
    _add_disable_encryption(configuration_subparser)

    subparsers.add_parser("help", help=COMMAND_DESCRIPTIONS["help"],
                          usage="fivetran help")
    return parser


def intercept_unknown_command():
    """Preserve suggest_correct_command for typos and scan sys.argv for the first positional token
    if it matches a known subcommand we normalize its case and return;
    if it does not, route through suggest_correct_command
    """
    for argv_index, token in enumerate(sys.argv[1:], start=1):
        if token.startswith("-"):
            continue
        token_lower = token.lower()
        if token_lower in VALID_COMMANDS:
            sys.argv[argv_index] = token_lower
            return
        if not suggest_correct_command(token):
            print_library_log(f"invalid command: {token}, see `fivetran help`",
                              Logging.Level.SEVERE)
        sys.exit(1)
