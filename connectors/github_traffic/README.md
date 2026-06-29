# GitHub Repository Traffic Connector

This connector syncs GitHub repository traffic data using the GitHub REST API. It collects the following information:
- Repository views (count and unique visitors)
- Repository clones (count and unique cloners)
- Top referral sources
- Top popular content paths

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init <project-path> --template connectors/github_traffic
```
`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration](#configuration) section for details on the required configuration parameters.

## Prerequisites
1. [GitHub Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) with the Read access to administration and metadata.
2. Repositories you want to monitor (in the format `owner/repo1, owner/repo2`)

## Configuration
Update the `configuration.json` file with your GitHub Personal Access Token and the repositories you want to monitor:

```json
{
  "personal_access_token": "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN",
  "repositories": "owner/repository1, owner/repository2"
}
```

## Tables and Schemas
### repository_views
Contains daily view counts for each repository.

| Column      | Type         | Description                           |
|-------------|--------------|---------------------------------------|
| repository  | STRING       | Repository name in owner/repo format  |
| timestamp   | UTC_DATETIME | Date of the view data                 |
| count       | INT          | Total view count for the day          |
| uniques     | INT          | Unique visitor count for the day      |

### repository_clones

Contains daily clone counts for each repository.
| Column      | Type         | Description                           |
|-------------|--------------|---------------------------------------|
| repository  | STRING       | Repository name in owner/repo format  |
| timestamp   | UTC_DATETIME | Date of the clone data                |
| count       | INT          | Total clone count for the day         |
| uniques     | INT          | Unique cloner count for the day       |

### repository_referrers
Contains top referral sources for each repository.

| Column     | Type         | Description                               |
|------------|--------------|-------------------------------------------|
| repository | STRING       | Repository name in owner/repo format      |
| referrer   | STRING       | Referral source (e.g., "google.com")      |
| count      | INT          | Total views from this referrer            |
| uniques    | INT          | Unique visitors from this referrer        |
| fetch_date | NAIVE_DATE   | Date when data was collected from the API |

### repository_paths

Contains top content paths for each repository.

| Column       | Type         | Description                                |
|--------------|--------------|--------------------------------------------|
| repository   | STRING       | Repository name in owner/repo format       |
| path         | STRING       | Path to the content (e.g., "/README.md")   |
| title        | STRING       | Title of the content                       |
| count        | INT          | Total views for this path                  |
| uniques      | INT          | Unique visitors for this path              |
| fetch_date   | NAIVE_DATE   | Date when data was collected from the API  |

## GitHub API Rate Limits

The GitHub API has rate limits. For authenticated requests, the rate limit is 5,000 requests per hour.

The traffic data endpoints specifically (views, clones, referrers, paths) only return data for the past 14 days.

## Required GitHub Permissions

The Personal Access Token used must have the `repo` scope to access traffic data for private repositories. For public repositories, only the `public_repo` scope is needed.

## Running the Connector

To run the connector locally for testing:

```bash
fivetran debug --configuration configuration.json
```

## Resources

- [GitHub Traffic API Documentation](https://docs.github.com/en/rest/metrics/traffic)
- [Fivetran Connector SDK Documentation](https://fivetran.com/docs/connectors/connector-sdk)