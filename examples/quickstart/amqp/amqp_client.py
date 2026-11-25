"""Connects to an AMQP 1.0 broker over TLS and opens a queue receiver, used by connector.py."""

# For decoding base64-encoded client certificates and keys
import base64

# For validating the host and checking the addresses it resolves to
import ipaddress
import re
import socket

# For handing the client certificate and key to the TLS library, which reads them from files
import os
import tempfile

# For connecting to the broker and receiving messages
from proton import ConnectionException, LinkException, ProtonException, SSLDomain, Timeout
from proton.utils import BlockingConnection

__AMQPS_SCHEME = "amqps://"
__DEFAULT_NAMESPACE = "/"
__HOST_PATTERN = re.compile(r"^(?:[A-Za-z0-9._-]{1,253}|\[[0-9A-Fa-f:.]{2,45}\])$")
__CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")
__IPV4_SITE_LOCAL = [
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
]
__IPV6_SITE_LOCAL = ipaddress.ip_network("fec0::/10")
__IPV6_UNIQUE_LOCAL = ipaddress.ip_network("fc00::/7")
__BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/=\s]+$")
__PEM_MARKER = "-----BEGIN"
__AUTH_FAILURE_PHRASES = ("unauthorized", "access denied", "authentication failed")
INVALID_HOST_ERROR = "Host must be a hostname, IPv4 address, or bracketed IPv6 address."
BLOCKED_HOST_ERROR = "Host resolves to a restricted address range and is not permitted as a connection target for security reasons."
UNRESOLVABLE_HOST_ERROR = "Could not resolve host: "
AUTH_TYPE_BASIC = "BasicAuth"
AUTH_TYPE_MUTUAL_TLS = "MutualTLS"
RECEIVER_CREDIT = 100


class AmqpCustomerError(Exception):
    """A failure the customer has to fix, such as rejected credentials, reported with op.error() instead of raised."""


def is_valid_host(host):
    """
    Check that the host is a bare hostname, IPv4 address or bracketed IPv6 address, so that no URI options or
    path can be smuggled into the connection URL.
    Args:
        host: the configured host.
    Returns:
        True when the host is well formed.
    """
    return isinstance(host, str) and bool(__HOST_PATTERN.match(host))


def is_blocked_address(address):
    """
    Check whether an address falls into a range that must not be used as a connection target: loopback, any-local,
    link-local (including cloud metadata services), private networks, multicast, carrier-grade NAT, IPv6 unique-local,
    and the IPv4-mapped IPv6 forms of all of these.
    Args:
        address: an ipaddress.IPv4Address or IPv6Address.
    Returns:
        True when the address is blocked.
    """
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return is_blocked_address(address.ipv4_mapped)
    special_ranges = (
        address.is_loopback,
        address.is_unspecified,
        address.is_link_local,
        address.is_multicast,
    )
    if any(special_ranges):
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return address in __CARRIER_GRADE_NAT or any(address in net for net in __IPV4_SITE_LOCAL)
    return address in __IPV6_SITE_LOCAL or address in __IPV6_UNIQUE_LOCAL


def check_destination_allowed(host: str):
    """
    Resolve the host and reject it when any of its addresses is in a restricted range.
    Args:
        host: the configured host.
    Raises:
        ConnectionError: if the host cannot be resolved or resolves to a restricted address.
    """
    try:
        resolved = socket.getaddrinfo(host.strip("[]"), None)
    except socket.gaierror as error:
        raise ConnectionError(UNRESOLVABLE_HOST_ERROR + host) from error
    for entry in resolved:
        address = ipaddress.ip_address(entry[4][0].split("%")[0])
        if is_blocked_address(address):
            raise ConnectionError(BLOCKED_HOST_ERROR)


def amqp_url(host: str, port: int):
    """
    Build the connection URL. Connections always use TLS.
    Args:
        host: the configured host.
        port: the configured port.
    Returns:
        The amqps URL.
    """
    return f"{__AMQPS_SCHEME}{host}:{port}"


def has_non_default_namespace(namespace):
    """
    Check whether a namespace other than the broker default is configured.
    Args:
        namespace: the configured namespace, or None.
    Returns:
        True for a namespace that is neither empty nor "/".
    """
    return bool(namespace) and namespace != __DEFAULT_NAMESPACE


def decode_pem(value: str):
    """
    Accept a PEM certificate or key either as PEM text or base64-encoded PEM, since the setup form cannot take
    multi-line input.
    Args:
        value: the configured certificate or key.
    Returns:
        The PEM text.
    """
    text = value.strip()
    if __PEM_MARKER not in text and __BASE64_PATTERN.match(text):
        decoded = base64.b64decode(text, validate=False).decode("utf-8", errors="replace")
        if __PEM_MARKER in decoded:
            return decoded
    return value


def write_secret_file(directory: str, name: str, content: str):
    """
    Write a certificate or key to a file only the current user can read, for the TLS library to load.
    Args:
        directory: a private temporary directory.
        name: the file name.
        content: the PEM text.
    Returns:
        The path of the file.
    """
    path = os.path.join(directory, name)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(content)
    return path


def ssl_domain(configuration: dict, secrets_directory: str):
    """
    Build the TLS settings. The broker certificate is verified against the system trust store, including its host
    name. For mutual TLS the client certificate and private key are presented as well.
    Args:
        configuration: the connector configuration.
        secrets_directory: a private temporary directory for the client certificate and key files.
    Returns:
        A proton SSLDomain.
    """
    domain = SSLDomain(SSLDomain.MODE_CLIENT)
    domain.set_peer_authentication(SSLDomain.VERIFY_PEER_NAME)
    if configuration.get("auth_type") == AUTH_TYPE_MUTUAL_TLS:
        certificate = write_secret_file(
            secrets_directory, "client.pem", decode_pem(configuration["client_certificate"])
        )
        private_key = write_secret_file(
            secrets_directory, "client.key", decode_pem(configuration["client_private_key"])
        )
        domain.set_credentials(certificate, private_key, None)
    return domain


def connect(configuration: dict, timeout_seconds: float):
    """
    Open one connection. Basic authentication uses SASL PLAIN; mutual TLS uses SASL EXTERNAL with the client
    certificate.
    Args:
        configuration: the connector configuration.
        timeout_seconds: timeout for opening the connection and for blocking calls.
    Returns:
        A proton BlockingConnection.
    """
    with tempfile.TemporaryDirectory() as secrets_directory:
        options = {"ssl_domain": ssl_domain(configuration, secrets_directory)}
        if configuration.get("auth_type") == AUTH_TYPE_MUTUAL_TLS:
            options["allowed_mechs"] = "EXTERNAL"
        else:
            options["user"] = configuration.get("username")
            options["password"] = configuration.get("password")
            options["allowed_mechs"] = "PLAIN"
        return BlockingConnection(
            amqp_url(configuration["host"], int(configuration["port"])),
            timeout=timeout_seconds,
            **options,
        )


def open_connection(configuration: dict, timeout_seconds: float):
    """
    Validate the host, then connect to the broker's default virtual host.
    Selecting a non-default virtual host is not supported: RabbitMQ selects one through an AMQP open hostname of the
    form vhost:<name>, and python-qpid-proton 0.41.1 crashes the process on TLS connections whose open hostname
    contains a colon. When the broker closes the connection during open and a non-default namespace is configured,
    the sync fails with an error that says so instead.
    Args:
        configuration: the connector configuration.
        timeout_seconds: timeout for opening the connection and for blocking calls.
    Returns:
        A proton BlockingConnection.
    Raises:
        ValueError: if the host is malformed.
        ConnectionError: if the host resolves to a restricted address or cannot be resolved, or the broker rejects
            the connection while a non-default namespace is configured.
    """
    host = configuration.get("host")
    if not is_valid_host(host):
        raise ValueError(INVALID_HOST_ERROR)
    check_destination_allowed(host)
    try:
        return connect(configuration, timeout_seconds)
    except ConnectionException as error:
        namespace = configuration.get("namespace")
        if not has_non_default_namespace(namespace):
            raise
        raise ConnectionError(
            f"The broker closed the connection, and namespace '{namespace}' is configured. This connector only"
            " connects to the broker's default virtual host or Message VPN, so set the namespace to '/' or grant"
            f" access through the default one. Error: {error}"
        ) from error


def open_receiver(connection, queue_name: str):
    """
    Open a receiver on the queue. Deliveries stay unsettled until the connector accepts them, so a message is only
    removed from the queue after its row has been checkpointed.
    Args:
        connection: the open BlockingConnection.
        queue_name: the queue to consume.
    Returns:
        A proton BlockingReceiver.
    """
    return connection.create_receiver(queue_name, credit=RECEIVER_CREDIT)


def classify_failure(error: Exception):
    """
    Decide whether a failure is one the customer has to fix. Rejected credentials, a missing queue and an untrusted
    certificate become customer errors; connectivity problems and timeouts stay ordinary failures, so the sync fails
    and is retried.
    Args:
        error: the exception raised while connecting or consuming.
    Returns:
        An AmqpCustomerError with the message to show, or None when the error is not customer-actionable.
    """
    if isinstance(error, Timeout) or not isinstance(error, ProtonException):
        return None
    text = str(error)
    lowered = text.lower()
    if any(phrase in lowered for phrase in __AUTH_FAILURE_PHRASES):
        return AmqpCustomerError(
            f"Authentication with the AMQP broker failed. Update the credentials and reconnect. Error: {text}"
        )
    if isinstance(error, LinkException) and "not-found" in lowered:
        return AmqpCustomerError(
            f"The queue could not be found on the AMQP broker. Check the queue name and namespace. Error: {text}"
        )
    if "ssl" in lowered and ("certificate" in lowered or "trust" in lowered):
        return AmqpCustomerError(
            "The TLS handshake with the AMQP broker failed because of a certificate problem. Check the broker"
            f" certificate and, for mutual TLS, the client certificate and key. Error: {text}"
        )
    return None
