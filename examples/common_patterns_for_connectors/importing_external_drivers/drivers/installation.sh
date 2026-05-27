#!/bin/bash

# Script to install python3-dev, default-libmysqlclient-dev, build-essential on Debian/Ubuntu systems.

# Detect OS
OS=$(uname -s)
# DISTRO=$(awk -F= '$1=="NAME" {print $2}' /etc/os-release | tr -d '"')

echo '{"level":"INFO", "message": "Detected OS: '$OS'", "message-origin": "installation_sh"}'

# Update package lists
update_packages() {
  if [[ "$OS" == "Linux" ]]; then
      apt-get update
  else
    echo '{"level":"INFO", "message": "Unsupported OS.", "message-origin": "installation_sh"}'
    exit 1
  fi
}

# Install MySqldb dependencies for header files -> default-libmysqlclient-dev
# python3-dev and build-essential are already present in the production base image
install_libmysqlclients() {
  if [[ "$OS" == "Linux" ]]; then
    apt-get install -y default-libmysqlclient-dev
  else
    echo '{"level":"INFO", "message": "Unsupported OS.", "message-origin": "installation_sh"}'
    exit 1
  fi
}

# Main execution
update_packages
install_libmysqlclients

echo '{"level":"INFO", "message": "default-libmysqlclient-dev installations complete.", "message-origin": "installation_sh"}'