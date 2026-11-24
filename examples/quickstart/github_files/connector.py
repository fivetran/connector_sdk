"""This connector syncs one GitHub repository: its metadata and the text of every file on its
default branch, read over the git protocol so that code and documentation can be parsed, embedded
and searched. Files are synced incrementally by blob sha.
See the Technical Reference documentation (https://fivetran.com/docs/connector-sdk/technical-reference)
and the Best Practices documentation (https://fivetran.com/docs/connector-sdk/best-practices) for details
"""

# For reading configuration from a JSON file
import json

# Import required classes from fivetran_connector_sdk
from fivetran_connector_sdk import Connector

# For enabling Logs in your connector code
from fivetran_connector_sdk import Logging as log

# For supporting Data operations like upsert(), update(), delete() and checkpoint()
from fivetran_connector_sdk import Operations as op

# For building the setup form shown to users when configuring the connector in Fivetran
from fivetran_connector_sdk import ConfigurationForm

# For defining the fields of the setup form
from fivetran_connector_sdk import form_field

# For returning success or failure from the setup form's connection test
from fivetran_connector_sdk import Test

# For catching git protocol failures raised by dulwich
from dulwich.client import HTTPUnauthorized
from dulwich.errors import GitProtocolError, NotGitRepository

# For catching SSH failures raised by paramiko
import paramiko

# For catching REST failures raised by requests
import requests

# For deciding which files to replicate
import file_filter

# For reading the repository over the git protocol
import git_client

# For enriching the repository row from the GitHub REST API
import github_api

__REPOSITORY_TABLE = "repository"
__FILE_TABLE = "repository_file"
__GITHUB_WEB_URL = "https://github.com"
__AUTH_MODE_TOKEN = "personal_access_token"
__AUTH_MODE_DEPLOY_KEY = "ssh_deploy_key"
__AUTH_MODES = (__AUTH_MODE_TOKEN, __AUTH_MODE_DEPLOY_KEY)
__CHECKPOINT_INTERVAL = 100
# Bounds how much one sync reads, so a large monorepo lands over several runs.
__MAX_FILES_PER_SYNC = 20_000
# 64 bits is ample to distinguish one repository's files.
__STATE_SHA_LENGTH = 16
# State is serialized on every checkpoint, so warn once it grows past this.
__STATE_PATH_WARNING_THRESHOLD = 200_000
__GIT_READ_FAILURES = (
    GitProtocolError,
    HTTPUnauthorized,
    NotGitRepository,
    paramiko.SSHException,
    OSError,
)

__MIMETYPES = {
    "md": "text/markdown",
    "markdown": "text/markdown",
    "json": "application/json",
    "yml": "application/yaml",
    "yaml": "application/yaml",
    "html": "text/html",
    "htm": "text/html",
    "css": "text/css",
    "csv": "text/csv",
    "xml": "application/xml",
}

# Every column of repository_file, so a soft-deleted row is written with all of them cleared.
__FILE_COLUMNS = (
    "repository_id",
    "path",
    "repository_full_name",
    "file_id",
    "modified_at",
    "size",
    "content",
    "url",
    "html_url",
    "blob_sha",
    "mode",
    "commit_sha",
    "mimetype",
)


def configuration_form():
    """
    Define the setup form shown to users when configuring this connector in Fivetran.
    Fivetran calls this method when rendering the connector setup UI.
    Returns:
        ConfigurationForm: the completed form with fields and the connection test.
    """
    config_form = ConfigurationForm()
    config_form.add_field(
        form_field.DropdownField(
            name="auth_mode",
            label="Authentication",
            fields=[
                form_field.DropdownFieldParam(
                    value=__AUTH_MODE_TOKEN,
                    label="Personal access token",
                    description="Clones over HTTPS, and also reads repository metadata.",
                ),
                form_field.DropdownFieldParam(
                    value=__AUTH_MODE_DEPLOY_KEY,
                    label="SSH deploy key",
                    description="Read-only access to this repository only; no metadata columns.",
                ),
            ],
            required=True,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="personal_access_token",
            label="Personal access token",
            description='Used with token authentication. Use a fine-grained token with "Contents:'
            ' Read-only" on just this repository. A classic token would need the "repo" scope,'
            " which grants read and write access to every repository you can see.",
            required=False,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="ssh_private_key",
            label="SSH deploy key private key",
            description="Used with deploy key authentication. The private half of a key whose public"
            ' half is installed as a deploy key on the repository with "Allow write access" left'
            " unchecked. A deploy key is scoped to one repository.",
            required=False,
            field_type=form_field.TextField.password,
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="repository",
            label="Repository",
            description='The repository to sync, as "owner/repository". For'
            ' https://github.com/acme/widgets that is "acme/widgets". Its default branch is synced.',
            required=True,
            field_type=form_field.TextField.plain_text,
            placeholder="owner/repository",
        )
    )
    config_form.add_field(
        form_field.TextField(
            name="include_path_patterns",
            label="Include path patterns",
            description="Comma-separated glob patterns matched against the path within the"
            " repository. Leave empty to sync every file. Dependency and build directories such as"
            " node_modules, dist and target are always excluded.",
            required=False,
            field_type=form_field.TextField.plain_text,
            placeholder="src/**",
        )
    )
    config_form.add_test(label="Checking repository access", func=connection_test)
    return config_form


def connection_test(configuration: dict):
    """
    Prove the credential can read the repository with a real ls-remote, so a mistyped repository
    or an uninstalled deploy key fails here rather than at the first sync. With a token, the REST
    API is asked first, because it can tell a missing repository from missing permission.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        Test response indicating success or failure.
    """
    test = Test()
    try:
        validate_configuration(configuration=configuration)
    except ValueError as error:
        return test.failure(str(error))
    repository = configuration["repository"].strip()
    if auth_mode_of(configuration) == __AUTH_MODE_TOKEN:
        problem = github_api.repository_access_problem(
            configuration["personal_access_token"], repository
        )
        if problem is not None:
            return test.failure(problem)
    try:
        client, path = create_git_client(configuration)
        git_client.resolve_remote_head(client, path)
    except (git_client.GitReadError,) + __GIT_READ_FAILURES as error:
        log.warning(f"Repository access test failed: {type(error).__name__}")
        return test.failure(
            f'Could not read repository "{repository}" over git. Check the name, and that the'
            " credential grants read access to it."
        )
    return test.success()


def validate_configuration(configuration: dict):
    """
    Validate the configuration dictionary to ensure it contains all required parameters.
    This function is called at the start of the update method to ensure that the connector has all necessary configuration values.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Raises:
        ValueError: if any required configuration parameter is missing or invalid.
    """
    auth_mode = auth_mode_of(configuration)
    if auth_mode not in __AUTH_MODES:
        raise ValueError(f"auth_mode must be one of {', '.join(__AUTH_MODES)}, got: {auth_mode}")
    if auth_mode == __AUTH_MODE_TOKEN and not configuration.get("personal_access_token"):
        raise ValueError("A personal access token is required.")
    if auth_mode == __AUTH_MODE_DEPLOY_KEY and not configuration.get("ssh_private_key"):
        raise ValueError("An SSH deploy key private key is required.")
    repository = str(configuration.get("repository", "")).strip()
    if not repository:
        raise ValueError("A repository is required.")
    # Anything else never resolves, and would fail mid-sync rather than at setup.
    if repository.count("/") != 1 or repository.startswith("/") or repository.endswith("/"):
        raise ValueError(f'Repository "{repository}" must be in "owner/repository" form.')
    for pattern in include_patterns_of(configuration):
        validate_pattern(pattern)


def validate_pattern(pattern: str):
    """
    Reject an include glob at setup rather than mid-sync.
    Args:
        pattern: one include path glob.
    Raises:
        ValueError: if the pattern is too long, not relative to the repository root, or invalid.
    """
    if len(pattern) > file_filter.MAX_PATTERN_LENGTH:
        raise ValueError(
            f'Include path pattern "{pattern}" is longer than '
            f"{file_filter.MAX_PATTERN_LENGTH} characters."
        )
    if pattern.startswith("/") or ".." in pattern:
        raise ValueError(
            f'Include path pattern "{pattern}" must be relative to the repository root and must'
            ' not contain "..".'
        )
    try:
        file_filter.glob_to_regex(pattern)
    except ValueError as error:
        raise ValueError(f'Include path pattern "{pattern}" is not a valid glob: {error}')


def auth_mode_of(configuration: dict):
    """
    Return the configured authentication mode, defaulting to a personal access token.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        The authentication mode.
    """
    return str(configuration.get("auth_mode") or __AUTH_MODE_TOKEN).strip()


def include_patterns_of(configuration: dict):
    """
    Split the comma-separated include patterns, keeping commas inside {a,b} groups.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        The non-empty patterns.
    """
    patterns, current, depth = [], [], 0
    for character in str(configuration.get("include_path_patterns") or ""):
        if character == "," and depth == 0:
            patterns.append("".join(current))
            current = []
            continue
        depth += {"{": 1, "}": -1}.get(character, 0)
        current.append(character)
    patterns.append("".join(current))
    return [pattern.strip() for pattern in patterns if pattern.strip()]


def create_git_client(configuration: dict):
    """
    Create the git client for the configured credential.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    Returns:
        A tuple of (dulwich client, repository path on that client).
    """
    return git_client.create_git_client(
        configuration["repository"].strip(),
        auth_mode_of(configuration),
        configuration.get("personal_access_token", ""),
        configuration.get("ssh_private_key", ""),
    )


def schema(configuration: dict):
    """
    Define the schema function which lets you configure the schema your connector delivers.
    See the technical reference documentation for more details on the schema function:
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#schema
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
    """
    return [
        {
            "table": __REPOSITORY_TABLE,
            "primary_key": ["id"],
            "columns": {
                "github_id": "LONG",
                "size": "LONG",
                "is_private": "BOOLEAN",
                "is_fork": "BOOLEAN",
                "archived": "BOOLEAN",
                "disabled": "BOOLEAN",
                "created_at": "UTC_DATETIME",
                "updated_at": "UTC_DATETIME",
                "pushed_at": "UTC_DATETIME",
                "synced_commit_at": "UTC_DATETIME",
            },
        },
        {
            "table": __FILE_TABLE,
            "primary_key": ["repository_id", "path"],
            "columns": {
                "size": "LONG",
                "content": "STRING",
                "modified_at": "UTC_DATETIME",
                # A git file mode such as 100644, which would otherwise be inferred as a number.
                "mode": "STRING",
            },
        },
    ]


def update(configuration: dict, state: dict):
    """
    Define the update function, which is a required function, and is called by Fivetran during each sync.
    See the technical reference documentation for more details on the update function
    https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-code/connector-sdk-methods#update
    Args:
        configuration: A dictionary containing connection details
        state: A dictionary containing state information from previous runs
        The state dictionary is empty for the first sync or for any full re-sync
    """
    log.warning("Example: QuickStart Examples - GitHub Files")

    # Validate the configuration to ensure it contains all required values.
    validate_configuration(configuration=configuration)

    repository = configuration["repository"].strip()
    sync_repository(configuration, state, repository)
    warn_if_state_is_large(state)


def sync_repository(configuration: dict, state: dict, repository: str):
    """
    Sync one repository, translating a failure to read it over git into an actionable message.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state, updated in place.
        repository: the repository as owner/repository.
    Raises:
        RuntimeError: when the repository cannot be read over git.
    """
    work_directory = git_client.create_work_directory()
    try:
        client, path = create_git_client(configuration)
        sync_repository_contents(configuration, state, repository, client, path, work_directory)
    except __GIT_READ_FAILURES as error:
        # The transport's own text describes the wire protocol, not anything the customer can
        # act on, so the actionable causes are named instead.
        log.warning(f"Git read failed for a GitHub repository: {type(error).__name__}: {error}")
        raise RuntimeError(
            f'Could not read repository "{repository}" over git. Check the repository name and that'
            " the credential grants read access."
        ) from error
    finally:
        git_client.remove_work_directory(work_directory)


def sync_repository_contents(configuration, state, repository, client, path, work_directory):
    """
    Sync the repository row and its changed, added and removed files.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state, updated in place.
        repository: the repository as owner/repository.
        client: the dulwich client.
        path: the repository path on that client.
        work_directory: the temporary directory the fetch lands in.
    """
    branch, remote_head_sha = git_client.resolve_remote_head(client, path)
    repo_state = state.setdefault("repositories", {}).setdefault(repository, {})
    repo_state.setdefault("file_shas", {})
    if repo_state.get("branch") != branch:
        # The cursors describe another branch, so the sha map cannot be trusted.
        repo_state["file_shas"] = {}
        repo_state["head_commit_sha"] = None
        repo_state["branch"] = branch
    if remote_head_sha == repo_state.get("head_commit_sha"):
        log.info("Branch head unchanged; skipping the fetch for one repository")
        checkpoint(state)
        return

    git_repository, head = git_client.fetch_head(
        client, path, branch, remote_head_sha, work_directory
    )
    try:
        sync_fetched_repository(configuration, state, repository, repo_state, git_repository, head)
    finally:
        # Releases the pack files before the temporary directory is removed.
        git_repository.close()


def sync_fetched_repository(configuration, state, repository, repo_state, git_repository, head):
    """
    Sync the repository row and the changed, added and removed files of a fetched repository.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        state: the connector state, updated in place.
        repository: the repository as owner/repository.
        repo_state: this repository's state, updated in place.
        git_repository: the fetched repository.
        head: the fetched head commit, with branch, sha and committed_at.
    """
    branch = head["branch"]
    repository_row = build_repository_row(configuration, repository, head)

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=__REPOSITORY_TABLE, data=repository_row)

    include_patterns = file_filter.compile_include_patterns(include_patterns_of(configuration))
    selected = select_files(git_repository, head["sha"], include_patterns)
    uploaded, failed = sync_files(
        git_repository, repository_row, head, repo_state, selected, state
    )
    if uploaded >= __MAX_FILES_PER_SYNC:
        # Leave head_commit_sha behind, so the next sync resumes rather than treating this
        # partial pass as complete.
        log.warning(
            f"Stopped after {uploaded} files for one repository; the next sync resumes where this"
            " one stopped."
        )
        checkpoint(state)
        return

    # Safe even after a partial pass: the listing was complete, so a path missing from it really
    # is gone.
    delete_removed_files(repository_row, repo_state, selected)
    repo_state["branch"] = branch
    if failed == 0:
        repo_state["head_commit_sha"] = head["sha"]
    else:
        # Advancing here would let the next sync short-circuit on an unchanged head and never
        # retry the failures. Holding it back costs one fetch.
        log.warning(
            f"{failed} files could not be read; holding the branch cursor back so they retry next"
            " sync."
        )
    checkpoint(state)


def build_repository_row(configuration: dict, repository: str, head: dict):
    """
    Build the repository row. REST metadata is best effort: a deploy key connection has no token,
    so those columns stay null rather than failing the sync.
    Args:
        configuration: a dictionary that holds the configuration settings for the connector.
        repository: the repository as owner/repository.
        head: the fetched head commit, with branch, sha and committed_at.
    Returns:
        The repository row.
    """
    owner, _, name = repository.partition("/")
    row = {
        # The configured owner/repository, not GitHub's numeric id, which needs a REST call. It
        # also survives a rename, because GitHub redirects the old name indefinitely.
        "id": repository,
        "github_id": None,
        "node_id": None,
        "name": name,
        "full_name": repository,
        "owner": owner,
        "description": None,
        "html_url": None,
        "default_branch": head["branch"],
        "is_private": None,
        "is_fork": None,
        "archived": None,
        "disabled": None,
        "size": None,
        "main_language": None,
        "created_at": None,
        "updated_at": None,
        "pushed_at": None,
        # The branch and commit this sync actually read, which the API does not report.
        "synced_branch": head["branch"],
        "synced_commit_sha": head["sha"],
        "synced_commit_at": head["committed_at"],
    }
    if auth_mode_of(configuration) != __AUTH_MODE_TOKEN:
        return row
    try:
        payload = github_api.fetch_repository(configuration["personal_access_token"], repository)
    except (requests.RequestException, ValueError) as error:
        log.warning(
            "Could not read repository metadata from the GitHub API; syncing files anyway: "
            f"{type(error).__name__}"
        )
        return row
    row.update(github_api.metadata_columns(payload))
    # The metadata overwrites full_name with the name GitHub reports, which differs from the
    # configured id after a rename. id stays as configured on purpose.
    row["id"] = repository
    return row


def select_files(git_repository, head_sha: str, include_patterns: list):
    """
    Return every file that passes the filter, keyed by path. A fetch has the whole tree locally or
    fails outright, so unlike the REST tree endpoint there is no truncation case to handle.
    Args:
        git_repository: the fetched repository.
        head_sha: the head commit sha.
        include_patterns: compiled include globs.
    Returns:
        A dictionary of path to tree entry.
    """
    entries = git_client.list_files(
        git_repository,
        head_sha,
        file_filter.is_prunable_directory,
        lambda entry: blob_size_if_candidate(git_repository, entry, include_patterns),
    )
    selected = {}
    for entry in entries:
        if file_filter.rejection_reason(entry, include_patterns) is None:
            selected[entry["path"]] = entry
    rejected = len(entries) - len(selected)
    log.info(
        f"Selected {len(selected)} files, skipped {rejected}, from a tree of {len(entries)} entries"
    )
    return selected


def blob_size_if_candidate(git_repository, entry: dict, include_patterns: list):
    """
    Return a blob's size, but only for an entry that every rule other than the size cap accepts:
    measuring decompresses the blob, which is not worth doing for a file that is skipped anyway.
    Args:
        git_repository: the fetched repository.
        entry: the tree entry, without its size.
        include_patterns: compiled include globs.
    Returns:
        The size in bytes, or None when the entry is rejected for another reason.
    """
    if file_filter.rejection_reason(entry, include_patterns) is not None:
        return None
    return len(git_client.read_blob(git_repository, entry["sha"]))


def sync_files(git_repository, repository_row, head, repo_state, selected, state):
    """
    Read changed and added files, leaving unchanged ones entirely untouched, so their modified_at
    stays put and downstream parsing skips them.
    Args:
        git_repository: the fetched repository.
        repository_row: the repository row.
        head: the fetched head commit.
        repo_state: this repository's state.
        selected: path to tree entry for every replicated file.
        state: the connector state, checkpointed periodically.
    Returns:
        A tuple of (files upserted, files that could not be read).
    """
    uploaded, unchanged, failed, since_checkpoint = 0, 0, 0, 0
    for path, entry in selected.items():
        sha = entry["sha"][:__STATE_SHA_LENGTH] if entry.get("sha") else None
        if sha is None:
            continue
        if repo_state["file_shas"].get(path) == sha:
            unchanged += 1
            continue
        try:
            if sync_file(git_repository, repository_row, head, entry):
                # Only after the upsert, so failures retry and an interrupted sync resumes rather
                # than restarts.
                repo_state["file_shas"][path] = sha
                uploaded += 1
            else:
                failed += 1
        except (KeyError, OSError) as error:
            # One unreadable file must not abort the sync. The path is omitted: customer data.
            log.warning(f"Skipping a GitHub file whose content could not be read: {error!r}")
            failed += 1

        since_checkpoint += 1
        if since_checkpoint >= __CHECKPOINT_INTERVAL:
            checkpoint(state)
            since_checkpoint = 0
        if uploaded >= __MAX_FILES_PER_SYNC:
            break
    log.info(f"Synced {uploaded} files, left {unchanged} unchanged, skipped {failed}")
    return uploaded, failed


def sync_file(git_repository, repository_row: dict, head: dict, entry: dict):
    """
    Upsert a file's row with its text in content. The row is written only once the content is in
    hand, so a file that could not be read leaves no row rather than a row with a null body.
    Args:
        git_repository: the fetched repository.
        repository_row: the repository row.
        head: the fetched head commit.
        entry: the file's tree entry.
    Returns:
        True when the row was written; False when the blob was binary or over the size cap.
    """
    content = read_text(git_repository, entry)
    if content is None:
        return False
    repository = repository_row["id"]
    path = entry["path"]
    row = {
        "repository_id": repository,
        "path": path,
        "repository_full_name": repository,
        # The document id the search index is keyed on, so it includes the repository.
        "file_id": f"{repository}:{path}",
        "modified_at": head["committed_at"],
        "size": entry.get("size"),
        "content": content,
        # Pinned to the immutable blob sha, so a citation survives the file changing.
        "url": blob_permalink(repository, entry["sha"], path),
        "html_url": blob_permalink(repository, head["branch"], path),
        "blob_sha": entry["sha"],
        "mode": entry.get("mode"),
        "commit_sha": head["sha"],
        "mimetype": mimetype_of(file_filter.file_name_of(path)),
    }

    # The 'upsert' operation is used to insert or update data in the destination table.
    # The first argument is the name of the destination table.
    # The second argument is a dictionary containing the record to be upserted.
    op.upsert(table=__FILE_TABLE, data=row)
    return True


def read_text(git_repository, entry: dict):
    """
    Return a blob decoded as UTF-8, or None when it is binary or over the size cap. A single
    malformed byte becomes a replacement character rather than costing the whole file.
    Args:
        git_repository: the fetched repository.
        entry: the file's tree entry.
    Returns:
        The text, or None.
    """
    content = git_client.read_blob(git_repository, entry["sha"])
    if len(content) > file_filter.MAX_FILE_SIZE_BYTES:
        log.warning("Skipping a GitHub file larger than the size cap")
        return None
    if file_filter.looks_binary(content[: file_filter.SNIFF_BYTES]):
        log.warning("Skipping a GitHub file whose content is not text")
        return None
    return content.decode("utf-8", errors="replace")


def delete_removed_files(repository_row: dict, repo_state: dict, selected: dict):
    """
    Soft-delete files gone from the tree. Deletions come from the tree diff rather than a full
    truncate: a truncate would mark the entire unchanged corpus deleted, precisely because
    unchanged files are not re-upserted. Two operations, in this order: a soft-deleted row keeps
    whatever columns it had, so blanking content first stops the text of every file ever removed
    from accumulating in the destination.
    Args:
        repository_row: the repository row.
        repo_state: this repository's state, updated in place.
        selected: path to tree entry for every file still in the repository.
    """
    removed = [path for path in repo_state["file_shas"] if path not in selected]
    for path in removed:
        row = dict.fromkeys(__FILE_COLUMNS)
        row.update(
            {
                "repository_id": repository_row["id"],
                "path": path,
                "repository_full_name": repository_row["full_name"],
                "file_id": f"{repository_row['id']}:{path}",
            }
        )

        # The 'upsert' operation is used to insert or update data in the destination table.
        # The first argument is the name of the destination table.
        # The second argument is a dictionary containing the record to be upserted.
        op.upsert(table=__FILE_TABLE, data=row)

        # The 'delete' operation marks the row with these primary key values as deleted.
        op.delete(table=__FILE_TABLE, keys={"repository_id": repository_row["id"], "path": path})
        del repo_state["file_shas"][path]
    if removed:
        log.info(f"Soft-deleted {len(removed)} files that are no longer in the repository")


def warn_if_state_is_large(state: dict):
    """
    Warn when the state tracks so many paths that serializing it on every checkpoint is costly.
    Args:
        state: the connector state.
    """
    tracked_paths = sum(
        len(repo_state.get("file_shas", {}))
        for repo_state in state.get("repositories", {}).values()
    )
    if tracked_paths > __STATE_PATH_WARNING_THRESHOLD:
        log.warning(
            f"Tracking {tracked_paths} file paths in state; consider narrowing the selection with"
            " include path patterns."
        )


def blob_permalink(repository: str, ref: str, path: str):
    """
    Return a GitHub link to a file at a ref.
    Args:
        repository: the repository as owner/repository.
        ref: a blob sha, for a permalink, or a branch name.
        path: the repository-relative file path.
    Returns:
        The URL, or None when the repository or ref is missing.
    """
    if not repository or not ref:
        return None
    return f"{__GITHUB_WEB_URL}/{repository}/blob/{ref}/{path}"


def mimetype_of(file_name: str):
    """
    Derive a content type from a file name's extension; git carries no content type.
    Args:
        file_name: the file name.
    Returns:
        The content type, or None for a file without an extension.
    """
    extension = file_filter.extension_of(file_name)
    if not extension:
        return None
    return __MIMETYPES.get(extension, "text/plain")


def checkpoint(state: dict):
    """
    Checkpoint the state.
    Args:
        state: the connector state.
    """
    # Save the progress by checkpointing the state. This is important for ensuring that the sync process can resume
    # from the correct position in case of next sync or interruptions.
    # You should checkpoint even if you are not using incremental sync, as it tells Fivetran it is safe to write to destination.
    # For large datasets, checkpoint regularly (e.g., every N records) not only at the end.
    # Learn more about how and where to checkpoint by reading our best practices documentation
    # (https://fivetran.com/docs/connector-sdk/best-practices#optimizingperformancewhenhandlinglargedatasets).
    op.checkpoint(state)


# Create the connector object using the schema and update functions
connector = Connector(update=update, schema=schema, configuration_form=configuration_form)

# Check if the script is being run as the main module.
# This is Python's standard entry method allowing your script to be run directly from the command line or IDE 'run' button.
#
# IMPORTANT: The recommended way to test your connector is using the Fivetran debug command:
#   fivetran debug
#
# This local testing block is provided as a convenience for quick debugging during development,
# such as using IDE debug tools (breakpoints, step-through debugging, etc.).
# Note: This method is not called by Fivetran when executing your connector in production.
# Always test using 'fivetran debug' prior to finalizing and deploying your connector.
if __name__ == "__main__":
    # Open the configuration.json file and load its contents
    with open("configuration.json", "r") as f:
        configuration = json.load(f)

    # Test the connector locally
    connector.debug(configuration=configuration)
