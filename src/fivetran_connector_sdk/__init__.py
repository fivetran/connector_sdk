import os

os.environ["GRPC_VERBOSITY"] = "ERROR"
import sys
import grpc
import json
import atexit
import traceback
import faulthandler
import threading
import queue
import subprocess
from types import GeneratorType
from http import HTTPStatus
from concurrent import futures
from typing import Callable, Optional

from fivetran_connector_sdk.initialisation_helper import init
from fivetran_connector_sdk.crash_report import build_debug_crash_report
from fivetran_connector_sdk.protos import common_pb2
from fivetran_connector_sdk.protos import connector_sdk_pb2
from fivetran_connector_sdk.protos import connector_sdk_pb2_grpc

from fivetran_connector_sdk.logger import Logging
from fivetran_connector_sdk.file_upload import ByteStream, FileUpload
from fivetran_connector_sdk.operations import Operations
from fivetran_connector_sdk.configuration_form import ConfigurationForm
from fivetran_connector_sdk.test import Test
from fivetran_connector_sdk import constants
from fivetran_connector_sdk.memory_tracker import get_memory_tracker
from fivetran_connector_sdk.constants import (
    DEPRECATED_FORCE_FLAG_WARNING,
    DEFAULT_PYTHON_VERSION,
    TABLES,
    PYPROJECT_TOML,
)
from fivetran_connector_sdk.helpers import (
    print_library_log,
    reset_local_file_directory,
    find_connector_object,
    PromptMode,
    resolve_confirmation,
    _resolve_existing_project_path,
    enable_debugging_for_verbose_commands,
)
from fivetran_connector_sdk.cli_parser import create_argument_parser, intercept_unknown_command
from fivetran_connector_sdk.connector_helper import (
    validate_requirements_file,
    validate_pyproject_file,
    package_project,
    create_package,
    update_connection,
    get_connection_details,
    create_connection,
    get_group_info,
    run_tester,
    run_configuration_tester,
    ensure_tester_installed,
    process_tables,
    update_base_url_if_required,
    exit_check,
    get_available_port,
    check_dict,
    check_newer_version,
    get_destination_group,
    get_connection_name,
    get_api_key,
    get_state,
    get_naming,
    get_python_version,
    get_hd_agent_id,
    get_proxy_id,
    get_proxy_host_config_key,
    get_configuration,
    validate_proxy_configuration,
    handle_connection_response,
    validate_required_deploy_params,
    validate_configuration,
    get_update_prompt,
)

# Version format: <major_version>.<minor_version>.<patch_version>
# (where Major Version = 2, Minor Version is incremental MM from Aug 25 onwards, Patch Version is incremental within a month)
__version__ = "2.12.1"
MAX_MESSAGE_LENGTH = 128 * 1024 * 1024  # 128MB

__all__ = [
    cls.__name__ for cls in [ByteStream, FileUpload, Logging, Operations, ConfigurationForm, Test]
] + ["form_field"]


def package(
    project_path: str,
    prompt_mode: PromptMode = PromptMode.INTERACTIVE,
    configuration_form_method: Optional[Callable] = None,
):
    """Packages the connector project into a distributable zip file.

    Args:
        project_path (str): The path to the connector project directory.
        prompt_mode (PromptMode): Controls how prompts are answered. Defaults to INTERACTIVE.
        configuration_form_method: Optional callable returning a ConfigurationForm instance.
    """
    if prompt_mode != PromptMode.FORCE:
        pyproject_path = os.path.join(project_path, PYPROJECT_TOML)
        if os.path.exists(pyproject_path):
            validate_pyproject_file(project_path, True, prompt_mode)
        else:
            validate_requirements_file(project_path, True, __version__, prompt_mode)
    else:
        print_library_log(f"skipping dependency validation; {prompt_mode.value} is set")

    package_path = create_package(project_path, configuration_form_method)
    print_library_log(f"package created at: {package_path}", log_icon=Logging.LogIcon.SUCCESS)
    sys.exit(0)


def _format_runtime_error_message(error_message):
    if constants.DEBUGGING:
        return error_message
    # The stacktrace is appended to the RuntimeError message so that the java client
    # can surface it in the user task.
    return f"{error_message}\n{traceback.format_exc()}"


class Connector(connector_sdk_pb2_grpc.SourceConnectorServicer):
    # noinspection PyShadowingNames
    def __init__(self, update, schema=None, configuration_form=None):
        """Initializes the Connector instance.
        Args:
            update: The update method.
            schema: The schema method.
            configuration_form: Optional callable returning a ConfigurationForm instance.
        """

        self.schema_method = schema
        self.update_method = update
        self.configuration_form_method = configuration_form
        self._cached_form = None

        self.configuration = None
        self.state = None
        self.project_path = None
        self._debug_crash_report = None

        update_base_url_if_required()

    # Call this method to deploy the connector to Fivetran platform
    def deploy(
        self,
        project_path: str,
        deploy_key: str,
        group: str,
        connection: str,
        hd_agent_id: str,
        configuration: dict = None,
        config_path=None,
        python_version: str = None,
        prompt_mode: PromptMode = PromptMode.INTERACTIVE,
        naming: str = None,
        proxy_id: str = None,
        proxy_host_config_key: str = None,
    ):
        """Deploys the connector to the Fivetran platform.

        Args:
            project_path (str): The path to the project.
            deploy_key (str): The deployment key.
            group (str): The group name.
            connection (str): The connection name.
            hd_agent_id (str): The hybrid deployment agent ID within the Fivetran system.
            configuration (dict): The configuration dictionary.
            config_path (str): The path to the configuration file.
            python_version (str): The Python version to use.
            prompt_mode (PromptMode): Controls how prompts are answered. Defaults to INTERACTIVE.
            naming (str): The formatted naming strategy (e.g., "FIVETRAN_NAMING" or "SOURCE_NAMING").
            proxy_id (str): Proxy Agent ID used for proxy routing.
            proxy_host_config_key (str): Configuration key that contains the proxied host details.
        """
        constants.EXECUTED_VIA_CLI = True
        print_library_log("executing deploy:")
        deploy_cmd = f"fivetran deploy --destination {group} --connection {connection} --api-key {deploy_key[0:8]}******** "
        if config_path:
            deploy_cmd += f"--configuration {config_path} "
        if python_version:
            deploy_cmd += f"--python-version {python_version} "
        if hd_agent_id:
            deploy_cmd += f"--hd-agent-id {hd_agent_id} "
        if proxy_id:
            deploy_cmd += f"--proxy-id {proxy_id} "
        if proxy_host_config_key:
            deploy_cmd += f"--proxy-host-config-key {proxy_host_config_key} "
        if naming:
            deploy_cmd += f"--naming {naming} "
        if prompt_mode.value:
            deploy_cmd += prompt_mode.value
        print_library_log(deploy_cmd)

        check_newer_version(__version__)

        resolved_proxy_host_config_key = validate_proxy_configuration(
            configuration or {}, proxy_id, proxy_host_config_key, hd_agent_id
        )
        check_dict(
            configuration,
            True,
            {resolved_proxy_host_config_key} if resolved_proxy_host_config_key else None,
        )

        secrets_list = []
        if configuration:
            for k, v in configuration.items():
                secrets_list.append({"key": k, "value": v})

        connection_config = {
            "schema": connection,
            "secrets_list": secrets_list,
        }

        if python_version:
            connection_config["python_version"] = python_version
        if resolved_proxy_host_config_key:
            connection_config["proxy_host_config_key"] = resolved_proxy_host_config_key

        if prompt_mode != PromptMode.FORCE:
            pyproject_path = os.path.join(project_path, PYPROJECT_TOML)
            if os.path.exists(pyproject_path):
                validate_pyproject_file(project_path, True, prompt_mode)
            else:
                validate_requirements_file(project_path, True, __version__, prompt_mode)
        else:
            print_library_log(f"skipping dependency validation; {prompt_mode.value} is set")

        group_id, group_name = get_group_info(group, deploy_key)
        connection_id, service = get_connection_details(
            connection, group, group_id, deploy_key
        ) or (None, None)

        if connection_id:
            if naming:
                print_library_log(
                    "ignored --naming flag; naming strategy cannot be changed after connection creation",
                    Logging.Level.WARNING,
                )
            if service != "connector_sdk":
                print_library_log(
                    f"cannot update connection '{connection}'; not a Connector SDK connection",
                    level=Logging.Level.SEVERE,
                    log_icon=Logging.LogIcon.FAILURE,
                )
                sys.exit(1)
            else:
                update_prompt = get_update_prompt(connection, group, configuration, config_path)
                should_update = resolve_confirmation(update_prompt, False, prompt_mode)

                if should_update:
                    print_library_log(
                        f"updating connection {connection} in group {group_name}",
                        log_icon=Logging.LogIcon.STEP,
                    )
                    package_id = package_project(
                        project_path, deploy_key, self.configuration_form_method
                    )
                    response = update_connection(
                        connection_id,
                        connection,
                        group_name,
                        connection_config,
                        package_id,
                        deploy_key,
                        hd_agent_id,
                        proxy_id,
                    )
                    handle_connection_response(
                        response,
                        package_id,
                        deploy_key,
                        HTTPStatus.OK.value,
                        is_new_connection=False,
                        connection_id=connection_id,
                    )
                else:
                    print_library_log("update cancelled", log_icon=Logging.LogIcon.FAILURE)
                    sys.exit(1)
        else:
            validate_configuration(configuration)
            if not python_version:
                print_library_log(
                    f"python version not specified; connection will use the default python version ({DEFAULT_PYTHON_VERSION})"
                )
                print_library_log(
                    "set --python-version <version> in the deploy command or update it in your Fivetran dashboard"
                )
            package_id = package_project(project_path, deploy_key, self.configuration_form_method)
            response = create_connection(
                deploy_key, group_id, connection_config, hd_agent_id, package_id, naming, proxy_id
            )
            handle_connection_response(
                response, package_id, deploy_key, HTTPStatus.CREATED.value, is_new_connection=True
            )

    # Call this method to run the connector in production
    def run(
        self,
        port: int = 50049,
        configuration: dict = None,
        state: dict = None,
        log_level: Logging.Level = Logging.Level.INFO,
    ) -> grpc.Server:
        """Runs the connector server.

        Args:
            port (int): The port number to listen for incoming requests.
            configuration (dict): The configuration dictionary.
            state (dict): The state dictionary.
            log_level (Logging.Level): The logging level.

        Returns:
            grpc.Server: The gRPC server instance.
        """
        self.configuration = check_dict(configuration, True)
        self.state = check_dict(state)
        Logging.LOG_LEVEL = log_level

        if not constants.DEBUGGING:
            """
            DO NOT MODIFY THE LOG MESSAGE BELOW
            This is used to identify the readiness of the connector to run the code.
            Any changes may break integration or automated workflows.
            This is referenced at https://github.com/fivetran/engineering/blob/main/connector_sdk/core/src/com/fivetran/connector_sdk/core/ConnectorSdkUtils.java#L73
            """
            print_library_log(f"Running on fivetran_connector_sdk: {__version__}")

        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10),
            options=[
                ("grpc.max_send_message_length", MAX_MESSAGE_LENGTH),
                ("grpc.max_receive_message_length", MAX_MESSAGE_LENGTH),
            ],
        )
        connector_sdk_pb2_grpc.add_SourceConnectorServicer_to_server(self, server)
        bind_address = "127.0.0.1" if constants.DEBUGGING else "[::]"
        server.add_insecure_port(bind_address + ":" + str(port))
        server.start()
        if constants.DEBUGGING:
            return server
        server.wait_for_termination()

    # This method starts both the server and the local testing environment
    def debug(
        self,
        project_path: str = None,
        configuration: dict = None,
        state: dict = None,
        naming: str = None,
        log_level: Logging.Level = Logging.Level.DEBUG,
    ):
        """Tests the connector code by running it with the connector tester.\n
        state.json docs: https://fivetran.com/docs/connector-sdk/connector-sdk-concepts/state-management#statemanagement\n
        configuration.json docs: https://fivetran.com/docs/connector-sdk/connector-development-and-configuration/configuration-json#workingwithconfigurationjson

        Args:
            project_path (str): The path to the project.
            configuration (dict): The configuration dictionary, same as configuration.json if present.
            state (dict): The state dictionary, same as state.json if present.
            log_level (Logging.Level): The logging level.
            naming (str): The formatted naming strategy (e.g., "FIVETRAN_NAMING" or "SOURCE_NAMING").
        """
        constants.DEBUGGING = True
        validate_configuration(configuration)

        check_newer_version(__version__)

        Logging.LOG_LEVEL = log_level
        java_exe, tester_root_dir = ensure_tester_installed()

        project_path = os.getcwd() if project_path is None else project_path
        project_path = _resolve_existing_project_path(project_path)
        self.project_path = project_path
        pyproject_path = os.path.join(project_path, PYPROJECT_TOML)
        if os.path.exists(pyproject_path):
            validate_pyproject_file(project_path, False)
        else:
            validate_requirements_file(project_path, False, __version__)
        print_library_log(f"debugging connector at: {project_path}", log_icon=Logging.LogIcon.STEP)
        self._register_debug_crash_report_at_exit()
        try:
            faulthandler.enable()
        except (RuntimeError, OSError):
            pass

        available_port = get_available_port()
        exit_check(project_path)

        if available_port is None:
            raise RuntimeError(
                "failed to allocate port error: no available port in range 50049-50060"
            )

        server = self.run(available_port, configuration, state, log_level=log_level)

        # Uncomment this to run the tester manually
        # server.wait_for_termination()

        try:
            print_library_log("starting connector tester", log_icon=Logging.LogIcon.STEP)
            for log_msg in run_tester(
                java_exe,
                tester_root_dir,
                project_path,
                available_port,
                json.dumps(self.state),
                self.configuration,
                naming,
            ):
                print(log_msg, end="")
        finally:
            server.stop(grace=2.0)

    def _validate_and_cache_form(self, run_tests: bool):
        if self.configuration_form_method is None:
            print_library_log(
                "Your connector does not implement the configuration_form() method. Please implement it and re-run."
                "\nFor more information, see https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-setup-form",
                Logging.Level.SEVERE,
            )
            sys.exit(1)

        constants.DEBUGGING = True
        Logging.LOG_LEVEL = Logging.Level.INFO
        try:
            self._cached_form = self.configuration_form_method()
        except Exception as e:
            self._set_debug_crash_report(e, "configuration_form()")
            raise

        if run_tests and not self._cached_form._tests:
            print_library_log(
                "Your connector does not provide any configuration tests to run.",
                Logging.Level.SEVERE,
            )
            sys.exit(1)

    def _confirm_configuration_override(self, project_path: str):
        config_path = os.path.join(project_path, constants.CONFIGURATION_JSON)
        if os.path.exists(config_path):
            confirm = input(
                f"'{constants.CONFIGURATION_JSON}' already exists in '{project_path}'\n"
                f"running this command will override it\n"
                f"continue? (y/N): "
            )
            if confirm.lower() != "y":
                print_library_log(
                    f"'{constants.CONFIGURATION_JSON}' already exists; creating new file and overriding values cancelled"
                )
                sys.exit(0)

    def generate_configuration(
        self, project_path: str, run_tests: bool = False, disable_encryption: bool = False
    ):
        """Runs the fivetran configuration command via the connector tester.

        Starts the gRPC server and invokes the Java tester in configuration mode.
        The tester calls ConfigurationForm to get fields, prompts the user interactively,
        and saves configuration.json. With run_tests=True, it calls Test for each registered
        test and displays results.

        Args:
            project_path: Path to the connector project directory.
            run_tests: If True, run setup tests instead of collecting configuration.
            disable_encryption: If True, skip encryption of sensitive fields. Defaults to False.
        """
        project_path = os.getcwd() if project_path is None else project_path
        self.project_path = project_path
        self._register_debug_crash_report_at_exit()

        self._validate_and_cache_form(run_tests)
        check_newer_version(__version__)

        if not run_tests:
            self._confirm_configuration_override(project_path)

        java_exe, tester_root_dir = ensure_tester_installed()

        available_port = get_available_port()
        if available_port is None:
            raise RuntimeError(
                "failed to allocate port error: no available port in range 50049-50060"
            )

        server = self.run(available_port, {}, log_level=Logging.Level.INFO)
        try:
            print_library_log("starting connector tester", log_icon=Logging.LogIcon.STEP)
            run_configuration_tester(
                java_exe,
                tester_root_dir,
                project_path,
                available_port,
                run_tests,
                disable_encryption,
            )
        except subprocess.CalledProcessError:
            raise
        except Exception as e:
            print(traceback.format_exc())
            raise e
        finally:
            server.stop(grace=2.0)

    def _register_debug_crash_report_at_exit(self):
        # Registered at exit so the report prints after the java tester's failure
        # summary, which is emitted when the tester subprocess is torn down.
        atexit.register(self._print_debug_crash_report)

    def _print_debug_crash_report(self):
        if not self._debug_crash_report:
            return
        print(Logging.colorize(self._debug_crash_report, Logging.Level.SEVERE))
        self._debug_crash_report = None
        atexit.unregister(self._print_debug_crash_report)

    def _set_debug_crash_report(self, exception, handler, state=None, memory_tracker=None):
        if not constants.DEBUGGING:
            return

        try:
            self._debug_crash_report = build_debug_crash_report(
                exception,
                self.project_path,
                configuration=self.configuration,
                handler=handler,
                sdk_version=__version__,
                state=state,
                memory_tracker=memory_tracker,
            )
        except Exception as report_error:
            # Crash reports are best-effort diagnostics and must not replace the customer exception.
            print_library_log(
                f"failed to build crash report: {report_error}. Please contact support: https://support.fivetran.com/",
                Logging.Level.WARNING,
            )

    # -- Methods below override ConnectorServicer methods
    def ConfigurationForm(self, request, context):
        """Overrides the ConfigurationForm method from ConnectorServicer.

        Args:
            request: The gRPC request.
            context: The gRPC context.

        Returns:
            common_pb2.ConfigurationFormResponse: The configuration form response.
        """
        if self.configuration_form_method is None:
            return common_pb2.ConfigurationFormResponse()

        try:
            if Logging.LOG_LEVEL is None:
                Logging.LOG_LEVEL = Logging.Level.INFO
            print_library_log("calling configuration_form()", Logging.Level.INFO)
            form = self._get_configuration_form()
            return form._to_proto()
        except Exception as e:
            self._set_debug_crash_report(e, "configuration_form()")
            error_message = f"failed while executing configuration_form() error: {str(e)}"
            print_library_log(error_message, Logging.Level.SEVERE)
            raise RuntimeError(_format_runtime_error_message(error_message)) from e

    def Test(self, request, context):
        """Overrides the Test method from ConnectorServicer.

        Dispatches to the test function registered in ConfigurationForm whose __name__
        matches request.name.

        Args:
            request: The gRPC request containing name and configuration.
            context: The gRPC context.

        Returns:
            common_pb2.TestResponse: The test result.
        """
        if self.configuration_form_method is None:
            return common_pb2.TestResponse(success=True)

        try:
            if Logging.LOG_LEVEL is None:
                Logging.LOG_LEVEL = Logging.Level.INFO
            form = self._get_configuration_form()
            test_fn = form._get_test_function_by_name(request.name)
            if test_fn is None:
                raise RuntimeError(f"no test registered with name '{request.name}'")
            configuration = (
                self.configuration if self.configuration else dict(request.configuration)
            )
            print_library_log(f"calling test '{request.name}'", Logging.Level.INFO)
            result = test_fn(configuration)
            if not isinstance(result, common_pb2.TestResponse):
                return common_pb2.TestResponse(
                    failure=f"test '{request.name}' must return Test.success() or Test.failure(...), got {type(result).__name__}"
                )
            return result
        except Exception as e:
            self._set_debug_crash_report(e, "test()")
            error_message = f"failed while executing test '{request.name}' error: {str(e)}"
            print_library_log(error_message, Logging.Level.SEVERE)
            raise RuntimeError(_format_runtime_error_message(error_message)) from e

    def _get_configuration_form(self):
        if self._cached_form is None:
            self._cached_form = self.configuration_form_method()
        return self._cached_form

    def Schema(self, request, context):
        """Overrides the Schema method from ConnectorServicer.

        Args:
            request: The gRPC request.
            context: The gRPC context.

        Returns:
            connector_sdk_pb2.SchemaResponse: The schema response.
        """

        table_list = {}

        if not self.schema_method:
            return connector_sdk_pb2.SchemaResponse(schema_response_not_supported=True)
        else:
            try:
                configuration = (
                    self.configuration if self.configuration else dict(request.configuration)
                )
                print_library_log("calling schema()", Logging.Level.INFO)
                response = self.schema_method(configuration)
                process_tables(response, table_list)
                return connector_sdk_pb2.SchemaResponse(
                    without_schema=common_pb2.TableList(tables=TABLES.values())
                )

            except Exception as e:
                self._set_debug_crash_report(e, "schema()")
                error_message = f"failed while executing schema() error: {str(e)}"
                print_library_log(error_message, Logging.Level.SEVERE)
                raise RuntimeError(_format_runtime_error_message(error_message)) from e

    def Update(self, request, context):
        """Overrides the Update method from ConnectorServicer.

        Args:
            request: The gRPC request.
            context: The gRPC context.

        Yields:
            connector_sdk_pb2.UpdateResponse: The update response.
        """
        configuration = self.configuration if self.configuration else dict(request.configuration)
        state = self.state if self.state else json.loads(request.state_json)
        exception_queue = queue.Queue()
        memory_tracker = None

        try:
            # Create memory tracker for both debug and sync modes
            memory_tracker = get_memory_tracker()
            memory_tracker.start()

            print_library_log("calling update()", Logging.Level.INFO)

            def run_update():
                try:
                    result = self.update_method(configuration=configuration, state=state)
                    # If the customer's update method returns a generator (i.e., uses yield),
                    # exhaust the generator responses, they are None. From this point on, all operations
                    # push update_response to a queue, and we yield from the queue instead.
                    # We return None here intentionally.
                    if isinstance(result, GeneratorType):
                        for _ in result:
                            pass
                    # If the update method doesn't use yield, skip the response returned.
                    else:
                        pass
                except Exception as exc:
                    exception_queue.put(exc)
                finally:
                    Operations.operation_stream.mark_done()

            thread = None
            try:
                thread = threading.Thread(target=run_update)
                thread.start()

                # consumer - yield the operations in the operation_stream.
                for response in Operations.operation_stream:
                    # checkpoint and file-upload-chunk flushes both return a list of responses.
                    if isinstance(response, list):
                        for res in response:
                            yield res
                        # add_checkpoint blocks the producer until its checkpoint response is yielded.
                        # File-upload flushes also return lists, but they do not block the producer, so
                        # unblock only when this batch contains a checkpoint.
                        if any(res.WhichOneof("operation") == "checkpoint" for res in response):
                            Operations.operation_stream.unblock()
                    else:
                        yield response
            finally:
                memory_tracker.stop()
                if thread is not None:
                    thread.join()

            # Check if any exception was raised during the update
            if not exception_queue.empty():
                raise exception_queue.get()

            print_library_log(
                "finished receiving records from customer's update().", Logging.Level.INFO, True
            )

        except Exception as e:
            self._set_debug_crash_report(e, "update()", state=state, memory_tracker=memory_tracker)
            error_message = f"failed while executing update() error: {str(e)}"
            print_library_log(error_message, Logging.Level.SEVERE)
            raise RuntimeError(_format_runtime_error_message(error_message)) from e


def print_version():
    print_library_log("fivetran_connector_sdk " + __version__)
    sys.exit(0)


def main():
    """The main entry point for the script.
    Parses command line arguments and passes them to connector object methods.
    """
    constants.EXECUTED_VIA_CLI = True
    intercept_unknown_command()
    parser = create_argument_parser()
    args = parser.parse_args()
    enable_debugging_for_verbose_commands(args.command)
    try:
        prompt_mode = PromptMode.from_args(args.non_interactive, args.force, args.yes)
    except ValueError as e:
        print_library_log(str(e), Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        sys.exit(1)
    if args.force:
        print_library_log(DEPRECATED_FORCE_FLAG_WARNING, Logging.Level.WARNING)

    if args.version:
        print_version()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command.lower() == "version":
        print_version()
    elif args.command.lower() == "init":
        check_newer_version(__version__)
        init(args.project_path, args.template, prompt_mode)
    elif args.command.lower() == "help":
        parser.print_help()
        sys.exit(0)

    try:
        args.project_path = _resolve_existing_project_path(args.project_path)
    except ValueError as e:
        print_library_log(str(e), level=Logging.Level.SEVERE, log_icon=Logging.LogIcon.FAILURE)
        sys.exit(1)

    if args.command.lower() == "reset":
        reset_local_file_directory(args, prompt_mode)
        sys.exit(0)

    connector_object = find_connector_object(args.project_path)

    if not connector_object:
        sys.exit(1)

    if args.command.lower() == "package":
        package(args.project_path, prompt_mode, connector_object.configuration_form_method)

    if args.command.lower() == "deploy":
        ft_group = get_destination_group(args)
        ft_connection = get_connection_name(args)
        ft_deploy_key = get_api_key(args)
        validate_required_deploy_params(
            ft_group=ft_group, ft_connection=ft_connection, ft_deploy_key=ft_deploy_key
        )
        python_version = get_python_version(args, prompt_mode)
        hd_agent_id = get_hd_agent_id(args, prompt_mode)
        proxy_id = get_proxy_id(args)
        proxy_host_config_key = get_proxy_host_config_key(args)
        configuration, config_path = get_configuration(args)
        get_state(args)
        naming = get_naming(args)

        try:
            connector_object.deploy(
                args.project_path,
                ft_deploy_key,
                ft_group,
                ft_connection,
                hd_agent_id,
                configuration,
                config_path,
                python_version,
                prompt_mode,
                naming,
                proxy_id,
                proxy_host_config_key,
            )
        except Exception as e:
            print_library_log(
                f"deploy run failed with error: {str(e)}",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(1)
    elif args.command.lower() == "debug":
        configuration, config_path = get_configuration(args)
        state = get_state(args)
        naming = get_naming(args)
        try:
            os.environ["FIVETRAN_CONNECTION_ID"] = "test_connection_id"
            os.environ["FIVETRAN_DEPLOYMENT_MODEL"] = "local_debug"
            os.environ["FIVETRAN_GROUP_ID"] = "test_group_id"
            os.environ["FIVETRAN_CONNECTION_NAME"] = "test_connection_name"
            connector_object.debug(args.project_path, configuration, state, naming)
        except subprocess.CalledProcessError as e:
            print_library_log(
                f"connector tester failed with exit code: {e.returncode}",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(e.returncode)
        except Exception as e:
            print_library_log(
                f"debug run failed error: {str(e)}",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(1)
        finally:
            del os.environ["FIVETRAN_CONNECTION_ID"]
            del os.environ["FIVETRAN_DEPLOYMENT_MODEL"]
            del os.environ["FIVETRAN_GROUP_ID"]
            del os.environ["FIVETRAN_CONNECTION_NAME"]

    elif args.command.lower() == "configuration":
        try:
            connector_object.generate_configuration(
                args.project_path, run_tests=args.test, disable_encryption=args.disable_encryption
            )
        except subprocess.CalledProcessError as e:
            print_library_log(
                f"connector tester failed with exit code: {e.returncode}",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(e.returncode)
        except Exception as e:
            print_library_log(
                f"configuration command failed error: {str(e)}",
                level=Logging.Level.SEVERE,
                log_icon=Logging.LogIcon.FAILURE,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
