# Fivetran Connector SDK File Structure Overview

The files are split based on functionality. This modular design separates concerns while ensuring each file has a focused purpose - constants for configuration, helpers for utilities, logging for message output, operations for data handling, and connector functionalities:  

**__init__.py** file serves as the entry point by calling the main method and defining the Connector class provides a customer-facing interface, which contains deployment and connection management functionality (upload, create/update connections, handle tests).
- Serves as the primary entry point for the SDK
- Defines the Connector class, which is the main interface customers interact with
- Deploys the connector to the Fivetran platform. Manages the complete deployment lifecycle, including code packaging, upload, and connection configuration
- Handles setup tests and validation during deployment
- Provides debug functionality for local testing and development

**connector_helper.py** module contains all the internal methods that support the functionality of the Connector class.
- Contains internal implementation methods that support the Connector class
- Manages file operations for project packaging and deployment
- Implements connection management (create, update, cleanup)
- Provides utilities for requirements validation and version checking
- Handles the execution of the connector tester

**logger.py** implements the logging system with different severity levels
- Implements a structured logging system with multiple severity levels (FINE, INFO, WARNING, SEVERE)
- Provides formatted output for both development and production environments
- Supports colored console output for better visibility during debugging
- Handles exception logging with stack traces
- Controls log verbosity based on configuration

**operations.py** defines core data operations (upsert, update, delete, checkpoint)
- Defines the core data manipulation methods used during connector execution:
    - upsert(): Updates existing records or inserts new ones
    - update(): Modifies existing records
    - delete(): Removes records from tables
    - checkpoint(): Saves connector state for incremental syncs
- Handles data type mapping
- Implements validation checks for operation usage

**constants.py** contains all configuration constants, version numbers, and global variables
- Defines all configuration constants and system defaults
- Stores version information and compatibility requirements
- Contains platform-specific mappings (OS, architecture)
- Manages file paths, naming patterns, and validation regexes
- Houses global variables used across multiple modules

**helpers.py** provides utility functions for logging, string sanitization, and command-line interactions
- Offers utility functions for string manipulation and sanitization
- Provides naming convention helpers for database compatibility
- Implements command-line interaction utilities
- Contains validation logic for configuration and requirements
- Manages table and column name transformations
