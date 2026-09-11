# Changelog

This changelog lists PyPI package releases for the `fivetran-connector-sdk` package, as published in the official [Fivetran Connector SDK release notes](https://fivetran.com/docs/connector-sdk/changelog).

## September 2026

### fivetran-connector-sdk `2.12.1`

- Updates the `grpcio` and `grpcio-tools` dependency versions to 1.80.0.

### fivetran-connector-sdk `2.12.0`

- `fivetran debug` now generates a crash report when your connector code fails, capturing the exception, handler, configuration, and SDK version to help diagnose the failure.
- Memory usage logging now reports the memory consumed by your connector code.
- Improved CLI log output. `fivetran debug` now aligns log levels and sources and drops the date, while other CLI commands print concise messages.
- The local connector tester binary downloaded by `fivetran debug` is now cached in `.fivetran/connector_sdk/tester` in your home directory, replacing the previous `.ft_sdk_connector_tester` folder.
- Dependency validation is now added to non-interactive flows, previously it was skipped.
- `fivetran init --template` now supports nested prefix search under `examples/`.
- Minor enhancements and improvements.
- Updated testers.

## August 2026

### fivetran-connector-sdk `2.11.0`

- Adds support for errors and warnings.
- Introduces the `--yes` flag and updates other non-interactive flags for better clarity and user experience.
- Adds resolution precedence for required flags and provides the `configuration.json` path.
- Updates the new connection creation and debug flows to require configuration.json. For more information, see the configuration resolution order.
- Updated `fivetran init` and AI plugin setup behavior for existing projects.
- Minor enhancements and improvements.
- Updated testers.

## July 2026

### fivetran-connector-sdk `2.10.4`

- Changes the default Python version to 3.14. Existing connections continue with their current version.
- Improved security of the local debug server.
- Added support for Windows ARM64 in the cSDK CLI.
- Minor enhancements and improvements.
- Updated testers.

### fivetran-connector-sdk `2.10.3`

- Adds the configuration command to run the connector's configuration form with interactive prompting support and create `configuration.json` locally from the provided input. Supports an additional `--test` flag to run connector tests locally.
- Improved configuration form UI rendering performance.
- Updated testers to support the updates.

### fivetran-connector-sdk `2.10.2`

- Added validation for unique field names within a table.
- Improved `fivetran init` behavior.
- Improved error detection for connector object issues in the tester.

### fivetran-connector-sdk `2.10.1`

- Supersedes the yanked `2.10.0` release.
- Fixed an issue with downloading the stable updated testers.
- Added validation for empty table names.
- Improved logging for agent plugins.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.10.0` (Yanked: Tester Version Mismatch)

- Added validation for empty table names.
- Improved logging for agent plugins.
- Minor enhancements and improvements.
- Updated testers.

## June 2026

### fivetran-connector-sdk `2.9.2`

- The fivetran debug command now logs peak memory usage at the end of a debug run.
- Added validation during `fivetran init`.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.9.1`

- `fivetran init` now supports Copilot plugins allowing users to leverage AI capabilities for faster and more efficient connector development.
- We've deprecated the `--force` and `-f` flags and introduced a new `--non-interactive` flag for better clarity and user experience.
- Updated the CLI to point to renamed repositories.
- Minor enhancements and improvements.
- Updated testers.

### fivetran-connector-sdk `2.9.0`

- Updated the `fivetran init` command to install the `fivetran-connector-sdk@fivetran-connector-sdk-ai` plugin, which provides AI-powered features for connector development.
- Improved prompts for dependency validations during package and deploy commands.
- Minor enhancements and improvements.
- Updated testers.

## May 2026

### fivetran-connector-sdk `2.8.3`

- Adds support for `pyproject.toml` dependency validation.
- Introduces a new `truncate()` operation that soft-deletes all previously synced rows in a table by setting `_fivetran_deleted = TRUE`, without physically removing the rows or altering the table structure. This is useful when your connector needs to replace all existing data in a table with a fresh set of records.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.8.2`

- Introduced support for Python-native log levels: DEBUG, ERROR, and CRITICAL.
- INFO and WARNING are already supported and work the same across both Python and Java-style levels.
- We recommend using Python-native log levels in all new connector code.
- The Java-style levels FINE and SEVERE are now deprecated. Use `log.debug()` in place of `log.fine()`, and `log.error()` or `log.critical()` in place of `log.severe()`.
- Existing connectors using Java-style levels continue to work without any modification.
- Minor enhancements and improvements.
- For more information, see our Connector SDK Logging Reference.

## April 2026

### fivetran-connector-sdk `2.8.1`

- We now support pyproject.toml as an alternative to `requirements.txt` for defining dependencies in your connector project. See Managing Project Dependencies for details.
- Improved overall performance and stability.
- `.ftignore` has been replaced by `.gitignore`. You can now create a `.gitignore` file in the root of your connector project to specify files and directories that should be excluded during `fivetran deploy` and `fivetran package`. If you have an existing `.ftignore` file, rename it to `.gitignore` because the package no longer reads `.ftignore`.
- We now allow and support all file types to be uploaded during deployment.
- Improved user experience for memory utilisation in testers and enhanced logging.
- Improved testers with bug fixes for transactional checkpointing.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.8.0`

- Improved overall performance and stability.
- Better user experience with enhanced logging.
- Updated testers that now support Transactional Checkpoint.
- Minor enhancements and improvements.

## March 2026

### fivetran-connector-sdk `2.7.2`

- Security fixes for vulnerabilities in requests package.
- Improved overall performance and stability.
- Minor enhancements and improvements.
- Updated testers.

### fivetran-connector-sdk `2.7.1`

- Improved logging for `fivetran debug` and `fivetran reset`
- Minor enhancements and improvements.
- Updated tester - fixed vulnerabilities and logging.

### fivetran-connector-sdk `2.7.0`

- Changes the default Python version to 3.13 since the Performance Profiling feature uses py-spy, which is not supported by Python versions > 3.13. You can still change the runtime Python version to 3.14 by using `--python-version` argument passed to `fivetran deploy` command or directly from the setup form after deployment.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.6.2`

- A new help command for the PyPI package that provides users with additional information about the package and its usage.
- Improved error handling and logging.
- Better handling of conflicting packages.
- Minor enhancements and improvements.

## February 2026

### fivetran-connector-sdk `2.6.1`

- Minor enhancements and improvements.

## January 2026

### fivetran-connector-sdk `2.6.0`

- Security fixes for vulnerabilities in grpcio and pipreqs-fivetran
- Improved PyPI package logging
- Enhanced package management.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.5.1`

- New deployment strategy for Connector SDK connections.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.5.0`

- Updated testers to use DuckDB version 1.4.2
- Minor enhancements and improvements.

## December 2025

### fivetran-connector-sdk `2.4.2`

- Increased gRPC maximum inbound message size from 32MB to 128MB to support larger operations.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.4.1`

- Logging improvements for better user experience.
- Minor enhancements and improvements.
- Updated tester - improved debugger performance.

### fivetran-connector-sdk `2.4.0`

- Minor enhancements and improvements.

## November 2025

### fivetran-connector-sdk `2.3.5`

- The `fivetran init` command, which you can use to initialize your project quickly. It includes the option to configure the Fivetran Connector SDK context for your AI agent of choice.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.3.4`

- Adds support for Python version 3.14. All new connections default to Python 3.14 unless the version is specified with the `--python-version` or `--python` argument at the deploy time.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.3.3`

- `.ftignore` support for Connector SDK. You can now create a `.ftignore` file in the root of your connector project to specify files and directories that should be excluded during `fivetran deploy`. The syntax of the `.ftignore` file is similar to that of a `.gitignore` file.
- Two new environment variables, FIVETRAN_GROUP_ID and FIVETRAN_CONNECTION_NAME, which can be referenced from connector code.
- Minor enhancements and improvements.

### fivetran-connector-sdk `2.3.2`

- Deprecation of Python v3.9
- Minor enhancements and improvements

## October 2025

### fivetran-connector-sdk `2.3.1`

- Previously, list objects required an explicit type definition within the schema() method. This release removes that limitation. Now, we automatically infer the list type values to JSON.
- Minor improvements and enhancements.

### fivetran-connector-sdk `2.3.0`

- Timeout handling for connector operations.
- Minor improvements and enhancements.

## September 2025

### fivetran-connector-sdk `2.2.1`

- Two new environment variables, FIVETRAN_CONNECTION_ID and FIVETRAN_DEPLOYMENT_MODEL, which can be referenced from connector code.
- Minor improvements and enhancements.
- Updated testers.

### fivetran-connector-sdk `2.2.0`

- Fix in inference for boolean data type, to identify as boolean and not int.
- Minor improvements and enhancements.

### fivetran-connector-sdk `2.1.1`

- Adds support for Python version 3.13. All new connections default to Python 3.13 unless the version is specified with the `--python-version` or `--python` argument at the deploy time.

### fivetran-connector-sdk `2.1.0`

- Support for using pipreqs-fivetran to generate requirements.txt
- Minor fixes and improvements

### fivetran-connector-sdk `2.0.2`

- Improved logging
- Updated tester performance
- Minor fixes and improvements

## August 2025

### fivetran-connector-sdk `2.0.1`

- Minor improvements and enhancements.

### fivetran-connector-sdk `2.0.0`

- Operations like op.upsert() no longer require the use of yield in your connector code.

  Previously, operations had to be yielded like this:

  ```
  yield op.upsert(table="table_name", data=data)
  ```

  Now, you can call them directly without yield:

  ```
  op.upsert( table="table_name", data=data)
  ```

  This simplifies connector logic and improves code readability. See our Migration Guide to learn how to remove yield usages from your connector code.

- Performance improvements and internal design enhancements.

### fivetran-connector-sdk `1.8.1`

- Minor improvements and enhancements.

### fivetran-connector-sdk `1.8.0`

- Internal design and performance improvements.
- Updated tester.

## July 2025

### fivetran-connector-sdk `1.7.5`

- Internal enhancements and design improvements.

### fivetran-connector-sdk `1.7.4`

- Internal enhancements and improvements.

### fivetran-connector-sdk `1.7.3`

- Internal enhancements and design improvements.

### fivetran-connector-sdk `1.7.2`

- Bug fix for `requirements.txt` validation.
- Minor improvements and enhancements.

### fivetran-connector-sdk `1.7.1`

- Internal enhancements and design improvements.
- Updated tester.

### fivetran-connector-sdk `1.7.0`

- Deploy flow improvements.
- Support for new environment variables.
- Upgraded requests library dependency to 2.32.4.
- Minor bug fixes and improvements.

## June 2025

### fivetran-connector-sdk `1.6.0`

- Minor bug fixes and improvements.
- Improved logging.

### fivetran-connector-sdk `1.5.1`

- Important fix around timestamp parsing and formatting.

### fivetran-connector-sdk `1.5.0`

- Environment variable naming improvements.
- Improvements to the `--force` argument and reset command.
- Performance improvements.
- Usage of latest versions for dependent libraries.
- Improved logging.
- Minor improvements and bug fixes.

## May 2025

### fivetran-connector-sdk `1.4.6`

- Support for special and escaped characters in debug.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.4.5`

- Support for arm64 architecture on Linux and MacOS.
- Minor improvements and bug fixes.
- Updated tester.

### fivetran-connector-sdk `1.4.4`

- Improved arguments for the `--python-version` CLI command that specifies the Python version to be used at runtime. Now you need to pass the Python version as 3.12, 3.11, 3.10 or 3.9 instead of 3.12.x, 3.11.x, 3.10.x or 3.9.x.
- Improved logging.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.4.3`

- As part of the existing `--force (-f)` flag, we've added the option to bypass the required dependencies check. This enhancement allows you to skip the validation process and use the `requirements.txt` file you provide.
- We no longer block you if you reply No to any of the existing prompts. The Connector SDK execution will continue without interruption.
- Minor improvements and bug fixes.
- Updated tester.

### fivetran-connector-sdk `1.4.2`

- Minor improvements to requirements.txt validations.
- Updated tester.

### fivetran-connector-sdk `1.4.0`

- Support for colored output in the command line for errors and warnings.
- A fix to skip validation of `requirements.txt` due to connection errors with PyPI.
- Minor improvements and bug fixes.

## April 2025

### fivetran-connector-sdk `1.3.4`

- Support for Hybrid Deployment.
- An additional parameter for Hybrid Deployment.
- Updated tester.

### fivetran-connector-sdk `1.3.3`

- A bug fix for error logging when using exit().
- Improvements to the data type inference for unknown types.
- Updated tester.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.3.2`

- A bug fix for reading the correct state value when using the fivetran debug command.
- Improved error logging when using `exit()` in `connector.py`.
- Improved data type inference for unknown types.
- Updated tester.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.3.1`

- Optimized performance by eliminating redundant method calls.
- Updated tester.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.3.0`

- Improved logging messages.
- Updated tester.
- Minor improvements and bug fixes.

## March 2025

### fivetran-connector-sdk `1.2.1`

- Minor improvements and bug fixes.
- Improved prompting of parameters for the `fivetran deploy` command.

### fivetran-connector-sdk `1.2.0`

- Minor improvements and bug fixes.
- Prevent uploading of Python virtual environment files to Fivetran.

## February 2025

### fivetran-connector-sdk `1.1.4`

- Enhancements around prompts for `requirements.txt` verification.
- Minor improvements and bug fixes.
- Updated testers.
- Enhanced logging capabilities.

### fivetran-connector-sdk `1.1.2`

- Enhancements and minor bug fixes around `requirements.txt` verification.
- Minor improvements and bug fixes.

### fivetran-connector-sdk `1.0.0`

- Contains some improvements and bug fixes.

## January 2025

### fivetran-connector-sdk `0.13.30.1`

- Enhancements and minor bug fixes around logging and improved error messages.
- Updated testers.
- Minor bug fixes.

### fivetran-connector-sdk `0.13.22.1`

- Support for multiple Python versions.
- Enhancements and minor bug fixes around logging and `requirements.txt` verification.
- Enhanced prompts to overwrite configurations.
- Minor bug fixes.

### fivetran-connector-sdk `0.13.16.2`

- Minor bug fixes.
- Enhanced logging and removal of unwanted warnings.

### fivetran-connector-sdk `0.13.10.1`

- A user confirmation prompt to automatically update faulty requirements.txt files.
- Added support for installing packages directly from Git sources via requirements.txt.
- Enhanced logging and exception handling for improved debugging and reliability.

## December 2024

### fivetran-connector-sdk `0.12.17.1`

- Contains some minor improvements.

### fivetran-connector-sdk `0.12.12.1`

- Updated testers for the fivetran debug command with better-formatted logs.
- An error message when attempting to deploy a connector with more than 100 configuration fields.
- Automatic handling of port conflicts on your local machine.

## November 2024

### fivetran-connector-sdk `0.11.21.1`

- We now show the `connector_id` in the success message of the `fivetran deploy` command.

### fivetran-connector-sdk `0.11.14.1`

- Support for Python version 3.12.
- Adds a `--force` flag to the `fivetran deploy` command, which bypasses the connector existence check.

## October 2024

### fivetran-connector-sdk `0.10.24.1`

- Provides improved error logging and updated testers for `fivetran debug`.
