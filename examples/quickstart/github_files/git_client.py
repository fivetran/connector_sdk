"""Reads a GitHub repository over the git protocol, used by connector.py.

One shallow fetch replaces a tree request plus a request per file, and git operations do not draw
on GitHub's REST hourly quota. The fetch lands in a bare repository with no working tree, so no
repository-controlled name ever becomes a path on the local filesystem and a symlink cannot escape
the temporary directory. dulwich implements git in Python, so no git binary is needed.
"""

# For reading an in-memory private key with paramiko
import io

# For measuring and removing the temporary repository
import os
import shutil
import tempfile

# For converting commit times to UTC timestamps
from datetime import datetime, timezone

# For the git protocol over HTTPS and SSH, and for the fetched object database
from dulwich.client import HttpGitClient, SSHGitClient, SSHVendor
from dulwich.repo import Repo

# For SSH connections with a deploy key and a pinned host key
import paramiko

# A shallow fetch still transfers every blob at the head commit, including the ones the filter
# would reject, so this bounds the disk a single sync can occupy. Exceeding it fails the sync.
MAX_CLONE_BYTES = 2 * 1024 * 1024 * 1024

GIT_HTTPS_HOST = "https://github.com/"
GIT_SSH_HOST = "github.com"
TOKEN_USERNAME = "x-access-token"

__SSH_USERNAME = "git"
__SSH_PORT = 22
__CONNECT_TIMEOUT_SECONDS = 60
__READ_BUFFER_BYTES = 65536
__HEADS_PREFIX = b"refs/heads/"
__HEAD = b"HEAD"
__SHALLOW_DEPTH = 1
__GIT_PROTOCOL_V2 = 2
__GITLINK_MODE = 0o160000
__TREE_MODE = 0o040000
__REGULAR_FILE_MODE = 0o100644
__EXECUTABLE_FILE_MODE = 0o100755

# Branch names preferred when the remote does not advertise a symbolic HEAD.
__DEFAULT_BRANCH_PREFERENCE = (b"main", b"master")

# Every host key github.com publishes at https://api.github.com/meta. All three rather than one,
# because the algorithm is negotiated and pinning one would make the handshake depend on which
# key the client prefers. A GitHub key rotation requires updating this list.
GITHUB_HOST_KEYS = {
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
    "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEez"
    "OmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aN"
    "UkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWz"
    "AOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlh"
    "Scqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFP"
    "GQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYi"
    "rYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOx"
    "JCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs"
    "+p1vN1/wsjk=",
}

# Private key formats tried in turn when parsing a deploy key.
__KEY_CLASSES = (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey)


class GitReadError(Exception):
    """A repository could not be read over git: wrong name, missing access, or a network failure."""


def is_github_host_key(key):
    """
    Check a server key against github.com's published host keys, in known_hosts encoding.
    Args:
        key: the paramiko public key the server presented.
    Returns:
        True when the key is one of the pinned keys.
    """
    try:
        encoded = f"{key.get_name()} {key.get_base64()}"
    except (AttributeError, ValueError):
        return False
    return encoded in GITHUB_HOST_KEYS


class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Accepts only github.com's published host keys: no known_hosts exists to trust on first use."""

    def missing_host_key(self, client, hostname, key):
        """
        Reject any host key that github.com does not publish.
        Args:
            client: the paramiko client.
            hostname: the host being connected to.
            key: the key the server presented.
        Raises:
            paramiko.SSHException: when the key is not pinned.
        """
        if not is_github_host_key(key):
            raise paramiko.SSHException(f"Host key for {hostname} did not match github.com")


def parse_private_key(private_key: str):
    """
    Parse an OpenSSH or PEM private key held in memory.
    Args:
        private_key: the key text.
    Returns:
        The paramiko key.
    Raises:
        GitReadError: if the key cannot be parsed. The cause is not attached because it can carry
        key material.
    """
    for key_class in __KEY_CLASSES:
        try:
            return key_class.from_private_key(io.StringIO(private_key))
        except (paramiko.SSHException, ValueError):
            continue
    raise GitReadError("The SSH deploy key could not be parsed")


class ParamikoChannel:
    """The socket-like object dulwich reads and writes the git protocol through."""

    def __init__(self, client, channel):
        """
        Wrap an SSH channel running a git command.
        Args:
            client: the connected paramiko client, closed with the channel.
            channel: the channel running git-upload-pack.
        """
        self.client = client
        self.channel = channel
        self.stderr = None

    def read(self, size=-1):
        """
        Read exactly size bytes, or fewer at end of stream.
        Args:
            size: the number of bytes to read; negative reads to end of stream.
        Returns:
            The bytes read.
        """
        return read_channel(self.channel, size)

    def write(self, data):
        """
        Send bytes to the remote git command.
        Args:
            data: the bytes to send.
        Returns:
            The number of bytes sent.
        """
        self.channel.sendall(data)
        return len(data)

    def can_read(self):
        """
        Check whether data is waiting to be read.
        Returns:
            True when the channel has buffered data.
        """
        return self.channel.recv_ready()

    def close(self, timeout=None):
        """
        Close the channel and the SSH connection.
        Args:
            timeout: unused; present for compatibility with dulwich's subprocess wrapper.
        """
        self.channel.close()
        self.client.close()


class PinnedParamikoVendor(SSHVendor):
    """Runs git commands over SSH with an in-memory deploy key and github.com's host keys pinned."""

    def __init__(self, private_key: str):
        """
        Create the vendor.
        Args:
            private_key: the deploy key, held in memory and never written to disk.
        """
        self.key = parse_private_key(private_key)

    def run_command(
        self,
        host,
        command,
        username=None,
        port=None,
        password=None,
        key_filename=None,
        ssh_command=None,
        protocol_version=None,
    ):
        """
        Open an SSH connection and start a git command on it.
        Args:
            host: the SSH host.
            command: the remote command, as bytes.
            username: the SSH user.
            port: the SSH port.
            password: unused.
            key_filename: unused; the key is held in memory.
            ssh_command: unused.
            protocol_version: the git protocol version to request.
        Returns:
            A ParamikoChannel.
        """
        return open_git_channel(self.key, host, command, username, port, protocol_version)


def read_channel(channel, size: int):
    """
    Read exactly size bytes from an SSH channel, or fewer at end of stream.
    Args:
        channel: the paramiko channel.
        size: the number of bytes to read; negative reads to end of stream.
    Returns:
        The bytes read.
    """
    chunks = []
    remaining = size
    while remaining != 0:
        chunk = channel.recv(__READ_BUFFER_BYTES if remaining < 0 else remaining)
        if not chunk:
            break
        chunks.append(chunk)
        if remaining > 0:
            remaining -= len(chunk)
    return b"".join(chunks)


def open_git_channel(key, host, command, username, port, protocol_version):
    """
    Open an SSH connection with a pinned host key and start a git command on it. No system
    known_hosts, agent or ~/.ssh keys are consulted, so the outcome does not depend on the machine
    the connector runs on.
    Args:
        key: the parsed deploy key.
        host: the SSH host.
        command: the remote command, as bytes or text.
        username: the SSH user.
        port: the SSH port, or None for the default.
        protocol_version: the git protocol version to request.
    Returns:
        A ParamikoChannel.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(PinnedHostKeyPolicy())
    client.connect(
        host,
        port=port or __SSH_PORT,
        username=username,
        pkey=key,
        allow_agent=False,
        look_for_keys=False,
        timeout=__CONNECT_TIMEOUT_SECONDS,
    )
    channel = client.get_transport().open_session()
    if protocol_version == __GIT_PROTOCOL_V2:
        channel.update_environment({"GIT_PROTOCOL": "version=2"})
    channel.exec_command(command.decode() if isinstance(command, bytes) else command)
    return ParamikoChannel(client, channel)


def create_git_client(repository: str, auth_mode: str, token: str, private_key: str):
    """
    Create the git client for the configured credential. A token authenticates only over HTTPS and
    a deploy key only over SSH, so the credential decides the transport.
    Args:
        repository: the repository as owner/repository.
        auth_mode: "personal_access_token" or "ssh_deploy_key".
        token: the personal access token, used in token mode.
        private_key: the deploy key, used in deploy key mode.
    Returns:
        A tuple of (dulwich client, repository path on that client).
    """
    if auth_mode == "ssh_deploy_key":
        client = SSHGitClient(
            GIT_SSH_HOST,
            port=__SSH_PORT,
            username=__SSH_USERNAME,
            vendor=PinnedParamikoVendor(private_key),
        )
        return client, f"/{repository}.git"
    client = HttpGitClient(GIT_HTTPS_HOST, username=TOKEN_USERNAME, password=token)
    # Relative, because the path is resolved against the base URL like a link.
    return client, f"{repository}.git"


def resolve_remote_head(client, path: str):
    """
    Resolve the default branch and its head commit without fetching anything. One lightweight
    round trip, which is what lets an untouched repository cost nothing regardless of its size.
    Args:
        client: the dulwich client.
        path: the repository path on that client.
    Returns:
        A tuple of (branch name, head commit sha), both strings.
    Raises:
        GitReadError: if the repository has no commits or its default branch cannot be determined.
    """
    result = client.get_refs(path.encode())
    refs = result.refs
    branch = default_branch_of(refs, result.symrefs)
    head = refs.get(__HEADS_PREFIX + branch)
    if not head:
        raise GitReadError("The repository has no commits to sync.")
    return branch.decode(), head.decode()


def default_branch_of(refs: dict, symrefs: dict):
    """
    Resolve the remote's default branch. Prefers the advertised symbolic HEAD; servers that do not
    advertise one leave only HEAD's commit to match against, which is ambiguous when several
    branches point at the same commit, hence the name preference before falling back to any match.
    Args:
        refs: ref name to commit sha, as bytes.
        symrefs: symbolic ref name to target ref name, as bytes.
    Returns:
        The default branch name, as bytes.
    Raises:
        GitReadError: if no branch can be identified.
    """
    target = symrefs.get(__HEAD)
    if target and target.startswith(__HEADS_PREFIX):
        return target[len(__HEADS_PREFIX) :]
    head_sha = refs.get(__HEAD)
    if head_sha:
        for preferred in __DEFAULT_BRANCH_PREFERENCE:
            if refs.get(__HEADS_PREFIX + preferred) == head_sha:
                return preferred
        for name, sha in refs.items():
            if name.startswith(__HEADS_PREFIX) and sha == head_sha:
                return name[len(__HEADS_PREFIX) :]
    raise GitReadError(
        "Could not determine the default branch; the repository may be empty or unreadable."
    )


def fetch_head(client, path: str, branch: str, head_sha: str, work_directory: str):
    """
    Fetch one branch at depth 1 into a bare repository and return its head commit. Depth 1 because
    history is never read: blob shas are compared against the connector's own state.
    Args:
        client: the dulwich client.
        path: the repository path on that client.
        branch: the branch to fetch.
        head_sha: the head commit resolved by resolve_remote_head().
        work_directory: an empty temporary directory that receives the bare repository.
    Returns:
        A tuple of (repository, head dict with branch, sha and committed_at).
    Raises:
        GitReadError: if the fetched objects exceed MAX_CLONE_BYTES.
    """
    repository = Repo.init_bare(work_directory)
    wanted = head_sha.encode()
    client.fetch(
        path.encode(),
        repository,
        determine_wants=lambda refs, depth=None: [wanted],
        depth=__SHALLOW_DEPTH,
    )
    check_clone_size(work_directory)
    commit = repository[wanted]
    # The committer date of the head commit, which becomes modified_at on every file this sync
    # changes. The author date would move with a rebase without the content changing.
    committed_at = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc)
    head = {
        "branch": branch,
        "sha": head_sha,
        "committed_at": committed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return repository, head


def check_clone_size(work_directory: str):
    """
    Fail the sync when the fetched repository is too large to be safe on a shared node.
    Args:
        work_directory: the bare repository directory.
    Raises:
        GitReadError: if the directory holds more than MAX_CLONE_BYTES.
    """
    total = 0
    for directory, _, file_names in os.walk(work_directory):
        for file_name in file_names:
            try:
                total += os.path.getsize(os.path.join(directory, file_name))
            except OSError:
                # A file removed while walking is not part of the repository's size.
                continue
    if total > MAX_CLONE_BYTES:
        raise GitReadError(
            f"The repository is larger than {MAX_CLONE_BYTES} bytes and cannot be synced."
        )


def list_files(repository, head_sha: str, is_prunable_directory, size_of):
    """
    Return every file at the head commit as a tree entry with the REST tree API's encoding: a
    symlink is a blob with mode 120000 and a submodule is a commit. Directories the caller rejects
    are skipped without descending into them, so a vendored directory costs one entry.
    Args:
        repository: the fetched repository.
        head_sha: the head commit sha.
        is_prunable_directory: called with a directory path; True skips the directory.
        size_of: called with a regular file's entry; returns its size, or None to skip measuring.
    Returns:
        A list of entry dictionaries with path, mode, type, sha and size keys.
    """
    entries = []
    pending = [("", repository[head_sha.encode()].tree)]
    while pending:
        prefix, tree_sha = pending.pop()
        for item in repository[tree_sha].items():
            item_path = prefix + item.path.decode("utf-8", errors="replace")
            if item.mode == __TREE_MODE:
                if not is_prunable_directory(item_path):
                    pending.append((item_path + "/", item.sha))
                continue
            entry = {
                "path": item_path,
                "mode": format(item.mode, "o"),
                "type": "commit" if item.mode == __GITLINK_MODE else "blob",
                "sha": item.sha.decode(),
                "size": None,
            }
            if item.mode in (__REGULAR_FILE_MODE, __EXECUTABLE_FILE_MODE):
                entry["size"] = size_of(entry)
            entries.append(entry)
    entries.sort(key=lambda entry: entry["path"])
    return entries


def read_blob(repository, sha: str):
    """
    Read a blob's bytes from the fetched object database.
    Args:
        repository: the fetched repository.
        sha: the blob sha.
    Returns:
        The blob content.
    """
    return repository.object_store[sha.encode()].as_raw_string()


def create_work_directory():
    """
    Create an empty temporary directory for one fetch.
    Returns:
        The directory path.
    """
    return tempfile.mkdtemp(prefix="github-files-")


def remove_work_directory(work_directory: str):
    """
    Remove a fetch's temporary directory and everything in it.
    Args:
        work_directory: the directory path.
    """
    shutil.rmtree(work_directory, ignore_errors=True)
