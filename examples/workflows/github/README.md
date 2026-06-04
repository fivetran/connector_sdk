# Deploy Hello Connector GitHub Workflow

This repository contains a GitHub Actions workflow to deploy a Fivetran Connector when changes are pushed to the `master` branch in the `hello/` directory.

## Workflow Overview

This workflow automates the deployment process for the Hello Connector using Fivetran. It:
- Runs on pushes to the `master` branch if changes occur in the `hello/` directory.
- Uses GitHub environment variables and secrets for secure configuration management.
- Sets up Python and installs required dependencies.
- Creates a configuration file using GitHub Secrets.
- Deploys the Fivetran connector using the `fivetran-connector-sdk`.

## Prerequisites

Before using this workflow, ensure you have:
1. **GitHub Environment Variables**
   - Define plaintext variables in a GitHub environment called `Fivetran`.
   - These variables are referenced in the workflow by prefixing the variable name with `vars.`
   - Examples:
     - `FIVETRAN_DEV_DESTINATION`: The name of an existing Fivetran destination.
     - `HELLO_DEV`: The name of the Fivetran connector to deploy.

2. **GitHub Secrets**
   - Store sensitive credentials securely in GitHub Secrets.
   - They should be named so that you can identify them later because they can't be viewed after storing.
   - These are referenced in the workflow by prefixing the variable name with `secrets.`
   - Examples:
     - `FIVETRAN_API_KEY`: API key for Fivetran authentication.
     - `HELLO_CLIENT_ID`: Client ID for authentication.
     - `HELLO_CLIENT_SECRET`: Client Secret for authentication.

## Workflow Steps

### 1. Triggering the Workflow
- The workflow runs when code is pushed to the `master` branch.
- Only changes inside the `hello/` directory trigger the workflow.

### 2. Job: `deploy-fivetran-connector`

#### **Step 1: Checkout Repository**
- Clones the repository to the runner environment.

#### **Step 2: Set up Python**
- Installs Python 3.11 for compatibility with Fivetran SDK.  
You can use any [supported version of Python](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements), but it’s preferable to keep it consistent with the version used in the `fivetran deploy` command (if provided) to avoid potential mismatches.

#### **Step 3: Change Directory & List Files**
- Moves into the `hello/` directory.
- Lists files for debugging purposes.

#### **Step 4: Install Dependencies**
- Upgrades `pip` and installs `fivetran-connector-sdk`.

#### **Step 5: Install `requirements.txt` (if present)**
- Installs required dependencies while avoiding duplicate installations of `requests`.

#### **Step 6: Create Configuration File**
- Generates `configuration.json` using GitHub Secrets.
- Any parameters like `initialSyncStart` that aren't secret can be supplied in plaintext here.
- Contains:
  ```json
  {
    "clientId": "<HELLO_CLIENT_ID>",
    "clientSecret": "<HELLO_CLIENT_SECRET>",
    "initialSyncStart": "2024-01-01T00:00:00.000Z"
  }
  ```

#### **Step 7: Deploy Fivetran Connector**
- Uses environment variables for deployment.
- Runs the `fivetran deploy` command with required parameters, including configuration file created in an earlier step.
- A supported Python version must be specified; defaults to 3.13 if not provided.

## How to Use

1. **Set up GitHub Secrets** as described in the prerequisites.
2. Save hello.yml to `.github/workflows` in your repo. Each YAML file inside `.github/workflows/` defines a workflow that GitHub Actions will recognize and execute based on the triggers you define in the file.
3. **Push changes to the `hello/` directory on the `master` branch`**.
4. **Monitor GitHub Actions logs** to track deployment progress.

## Debugging
- Ensure all required secrets and variables are properly set up.
- Check GitHub Actions logs for errors.
- Confirm `fivetran-connector-sdk` is installed correctly.

## Notes
- Secrets are used for sensitive information and should not be hardcoded.
- Plaintext environment variables are used for non-sensitive deployment settings.
