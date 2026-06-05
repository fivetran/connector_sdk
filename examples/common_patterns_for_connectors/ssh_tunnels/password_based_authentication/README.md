# **SSH Tunnel with Password-Based Authentication**

## **Connector Overview**

This example demonstrates how to connect to an SSH server using password-based authentication with the Fivetran Connector SDK. The connector securely establishes an SSH session to a remote EC2 instance running the fivetran-api-playground server and facilitates data interaction over the SSH channel. This setup uses passwords for authentication.

## **Requirements**

* [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)   
* Operating system:
  * Windows: 10 or later (64-bit only)
  * macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  * Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)

## **Getting Started**

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/common_patterns_for_connectors/ssh_tunnels/password_based_authentication
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## **Features**

- Connects to a remote server over SSH using Python's paramiko library.
- Uses password-based authentication for secure access.
- Interact with service (e.g., fivetran-api-playground) over SSH.
- Handles connection errors and logs detailed diagnostics for troubleshooting.

## **Configuration File**

The connector requires the following configuration parameters: 

```
{
  "ssh_host": "YOUR_SSH_HOST_IP_OR_HOSTNAME",
  "ssh_user": "YOUR_SSH_USERNAME",
  "api_key": "YOUR_PLAYGROUND_API_KEY",
  "local_port": "LOCAL_PORT_TO_FORWARD",
  "remote_port": "REMOTE_PORT_OF_THE_SERVER",
  "ssh_password": "YOUR_SSH_PASSWORD"
}
```

- ssh_host: Hostname or IP address of the SSH server.
- ssh_user: Username for SSH authentication.
- api_key: API key for authenticating API requests for fivetran-api-playground.
- local_port: Local port to forward for the SSH tunnel.
- remote_port: Remote port of the server to which the tunnel connects.
- ssh_password: Password for SSH authentication.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## **Requirements File**

This connector uses the paramiko and sshtunnel libraries to establish SSH connections:
```
paramiko==3.5.1
sshtunnel==0.4.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## **Authentication**

This connector uses SSH password-based authentication:

1. The connector gets password from the configuration.
2. It connects to the EC2 instance using `sshtunnel.SSHTunnelForwarder` and `paramiko.RSAKey` for authentication.
3. Make sure the EC2 instance's security group allows inbound traffic on port 22 from the connector's environment.
4. Whitelist Fivetran IP addresses in your security group to ensure connectivity. See the [Fivetran IP Allowlist documentation](https://fivetran.com/docs/using-fivetran/ips) for details.

## **Data Handling**

The connector processes data from the SSH session as follows:
1. Establishes an SSH tunnel to the EC2 instance using sshtunnel and paramiko
2. Sends an HTTP GET request to the remote API server over the tunnel
3. Parses the JSON response from the API
4. Forwards each item in the response to the destination system using the Connector SDK’s upsert method

## **Error Handling**

The connector includes error handling for:  
- SSH authentication and connectivity issues (e.g., getting the password, establishing the SSH tunnel)
- HTTP request failures when calling the remote API over the tunnel
- Parsing errors when handling JSON responses from the API

All exceptions are logged with detailed error messages for easier debugging and monitoring.

## **Additional Considerations**

- Ensure that your EC2 instance has the appropriate IAM role or permissions to access the services it needs.
- If your server uses a jump host or bastion, additional SSH tunneling logic may be needed.
- For production environments, avoid hardcoding sensitive paths or credentials.

The examples provided are meant to help you get started with Fivetran's Connector SDK. While the connector has been tested, Fivetran is not responsible for any issues resulting from its use. For support, contact the Fivetran Support team.