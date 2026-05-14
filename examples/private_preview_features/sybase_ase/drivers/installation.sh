#!/bin/bash

echo '{"level":"INFO", "message": "Starting FreeTDS/ODBC installation...", "message_origin": "installation_sh"}'

# Register the bundled libtdsodbc.so (shipped in drivers/ alongside this script)
# This is the primary path — works even when apt-get is unavailable.
BUNDLED="/app/drivers/libtdsodbc.so"
if [ -f "$BUNDLED" ]; then
  cat >> /etc/odbcinst.ini << ODBCEOF

[FreeTDS]
Description=FreeTDS ODBC Driver for Sybase ASE
Driver=$BUNDLED
ODBCEOF
  echo "{\"level\":\"INFO\", \"message\": \"Registered bundled driver: $BUNDLED\", \"message_origin\": \"installation_sh\"}"
else
  echo '{"level":"WARNING", "message": "Bundled libtdsodbc.so not found — attempting apt-get install", "message_origin": "installation_sh"}'

  # Fallback: install from apt (requires network + apt in container)
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends tdsodbc unixodbc unixodbc-dev freetds-dev freetds-bin 2>/dev/null
  if [ $? -ne 0 ]; then
    echo '{"level":"ERROR", "message": "apt-get install FAILED and no bundled driver found", "message_origin": "installation_sh"}'
    exit 1
  fi

  # Locate and register the installed driver
  DRIVER_PATH=""
  for candidate in \
      /usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so \
      /usr/lib/x86_64-linux-gnu/libtdsodbc.so \
      /usr/lib/odbc/libtdsodbc.so \
      /usr/lib/libtdsodbc.so; do
    if [ -f "$candidate" ]; then
      DRIVER_PATH="$candidate"
      break
    fi
  done

  if [ -z "$DRIVER_PATH" ]; then
    echo '{"level":"ERROR", "message": "libtdsodbc.so not found after apt-get install", "message_origin": "installation_sh"}'
    exit 1
  fi

  cat >> /etc/odbcinst.ini << ODBCEOF

[FreeTDS]
Description=FreeTDS ODBC Driver for Sybase ASE
Driver=$DRIVER_PATH
ODBCEOF
  echo "{\"level\":\"INFO\", \"message\": \"Registered apt-installed driver: $DRIVER_PATH\", \"message_origin\": \"installation_sh\"}"
fi

echo '{"level":"INFO", "message": "Installation complete.", "message_origin": "installation_sh"}'
