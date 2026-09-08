# Changelog

This changelog lists PyPI package releases for the `fivetran-connector-sdk` and `fivetran-api-playground` packages, as published in the official [Fivetran Connector SDK release notes](https://fivetran.com/docs/connector-sdk/changelog).

## August 2026

### fivetran-connector-sdk PyPI package

We have released version `2.11.0` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Adds support for errors and warnings.
- Introduces the `--yes` flag and updates other non-interactive flags for better clarity and user experience.
- Adds resolution precedence for required flags and providing the configuration.json path.
- Updates the new connection creation and debug flows to require configuration.json. For more information, see configuration resolution order.
- Updated fivetran init and AI plugin setup behavior for existing projects.
- Minor enhancements and improvements.
- Updated testers.

### fivetran-api-playground PyPI package

We have released version `1.1.9` of the fivetran-api-playground PyPI package. This release upgrades the faker library dependency to 40.36.0.

## July 2026

### fivetran-connector-sdk PyPI package

We have released version `2.10.4` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Changes the default Python version to 3.14. Existing connections continue with their current version.
- Improved security of the local debug server.
- Added support for Windows ARM64 in the cSDK CLI.
- Minor enhancements and improvements.
- Updated testers.

We have released version `2.10.3` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Adds the configuration command to run the connector's configuration form with interactive prompting support and create configuration.json locally from the provided input. Supports an additional `--test` flag to run connector tests locally.
- Improved configuration form UI rendering performance.
- Updated testers to support the updates.

We have released version `2.10.2` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Added validation for unique field names within a table.
- Improved fivetran init behavior.
- Improved error detection for connector object issues in the tester.

We have released version `2.10.1` of the fivetran-connector-sdk PyPI package. This release supersedes the yanked `2.10.0` release and includes the following updates:

- Fixed an issue with downloading the stable updated testers.
- Added validation for empty table names.
- Improved logging for agent plugins.
- Minor enhancements and improvements.

**(Yanked: Tester Version Mismatch)** We have released version `2.10.0` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Added validation for empty table names.
- Improved logging for agent plugins.
- Minor enhancements and improvements.
- Updated testers.

### fivetran-api-playground PyPI package

We have released version `1.1.8` of the fivetran-api-playground PyPI package. This release adds the following:

- Upgrades the requests library dependency to 2.34.2.
- Upgrades the faker library dependency to 40.23.0.

## June 2026

### fivetran-connector-sdk PyPI package

We have released version `2.9.2` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- The fivetran debug command now logs peak memory usage at the end of a debug run.
- Added validation during fivetran init.
- Minor enhancements and improvements.

We have released version `2.9.1` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- fivetran init now supports Copilot plugins allowing users to leverage AI capabilities for faster and more efficient connector development.
- We've deprecated the `--force` and `-f` flags and introduced a new `--non-interactive` flag for better clarity and user experience.
- Updated the CLI to point to renamed repositories.
- Minor enhancements and improvements.
- Updated testers.

We have released version `2.9.0` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Updated fivetran init command to install fivetran-connector-sdk@fivetran-connector-sdk-ai plugin, which provides AI-powered features for connector development.
- Improved prompts for dependency validations during package and deploy commands.
- Minor enhancements and improvements.
- Updated testers.

## May 2026

### fivetran-connector-sdk PyPI package

We have released version `2.8.3` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Adds support for pyproject.toml dependency validation.
- Introduces a new truncate() operation that soft deletes all previously synced rows in a table by setting `_fivetran_deleted = TRUE`, without physically removing the rows or altering the table structure. This is useful when your connector needs to replace all existing data in a table with a fresh set of records.
- Minor enhancements and improvements.

We have released version `2.8.2` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Introduced support for Python-native log levels: DEBUG, ERROR, and CRITICAL.
- INFO and WARNING are already supported and work the same across both Python and Java-style levels.
- We recommend using Python-native log levels in all new connector code.
- The Java-style levels FINE and SEVERE are now deprecated. Use log.debug() in place of log.fine(), and log.error() or log.critical() in place of log.severe().
- Existing connectors using Java-style levels continue to work without any modification.
- Minor enhancements and improvements.
- For more information, see our Connector SDK Logging Reference.

### fivetran-api-playground PyPI package

We have released version `1.1.6` of the fivetran-api-playground PyPI package. This release adds the following:

- Adds rate limiting support via the `--rate-limit` flag to simulate real-world HTTP 429 Too Many Requests responses.
- Adds `--capacity` flag to configure the maximum burst size of the token bucket.
- Adds X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset headers to all responses when rate limiting is enabled.
- Adds Retry-After header to HTTP 429 responses indicating when the next request can be made.

We have released version `1.1.7` of the fivetran-api-playground PyPI package. This release adds the following:

- Upgrades the faker library dependency to 40.15.0.

## April 2026

### fivetran-connector-sdk PyPI package

We have released version `2.8.1` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- We now support pyproject.toml as an alternative to requirements.txt for defining dependencies in your connector project. Please refer to Managing Project Dependencies for more details.
- Improved overall performance and stability.
- .ftignore has been replaced by .gitignore. You can now create a .gitignore file in the root of your connector project to specify files and directories that should be excluded during fivetran deploy and fivetran package. If you have an existing .ftignore file, rename it to .gitignore because the package no longer reads .ftignore.
- We now allow and support all file types to be uploaded during deployment.
- Improved user experience for memory utilisation in testers and enhanced logging.
- Improved testers with bug fixes for transactional checkpointing.
- Minor enhancements and improvements.

We have released version `2.8.0` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Improved overall performance and stability.
- Better user experience with enhanced logging.
- Updated testers that now support Transactional Checkpoint.
- Minor enhancements and improvements.

## March 2026

### fivetran-connector-sdk PyPI package

We have released version `2.7.2` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Security fixes for vulnerabilities in requests package.
- Improved overall performance and stability.
- Minor enhancements and improvements.
- Updated testers.

We have released version `2.7.1` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Improved logging for fivetran debug and fivetran reset
- Minor enhancements and improvements.
- Updated tester - fixed vulnerabilities and logging.

We have released version `2.7.0` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- Changes the default Python version to 3.13 since the Performance Profiling feature uses py-spy, which is not supported by Python versions > 3.13. You can still change the runtime Python version to 3.14 by using `--python-version` argument passed to fivetran deploy command or directly from the setup form after deployment.
- Minor enhancements and improvements.

We have released version `2.6.2` of the fivetran-connector-sdk PyPI package. This release includes the following updates:

- A new help command for the PyPI package that provides users with additional information about the package and its usage.
- Improved error handling and logging.
- Better handling of conflicting packages.
- Minor enhancements and improvements.

### fivetran-api-playground PyPI package

We have released version `1.1.4` of the fivetran-api-playground PyPI package. This release adds the following:

- Upgrades the flask library dependency to 3.1.3 .
- Upgrades the faker library dependency to 40.4.0 .
- Upgrades the colorama library dependency to 0.4.6 .

We have released version `1.1.5` of the fivetran-api-playground PyPI package. This release adds support for session token expirations. Session tokens now expire after 1 hour, and the login endpoint returns an expires_in field indicating the token's validity period.

## February 2026

### fivetran-connector-sdk PyPI package

We have released version `2.6.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor enhancements and improvements.

## January 2026

### fivetran-connector-sdk PyPI package

We have released version `2.6.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Security fixes for vulnerabilities in grpcio and pipreqs-fivetran
- Improved PyPI package logging
- Enhanced package management.
- Minor enhancements and improvements.

We have released version `2.5.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- New deployment strategy for Connector SDK connections.
- Minor enhancements and improvements.

We have released version `2.5.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Updated testers to use DuckDB version 1.4.2
- Minor enhancements and improvements.

## December 2025

### fivetran-connector-sdk PyPI package

We have released version `2.4.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Increased gRPC maximum inbound message size from 32MB to 128MB to support larger operations.
- Minor enhancements and improvements.

We have released version `2.4.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Logging improvements for better user experience.
- Minor enhancements and improvements.
- Updated tester - improved debugger performance.

### fivetran-connector-sdk PyPI package

We have released version `2.4.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor enhancements and improvements.

### fivetran-api-playground PyPI package

We have released version `1.1.2` of the fivetran-api-playground PyPI package. This release adds the following:

- Minor improvements and bug fixes.
- Updated dependencies.

We have released version `1.1.3` of the fivetran-api-playground PyPI package. This release adds the following:

- Upgrades the flask library dependency to 3.1.2.
- Upgrades the faker library dependency to 38.2.0.

## November 2025

### fivetran-connector-sdk PyPI package

We have released version `2.3.5` of the fivetran-connector-sdk PyPI package. This release adds the following:

- The fivetran init command, which you can use to initialize your project quickly. It includes the option to configure Fivetran Connector SDK context for your AI agent of choice.
- Minor enhancements and improvements.

We have released version `2.3.4` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Adds support for Python version 3.14. All new connections default to Python 3.14 unless the version is specified with the `--python-version` or --python argument at the deploy time.
- Minor enhancements and improvements.

We have released version `2.3.3` of the fivetran-connector-sdk PyPI package. This release adds the following:

- .ftignore support for Connector SDK. You can now create a .ftignore file in the root of your connector project to specify files and directories that should be excluded during fivetran_deploy. The syntax of the .ftignore file is similar to that of a .gitignore file.
- Two new environment variables, FIVETRAN_GROUP_ID and FIVETRAN_CONNECTION_NAME, which can be referenced from connector code.
- Minor enhancements and improvements.

We have released version `2.3.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Deprecation of Python v3.9
- Minor enhancements and improvements

## October 2025

### fivetran-connector-sdk PyPI package

We have released version `2.3.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Previously, list objects required an explicit type definition within the schema() method. This release removes that limitation. Now, we automatically infer the list type values to JSON.
- Minor improvements and enhancements.

We have released version `2.3.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Timeout handling for connector operations.
- Minor improvements and enhancements.

## September 2025

### fivetran-connector-sdk PyPI package

We have released version `2.2.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Two new environment variables, FIVETRAN_CONNECTION_ID and FIVETRAN_DEPLOYMENT_MODEL, which can be referenced from connector code.
- Minor improvements and enhancements.
- Updated testers.

We have released version `2.2.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Fix in inference for boolean data type, to identify as boolean and not int.
- Minor improvements and enhancements.

We have released version `2.1.1` of the fivetran-connector-sdk PyPI package. This release adds support for Python version 3.13. All new connections default to Python 3.13 unless the version is specified with the `--python-version` or --python argument at the deploy time.

We have released version `2.1.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for using pipreqs-fivetran to generate requirements.txt
- Minor fixes and improvements

We have released version `2.0.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Improved logging
- Updated tester performance
- Minor fixes and improvements

## August 2025

### fivetran-connector-sdk PyPI package

We have released version `2.0.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor improvements and enhancements.

We have released version `2.0.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

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

We have released version `1.8.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor improvements and enhancements.

We have released version `1.8.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Internal design and performance improvements.
- Updated tester.

### fivetran-api-playground PyPI package

We have released version `1.1.1` of the fivetran-api-playground PyPI package. This release adds the following:

- Added two new cursor endpoints for retrieving user data for multiple sync strategies:
  - /incremental/timestamp - Get a list of user data which was updated since the timestamp in params.
  - /incremental/step - Get a list of users within a start and end parameter.

We have released version `1.1.0` of the fivetran-api-playground PyPI package. This release adds the following:

- Added two new cursor endpoints for retrieving company and department data:
  - /cursors/companies - Get a list of companies with filtering options.
  - /cursors/<company_id>/departments - Get department details for a specific company with filtering options.

## July 2025

### fivetran-connector-sdk PyPI package

We have released version `1.7.5` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Internal enhancements and design improvements.

We have released version `1.7.4` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Internal enhancements and improvements.

We have released version `1.7.3` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Internal enhancements and design improvements.

We have released version `1.7.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Bugfix for requirements.txt validation.
- Minor improvements and enhancements.

We have released version `1.7.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Internal enhancements and design improvements.
- Updated tester.

We have released version `1.7.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Deploy flow improvements.
- Support for new environment variables.
- Upgraded requests library dependency to 2.32.4.
- Minor bug fixes and improvements.

## June 2025

### fivetran-connector-sdk PyPI package

We have released version `1.6.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor bug fixes and improvements.
- Improved logging.

We have released version `1.5.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Important fix around timestamp parsing and formatting.

We have released version `1.5.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Environment variable naming improvements.
- Improvements to the `--force` argument and reset command.
- Performance improvements.
- Usage of latest versions for dependent libraries.
- Improved logging.
- Minor improvements and bug fixes.

### fivetran-api-playground PyPI package

We have released version `1.0.0` of the fivetran-api-playground PyPI package. This release adds the following:

- Minor improvements and bug fixes.
- Updated dependencies.

## May 2025

### fivetran-connector-sdk PyPI package

We have released version `1.4.6` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for special and escaped characters in debug.
- Minor improvements and bug fixes.

We have released version `1.4.5` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for arm64 architecture on Linux and MacOS.
- Minor improvements and bug fixes.
- Updated tester.

We have released version `1.4.4` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Improved arguments for the `--python-version` CLI command that specifies the Python version to be used at runtime. Now you need to pass the Python version as 3.12, 3.11, 3.10 or 3.9 instead of 3.12.x, 3.11.x, 3.10.x or 3.9.x.
- Improved logging.
- Minor improvements and bug fixes.

We have released version `1.4.3` of the fivetran-connector-sdk PyPI package. This release adds the following:

- As part of the existing `--force (-f)` flag, we've added the option to bypass the required dependencies check. This enhancement allows you to skip the validation process and use the requirements.txt file you provide.
- We no longer block you if you reply No to any of the existing prompts. The Connector SDK execution will continue without interruption.
- Minor improvements and bug fixes.
- Updated tester.

We have released version `1.4.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor improvements in requirements.txt validations.
- Updated tester.

We have released version `1.4.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for colored output in the command line for errors and warnings.
- A fix to skip validation of requirements.txt due to connection errors with PyPI.
- Minor improvements and bug fixes.

## April 2025

### fivetran-connector-sdk PyPI package

We have released version `1.3.4` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for Hybrid Deployment.
- An additional parameter for Hybrid Deployment.
- Updated tester.

We have released version `1.3.3` of the fivetran-connector-sdk PyPI package. This release adds the following:

- A bug fix around error logging when using exit().
- Improvements to the data type inference for unknown types.
- Updated tester.
- Minor improvements and bug fixes.

We have released version `1.3.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- A bug fix for reading the correct state value when using the fivetran debug command.
- Improved error logging when using exit() in connector.py.
- Improved data type inference for unknown types.
- Updated tester.
- Minor improvements and bug fixes.

We have released version `1.3.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Optimized performance by eliminating redundant method calls.
- Updated tester.
- Minor improvements and bug fixes.

We have released version `1.3.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Improved logging messages.
- Updated tester.
- Minor improvements and bug fixes.

## March 2025

### fivetran-connector-sdk PyPI package

We have released version `1.2.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor improvements and bug fixes.
- Improved prompting of parameters for the fivetran deploy command.

We have released version `1.2.0` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor improvements and bug fixes.
- Prevent uploading of Python virtual environment files to Fivetran.

## February 2025

### fivetran-connector-sdk PyPI package

We have released version `1.1.4` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Enhancements around prompts for requirements.txt verification.
- Minor improvements and bug fixes.
- Updated testers.
- Enhanced logging capabilities.

We have released version `1.1.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Enhancements and minor bug fixes around requirements.txt verification.
- Minor improvements and bug fixes.

We have released version `1.0.0` of the fivetran-connector-sdk PyPI package. This release contains some improvements and bug fixes.

## January 2025

### fivetran-connector-sdk PyPI package

We have released version `0.13.30.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Enhancements and minor bug fixes around logging and improved error messages.
- Updated testers.
- Minor bug fixes.

We have released version `0.13.22.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for multiple Python versions.
- Enhancements and minor bug fixes around logging and requirements.txt verification.
- Enhanced prompts to overwrite configurations.
- Minor bug fixes.

We have released version `0.13.16.2` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Minor bug fixes.
- Enhanced logging and removal of unwanted warnings.

We have released version `0.13.10.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- A user confirmation prompt to automatically update faulty requirements.txt files.
- Added support for installing packages directly from Git sources via requirements.txt.
- Enhanced logging and exception handling for improved debugging and reliability.

## December 2024

### fivetran-connector-sdk PyPI package

We have released version `0.12.17.1` of the PyPI package. This release contains some minor improvements.

We have released version `0.12.12.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Updated testers for the fivetran debug command with better-formatted logs.
- An error message when attempting to deploy a connector with more than 100 configuration fields.
- Automatic handling of port conflicts on your local machine.

### fivetran-api-playground PyPI package

We have released version `0.12.12.1` of the fivetran-api-playground PyPI package. This release adds the following:

- Export CSV endpoint for testing export APIs.
- Authentication endpoints for testing the following types of authentication:
  - HTTP basic
  - HTTP bearer
  - API key
  - Session token

## November 2024

### fivetran-connector-sdk PyPI package

We have released version `0.11.21.1` of the fivetran-connector-sdk PyPI package. We now show the connector_id in the success message of the fivetran deploy command.

We have released version `0.11.14.1` of the fivetran-connector-sdk PyPI package. This release adds the following:

- Support for Python version 3.12.
- Adds a `--force` flag to fivetran deploy command which bypasses the connector exists check.

### fivetran-api-playground PyPI package

We have released version `0.11.21.1` of the fivetran-api-playground PyPI package. This release adds changelog section to our PyPI package.

We have released version `0.11.14.1` of the fivetran-api-playground PyPI package. This release adds support for Python version 3.12.

## October 2024

### fivetran-connector-sdk PyPI package

We have released version `0.10.24.1` of the fivetran-connector-sdk PyPI package. This release provides improved error logging and updated testers for fivetran debug.
