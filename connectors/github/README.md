# GitHub Connector Example

## Connector overview

This connector integrates with the GitHub REST API to synchronize repository data, commits, and pull requests into your destination. It provides comprehensive insights into your organization's repositories, development activity, and code review processes. The connector can sync data from both on-premises and cloud (github.com) instances.

The connector uses GitHub App authentication for secure access and supports incremental syncs to efficiently fetch only new or updated data. It handles pagination automatically and implements robust error handling with retry logic for production use.

Example use cases include:

- Development analytics - Track commit frequency, PR velocity, and code review metrics.
- Repository management - Monitor repository growth, stars, forks, and activity.
- Team productivity - Analyze contributor activity, PR turnaround time, and collaboration patterns.
- Compliance and security - Audit code changes, track repository settings, and monitor access.
- Cross-repository insights - Compare activity across multiple repositories in your organization.

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
fivetran init <project-path> --template connectors/github
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- GitHub App authentication - Uses JWT-based authentication for secure, long-term access.
- Incremental sync - Fetches only new or updated data since the last sync using timestamp filtering.
- Multi-organization support - Syncs data from multiple GitHub organizations in a single run, if required.
- Automatic pagination - Handles GitHub's pagination (100 items per page) automatically.
- State management - Tracks sync progress per repository for reliable resumption after interruptions.
- Rate limiting - Implements delays between requests and handles rate limit errors gracefully.
- Retry logic - Automatic retry with exponential backoff for transient errors.
- Checkpointing - Saves progress every 1000 records during large repository syncs, once after each repository completes, and once after all organizations are fully processed.

## Configuration file

The configuration file contains the GitHub App credentials required to authenticate with the GitHub API.

```json
{
  "app_id": "<YOUR_GITHUB_APP_ID>",
  "private_key": "<YOUR_GITHUB_APP_PRIVATE_KEY>",
  "organization": "<YOUR_ORGANIZATION_NAME>",
  "installation_id": "<YOUR_INSTALLATION_ID>"
}
```

For on-premises GitHub Enterprise instances, add a `"base_url"` field with your instance's URL (e.g., `"base_url": "https://github.your-company.com/api/v3"`).

Configuration parameters:
- `app_id` (required) - Your GitHub App ID (found in **GitHub App settings**).
- `private_key` (required) - RSA private key for your GitHub App (PEM format with newlines).
- `organization` (required) - GitHub organization name to sync (can be comma-separated for multiple orgs).
- `installation_id` (required) - Installation ID for the GitHub App on your organization.

Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

This connector requires the following Python packages:

```
pyjwt==2.11.0
cryptography==36.0.1
```

Explanation: PyJWT is used for GitHub App JWT authentication. The cryptography package is required by PyJWT for RSA algorithm support (RS256), which is used to sign JWTs with the GitHub App's private key.

Note: The `fivetran_connector_sdk` and `requests` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

### GitHub app setup

This connector uses GitHub App authentication, which is the recommended approach for production integrations. Follow these steps to set up a GitHub App:

#### Step 1: Create a GitHub App
1. Click your profile icon (top right) and select **Settings**.
2. In the left sidebar, scroll down and click **Developer settings**.
3. Click **GitHub Apps**, then click **New GitHub App**.
4. Enter a descriptive **GitHub App name** (e.g., Fivetran Data Sync).
5. In **Homepage URL**, enter your organization's website or use `https://fivetran.com`.
6. Uncheck the **Webhook Active** option. You don't need it for this connector.

#### Step 2: Set permissions
1. Under Repository permissions, set **Contents** to Read-only (to access repository data).
2. Set **Metadata** to Read-only (automatically required).
3. Set **Pull requests** to Read-only (to access PR data).

#### Step 3: Generate a private key
1. Scroll to the **Private keys** section.
2. Click **Generate a private key**.
3. Save the downloaded `.pem` file securely.
4. Copy the entire contents, including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`.

#### Step 4: Note your App ID
At the top of the GitHub App settings page, make a note of the **App ID**. You will need it later to authenticate your connector.

#### Step 5: Install the app
1. Go to **Install App** in the left sidebar.
2. Click **Install** next to your organization.
3. Choose whether to give access to all repositories or select specific ones.
4. After installation, note the **Installation ID** from the URL: `https://github.com/organizations/{org}/settings/installations/{installation_id}`

#### Step 6: Configure the connector
Add the following items to your connector's `configuration.json`:
- `app_id` (the **App ID** from step 4)
- `private_key` (the full private key content from step 3)
- `organization` (your GitHub organization name)
- `installation_id` (the **Installation ID** from step 5)

### Authentication flow

The connector uses a two-step authentication process implemented in `generate_jwt()` and `get_installation_access_token()`:
1. Generates a JSON Web Token (JWT) signed with your private key (valid for 10 minutes).
2. Get installation token: Exchanges the JWT for an installation access token (valid for 1 hour).
3. API requests: Uses the installation token for all GitHub API requests.

## Pagination

The connector implements cursor-based pagination using GitHub's Link header.

Pagination details:
- Page size - 100 records per request (GitHub's maximum).
- Link header parsing - Automatically extracts "next" page URLs from response headers using `parse_pagination_links()`.
- Memory efficient - Uses generator functions to process data without loading everything into memory.
- Rate limiting - Adds a 2-second delay between page requests to respect GitHub's rate limiting.

Example pagination flow:
1. Request first page: `GET /orgs/{org}/repos?per_page=100`.
2. Parse `Link` header: `<https://api.github.com/orgs/{org}/repos?page=2>; rel="next"`.
3. Request next page using extracted URL.
4. Continue until no "next" link is present.

## Data handling

### Incremental sync

The connector supports incremental synchronization to minimize API calls and processing time. Implemented in `get_repositories()`, `get_commits()`, and `get_pull_requests()` functions:

Repositories:
- Sorts by `updated` timestamp in descending order (note: `GET /orgs/{org}/repos` does not support a `since` query parameter).
- Filters client-side - stops paginating as soon as a repository's `updated_at` is older than the last sync timestamp.

Commits:
- Uses the `since` query parameter supported by `GET /repos/{owner}/{repo}/commits` to fetch only commits after last sync time.
- Tracked per repository in state.

Pull requests:
- Fetches both open and closed PRs.
- Filters by `updated_at` timestamp.
- Stops fetching when encountering PRs with `updated_at` older than the last sync timestamp.

### State management

The connector maintains detailed state for resumable syncs, managed in the `update()` function with `process_repository_data()` helper:

```json
{
  "last_repo_sync": "2024-02-13T10:30:00Z",
  "processed_repos": {
    "org/repo1": {
      "last_commit_sync": "2024-02-13T10:35:00Z",
      "last_pr_sync": "2024-02-13T10:35:00Z"
    }
  }
}
```

State fields:
- `last_repo_sync` - The timestamp when the last full sync completed. On the next run, the connector fetches only repositories updated after this date/time. This value only advances once all organizations are fully processed.
- `processed_repos` - A record of the newest commit date and PR date that were successfully synced for each repository. On the next run, only commits and PRs newer than these timestamps are fetched.

Checkpointing:
- Every 1000 commits or pull requests - Flushes buffered records to the destination. Per-repo timestamps are not updated here, so if the sync is interrupted mid-repository, the next run re-fetches the full repository from its last completed point.
- After each repository completes - Saves the newest commit date and PR date for that repository.
- After all organizations complete - Advances `last_repo_sync` to mark the sync as fully done.

## Error handling

The connector implements comprehensive error handling with retry logic in `make_github_request()`.

### Retry strategy

- Maximum retries - 3 attempts for failed requests.
- Exponential backoff - Waits 2^attempt seconds between retries (2s, 4s, 8s).
- Rate limit handling - Automatically waits until rate limit resets (checks `X-RateLimit-Reset` header).
- 409 conflict - Skips repositories that return 409 errors and continues processing.

### Error categories

- Configuration errors - Validated at sync start with clear error messages in `validate_configuration()`.
- Authentication errors - JWT generation and token exchange failures.
- HTTP errors - Handled based on status code (4xx vs 5xx).
- Network errors - Retried with exponential backoff.

### Special handling

- 404 errors - Repository not found or no access, skips and continues.
- 403 rate limit - Waits until rate limit resets (minimum 60 seconds).
- 409 conflict - Empty repository or git conflict, skips repository.

## Tables created

The connector creates the `REPOSITORIES`, `COMMITS`, and `PULL_REQUESTS` tables in your destination. Column types are inferred from the data returned by the GitHub API and may vary based on the actual values received.

### REPOSITORIES

Contains repository metadata and statistics. Column types shown below are typical but may be inferred differently based on the data.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key - Unique GitHub repository ID |
| `name` | STRING | Repository name |
| `full_name` | STRING | Full repository name (owner/repo) |
| `description` | STRING | Repository description |
| `private` | BOOLEAN | Whether the repository is private |
| `html_url` | STRING | Repository web URL |
| `clone_url` | STRING | HTTPS clone URL |
| `ssh_url` | STRING | SSH clone URL |
| `language` | STRING | Primary programming language |
| `stargazers_count` | INT | Number of stars |
| `watchers_count` | INT | Number of watchers |
| `forks_count` | INT | Number of forks |
| `open_issues_count` | INT | Number of open issues |
| `default_branch` | STRING | Default branch name (e.g., "main") |
| `created_at` | TIMESTAMP | Repository creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |
| `pushed_at` | TIMESTAMP | Last push timestamp |
| `archived` | BOOLEAN | Whether the repository is archived |
| `disabled` | BOOLEAN | Whether the repository is disabled |

### COMMITS

Contains commit history for all repositories. Column types shown below are typical but may be inferred differently based on the data.

| Column | Type | Description |
|--------|------|-------------|
| `sha` | STRING | Primary key - Unique commit SHA hash |
| `repository` | STRING | Repository name (owner/repo) |
| `message` | STRING | Commit message |
| `author_name` | STRING | Commit author name |
| `author_email` | STRING | Commit author email |
| `author_date` | TIMESTAMP | When the commit was authored |
| `author_login` | STRING | GitHub username of author |
| `committer_name` | STRING | Committer name |
| `committer_email` | STRING | Committer email |
| `committer_date` | TIMESTAMP | When the commit was committed |
| `committer_login` | STRING | GitHub username of committer |
| `html_url` | STRING | Commit web URL |

### PULL_REQUESTS

Contains pull request data including both open and closed PRs. Column types shown below are typical but may be inferred differently based on the data.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key - Unique GitHub PR ID |
| `number` | INT | PR number within the repository |
| `repository` | STRING | Repository name (owner/repo) |
| `title` | STRING | PR title |
| `body` | STRING | PR description/body |
| `state` | STRING | PR state (open or closed) |
| `user_login` | STRING | PR creator's GitHub username |
| `user_id` | INT | PR creator's GitHub user ID |
| `created_at` | TIMESTAMP | When the PR was created |
| `updated_at` | TIMESTAMP | When the PR was last updated |
| `closed_at` | TIMESTAMP | When the PR was closed (null if open) |
| `merged_at` | TIMESTAMP | When the PR was merged (null if not merged) |
| `merge_commit_sha` | STRING | Merge commit SHA if merged |
| `assignee_login` | STRING | Assignee's GitHub username |
| `head_ref` | STRING | Source branch name |
| `head_sha` | STRING | Source branch commit SHA |
| `base_ref` | STRING | Target branch name |
| `base_sha` | STRING | Target branch commit SHA |
| `html_url` | STRING | PR web URL |
| `draft` | BOOLEAN | Whether the PR is a draft |
| `merged` | BOOLEAN | Whether the PR was merged |

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.

### Troubleshooting

#### Common issues

Unable to retrieve installation access token
- Confirm that the GitHub App has been installed on your organization (go to **Install App** in the sidebar and check that your org is listed).
- Make sure the `app_id` in your configuration matches the App ID shown on your GitHub App settings page.
- Double-check the `installation_id` — you can find it in the URL after installing the app: `https://github.com/organizations/{org}/settings/installations/{installation_id}`.

Empty private key error
- Ensure the private key includes opening and closing tags: `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`.
- Preserve newline characters in the private key (use `\n` in JSON).

No data returned
- Verify the organization name is correct.
- Ensure the GitHub App has access to the repositories.
- Check repository permissions in **GitHub App settings**.

Rate limit errors
- The connector automatically handles rate limits.
- For large organizations, consider increasing the sync frequency.

### Related examples

- [github_traffic connector example](../github_traffic/) - This example shows how to sync GitHub repository traffic metrics (views, clones, referrers, and popular content paths) using the GitHub REST API. It demonstrates how to work with GitHub's traffic analytics endpoints, handle limited historical data (14 days), and use Personal Access Token authentication.
- [Certificate authentication pattern example](../../examples/common_patterns_for_connectors/authentication/certificate/) - This example demonstrates certificate-based authentication with two approaches - using base64 encoded certificates in configuration, or retrieving certificates from AWS S3 at runtime. Useful for understanding advanced credential management patterns that can be applied to GitHub App private keys.

### Additional resources

- [GitHub Apps Documentation](https://docs.github.com/en/apps)
- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connectors/connector-sdk)
- [GitHub API Rate Limits](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api)
