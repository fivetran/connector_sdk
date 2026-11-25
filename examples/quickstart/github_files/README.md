# GitHub Files Connector Example

## Connector overview
This connector syncs a single GitHub repository into your destination: one row of repository metadata, and one row for each file on the repository's default branch with the file's text in a `content` column. It is meant for making code and documentation searchable and available to AI features, as the file-content counterpart to a relational GitHub connector that syncs issues and commits but never fetches a file's bytes.

Content is read over the git protocol rather than the REST API. One shallow fetch replaces a tree request plus a request per file, and git operations do not draw on GitHub's REST hourly quota: listing a 5,000-file repository costs one fetch rather than roughly 5,000 blob requests. The connector uses [dulwich](https://www.dulwich.io/), a pure-Python git implementation, so no `git` binary is needed. The REST API is used for exactly one request per sync, to enrich the repository row, and only when the connection authenticates with a token.


## Requirements
- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)


## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template examples/quickstart/github_files
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.


## Features
- Reads the default branch with one depth-1 fetch into a temporary bare repository with no working tree, so no repository-controlled name ever becomes a local file path.
- Skips the fetch entirely when the branch head has not moved since the last completed sync, so an untouched repository costs one lightweight round trip.
- Syncs incrementally by blob sha: a file whose content is unchanged is neither re-read nor re-upserted, so its `modified_at` stays put and downstream parsing skips it.
- Marks files removed from the repository as deleted, after first clearing their content.
- Selects files with a built-in denylist of dependency and build directories, lock and generated files, binary and credential file types, `.env` files and files over 2 MB, plus optional include path globs.
- Authenticates with a personal access token over HTTPS or a read-only SSH deploy key, with github.com's host keys pinned.
- Defines a setup form with a connection test that performs a real `ls-remote`.


## Configuration file
The connector requires the following configuration parameters:

```json
{
  "auth_mode": "<personal_access_token OR ssh_deploy_key>",
  "personal_access_token": "<YOUR_GITHUB_FINE_GRAINED_PERSONAL_ACCESS_TOKEN>",
  "ssh_private_key": "<YOUR_SSH_DEPLOY_KEY_PRIVATE_KEY>",
  "repository": "<OWNER/REPOSITORY>",
  "include_path_patterns": "<OPTIONAL_COMMA_SEPARATED_GLOBS_E.G._src/**>"
}
```

- `auth_mode` – `personal_access_token` (the default) or `ssh_deploy_key`.
- `personal_access_token` – Required with token authentication.
- `ssh_private_key` – Required with deploy key authentication. The private key in OpenSSH or PEM format.
- `repository` – The repository as `owner/repository`, for example `acme/widgets`. Its default branch is synced.
- `include_path_patterns` – Optional comma-separated globs that act as a whitelist on top of the built-in denylist. `*` and `?` do not cross `/`, `**` does, and commas inside a `{a,b}` group are kept.

The same fields are defined in the setup form (refer to `def configuration_form()`). The form cannot show fields conditionally, so both credential fields are always displayed.

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.


## Requirements file
The connector requires the `dulwich` package to read the repository over the git protocol without a git binary, and the `paramiko` package for SSH deploy key authentication.

```
dulwich==1.2.21
paramiko==5.1.0
```

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.


## Authentication
The credential decides the transport: a token can only clone over HTTPS and a deploy key can only clone over SSH (refer to `def create_git_client()` in `git_client.py`).

| | Personal access token | SSH deploy key |
| --- | --- | --- |
| Clone transport | HTTPS, port 443 | SSH, port 22 |
| Access granted | Whatever the token's scope allows | Read-only, one repository |
| Repository metadata columns | Populated | Null, because the REST API cannot be called with an SSH key |

To set up token authentication:

1. In GitHub, create a fine-grained personal access token with `Contents: Read-only` on the one repository. A classic token would need the `repo` scope, which grants read and write access to every repository you can see.
2. Set `auth_mode` to `personal_access_token` and provide the token as `personal_access_token`.

To set up deploy key authentication:

1. Generate a keypair, for example with `ssh-keygen -t ecdsa -b 256 -f github_files_key -N ""`.
2. In the repository's settings on GitHub, add the public half as a deploy key, leaving "Allow write access" unchecked.
3. Set `auth_mode` to `ssh_deploy_key` and provide the private half as `ssh_private_key`.

A deploy key is scoped to one repository, and GitHub refuses to reuse one key across repositories, so each repository needs its own connection. The key is held in memory and never written to disk. github.com's published host keys are pinned rather than trusted on first use, because the connector runs unattended with no `known_hosts` to seed; a GitHub host key rotation requires updating `GITHUB_HOST_KEYS` in `git_client.py`.


## Pagination
Not applicable. The git protocol transfers the whole tree at the head commit in one fetch, so there is no truncation to handle: a fetch has the complete tree locally or fails outright. Large repositories are instead bounded per sync: at most 20,000 files are upserted in one sync, and the next sync resumes where it stopped (refer to `def sync_files()`).


## Data handling
Each sync runs these steps (refer to `def sync_repository_contents()`):

1. Resolve the default branch and its head commit with `ls-remote`, preferring the advertised symbolic `HEAD`.
2. If the head commit is unchanged since the last completed sync, stop.
3. Otherwise fetch the branch at depth 1, list its files, and compare each file's blob sha with the sha stored in the state. The blob sha is a hash of the content, so the comparison identifies changed files exactly.
4. Upsert each changed or added file, storing its sha in the state only after the upsert succeeds, and checkpoint every 100 files.
5. Clear and delete files that are no longer in the tree.
6. Advance the stored head commit only if every file was read, so a partial sync is never mistaken for a complete one.

The state stores, per repository, the branch, the head commit of the last completed sync and a map of file path to the first 16 characters of its blob sha.

File content is decoded as UTF-8, with a malformed byte replaced rather than dropping the file. Content is also sniffed for binary data before the row is written, because extensions lie: `.ts` is both TypeScript and MPEG transport stream. A file that turns out to be binary is skipped and holds the head commit back, as in the original connector (refer to `def read_text()`).

Deletions come from the tree diff rather than from a truncate. A truncate would mark the entire unchanged corpus deleted, precisely because unchanged files are not re-upserted. A removed file is first upserted with every column except its keys and `file_id` cleared, then deleted, because a soft-deleted row keeps whatever columns it had (refer to `def delete_removed_files()`).

`modified_at` is the committer date of the head commit in which the file last changed, not the sync time. The committer date rather than the author date, because a rebase moves the author date without the content changing.

The size cap is applied before content is read. The git object database offers no cheap size-only read for packed objects, so each blob that passes every other rule is decompressed once to measure it, one blob at a time.


## Error handling
- Repository read failures – A failure to read the repository over git fails the sync with a message naming the actionable causes, the repository name and the credential's read access, rather than the transport's protocol text (refer to `def sync_repository()`).
- Oversized repositories – A fetch larger than 2 GB fails the sync, because a shallow fetch transfers every blob at the head commit, including the ones the filter would reject (refer to `def check_clone_size()` in `git_client.py`).
- Unreadable files – One file whose content cannot be read is skipped rather than failing the sync, and holds the head commit back so it is retried next sync.
- Metadata failures – A failed REST request leaves the repository's metadata columns empty and the sync continues (refer to `def build_repository_row()`).
- Connection test – With a token, the REST API is asked first, because it can tell a missing repository from missing permission, which GitHub's git endpoint deliberately does not. Then a real `ls-remote` proves the credential can read the repository (refer to `def connection_test()`).


## Tables created
The connector creates the following tables (refer to `def schema()`).

| Table | Primary key | Columns | Grain |
| --- | --- | --- | --- |
| `repository` | `id` | `github_id` (LONG), `node_id`, `name`, `full_name`, `owner`, `description`, `html_url`, `default_branch`, `is_private` (BOOLEAN), `is_fork` (BOOLEAN), `archived` (BOOLEAN), `disabled` (BOOLEAN), `size` (LONG, in KB), `main_language`, `created_at` (UTC_DATETIME), `updated_at` (UTC_DATETIME), `pushed_at` (UTC_DATETIME), `synced_branch`, `synced_commit_sha`, `synced_commit_at` (UTC_DATETIME) | One row for the configured repository. |
| `repository_file` | `repository_id`, `path` | `repository_full_name`, `file_id`, `modified_at` (UTC_DATETIME), `size` (LONG), `content` (STRING), `url`, `html_url`, `blob_sha`, `mode` (STRING), `commit_sha`, `mimetype` | One row per replicated file. |

- `repository.id` is the configured `owner/repository`, not GitHub's numeric id. The numeric id needs a REST request and so is unavailable to a deploy key connection; it is synced as `github_id` when a token is available. The configured name also survives a rename on GitHub, which redirects the old name indefinitely.
- `repository_file.file_id` is `owner/repository:path`, so two repositories that both contain a `README.md` do not collide when it is used as a document id.
- `repository_file.url` is a permalink pinned to the immutable blob sha, so a citation survives the file changing. `html_url` points at the branch instead.


## Additional files
- `git_client.py` – Reads the repository over the git protocol with dulwich: resolves the default branch, fetches it at depth 1, lists its files and reads blobs. Also holds the SSH support with the pinned github.com host keys.
- `file_filter.py` – Decides which files to replicate: the built-in denylist, the size cap, the binary sniff and the include path globs.
- `github_api.py` – Reads repository metadata from the GitHub REST API, and checks repository access for the connection test.


## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
