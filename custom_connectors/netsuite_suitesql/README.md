# NetSuite SuiteQL Connector Example

## Connector overview

This connector extracts General Ledger (GL) and Trial Balance source data from NetSuite using SuiteQL over SuiteTalk REST Web Services, authenticated with NetSuite Token-Based Authentication (TBA). It is designed for NetSuite accounts that do not have the paid SuiteAnalytics Connect subscription: it does not use SuiteAnalytics Connect (ODBC/JDBC) or the Data Warehouse Integrator role. It does need the free SuiteAnalytics Workbook feature, which SuiteQL requires.

The connector syncs six tables: `subsidiary`, `account`, `accountingperiod`, `transaction`, `transactionline`, and `transactionaccountingline`. These are the tables needed to reconstruct the GL and Trial Balance in a destination warehouse. Setup takes a date range and a list of subsidiaries; the table list, columns, and joins are fixed in `connector.py`.

The connector and the NetSuite role that goes with it were built, tested, and permissioned for these six tables only. See [Extending beyond the included tables](#extending-beyond-the-included-tables) if you want to load others.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- A NetSuite administrator who can enable features, deploy a role, create an integration record, manage users and roles, and create an access token.
- [Node.js](https://nodejs.org) and the Oracle SuiteCloud CLI, to deploy the pre-built role.
- SuiteCloud Development Framework enabled in the NetSuite account (**Setup > Company > Enable Features > SuiteCloud > SuiteCloud Development Framework**).

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters. Complete the [NetSuite setup](#netsuite-setup) steps first to obtain the credentials.

## Features

- Extracts GL and Trial Balance source data with SuiteQL over REST Web Services, with no SuiteAnalytics Connect subscription.
- Authenticates with TBA (OAuth 1.0a, HMAC-SHA256) as a dedicated integration user (`get_oauth1_auth`).
- Ships a deployable SuiteCloud (SDF) package that creates a read-only, least-privilege NetSuite role (`sdf/fivetran_netsuite_role`).
- Filters transaction data by date range and subsidiary.
- Handles NetSuite's 100,000-row SuiteQL limit by splitting large windows by date, then subsidiary, then transaction ID (`sync_windowed_table`).
- Retries transient errors with exponential backoff (`execute_suiteql`).
- Resumes an interrupted sync from the last checkpoint.
- Validates configuration and runs a real query on **Test Connection** so problems show up at setup time (`validate_configuration`, `connection_test`).

## Configuration file

The configuration keys below are uploaded to Fivetran from `configuration.json`.

```json
{
  "account_id": "<YOUR_NETSUITE_ACCOUNT_ID>",
  "consumer_key": "<YOUR_CONSUMER_KEY>",
  "consumer_secret": "<YOUR_CONSUMER_SECRET>",
  "token_key": "<YOUR_TOKEN_ID>",
  "token_secret": "<YOUR_TOKEN_SECRET>",
  "date_from": "2020-01-01",
  "date_to": "",
  "subsidiaries": "1,2,3"
}
```

- `account_id` (required) - NetSuite account ID, for example `TSTDRV1234567` or `1234567_SB1`. Used to build the SuiteQL host and as the OAuth realm. Letters, digits, hyphens, and underscores only.
- `consumer_key` (required) - The integration record's consumer key.
- `consumer_secret` (required) - The integration record's consumer secret.
- `token_key` (required) - The access token's token ID.
- `token_secret` (required) - The access token's token secret.
- `date_from` (required) - Lower bound (inclusive) for transaction data, in `YYYY-MM-DD` format.
- `date_to` (optional) - Upper bound (inclusive), in `YYYY-MM-DD` format. Leave blank to sync through the present. It must not be earlier than `date_from`.
- `subsidiaries` (required) - Comma-separated numeric subsidiary internal IDs, for example `1,2,3`.

The Fivetran setup form shows these fields with labels and masks the two secrets (`configuration_form`). There is no role ID field and no authentication-method selector: the connector always uses TBA, and the role is whichever role the access token was created against.

Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values. When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file

The `requirements.txt` file lists the Python libraries the connector needs in addition to those pre-installed by Fivetran. This connector needs one:

```
requests_oauthlib==2.0.0
```

`requests_oauthlib` signs the TBA requests with OAuth 1.0a (HMAC-SHA256) and pulls in `oauthlib` as a dependency.

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication

The connector authenticates with NetSuite Token-Based Authentication. Each request is signed with OAuth 1.0a using the consumer key and secret from an integration record, and the token ID and secret from an access token (`get_oauth1_auth`). Create these in NetSuite as described in [NetSuite setup](#netsuite-setup).

Use a dedicated integration user and a custom role. NetSuite can reject TBA logins made with the Administrator role, in some accounts with a generic 401 (`EntityOrRoleDisabled` in the Login Audit Trail).

## Pagination

The connector pages through each SuiteQL result with `limit` and `offset`, 1,000 rows per request, until `hasMore` is false (`sync_simple_table`, `sync_windowed_table`). NetSuite stops paging a single query at 100,000 rows, so large tables are split into smaller windows first. See [Handling large accounts](#handling-large-accounts).

## Data handling

- Each sync is a full re-extraction. There is no incremental cursor.
- At the start of each fresh extraction of a table, the connector truncates that table once (`truncate_table`) and then upserts the current rows. Rows that were deleted in NetSuite, or that fall outside a narrowed date range or subsidiary list, are soft-deleted in the destination (`_fivetran_deleted = true`) instead of lingering as active rows. The truncate is recorded in the checkpointed state, so a resumed sync does not truncate again.
- Date and subsidiary filters are passed to SuiteQL as bound parameters, and configuration values are validated before use (`validate_configuration`).
- `state` holds only the progress needed to resume an interrupted sync: per-table completion, the pending windows, and the current offset.

### What's synced

- `subsidiary`, `account`, and `accountingperiod` are dimension tables, synced in full on every run with no date or subsidiary filter (`sync_simple_table`).
- `transactionline` is filtered directly: it has its own `subsidiary` column and is joined to `transaction` to filter on `trandate`.
- `transaction` has no `subsidiary` column and no usable date column of its own for this filter. It is filtered through the matching `transactionline` rows with a subquery.
- `transactionaccountingline` is the GL posting detail per transaction line. It has neither `subsidiary` nor `trandate`, so it is joined to `transaction` for the date and to `transactionline` for the subsidiary. It joins to `transactionline` on `tl.id = tal.transactionline`, not on `linesequencenumber`: the two values differ on many lines, and joining on the sequence number drops or misassociates accounting lines.

`transactionline.postingperiod` cannot be selected or filtered through SuiteQL REST in the account this connector was built against (the query fails with `500 UNEXPECTED_ERROR`), so the connector filters on `transaction.trandate` instead.

Every column reference is qualified with the table alias. A bare `SELECT *` on a joined query merges the columns of both tables into one result. The column lists are narrowed to what GL and Trial Balance reconstruction needs.

### Handling large accounts

NetSuite caps a SuiteQL query at 100,000 rows. To guarantee full coverage regardless of account size, each date-filtered table is fetched in windows, and a window that is too large is split further (`sync_windowed_table`):

1. Count the window with `SELECT COUNT(*)`, using the same filters and joins as the data query (`build_count_query`).
2. If the count is at or below the safe threshold of 90,000 rows, page through the window and upsert it.
3. Otherwise split the window in half by date and repeat for each half (`split_window`).
4. If a window is a single day and still too large, split it into one window per configured subsidiary.
5. If a window is a single day for a single subsidiary and still too large, split by transaction ID range (`get_id_range`, `split_id_range`).
6. If a window cannot be split any further and is still over the threshold, the sync fails with an error instead of silently truncating the data.

The state keeps the list of pending windows, so an interrupted sync resumes mid-window without redoing finished windows. The dimension tables are not windowed; if one ever reached the row limit, the sync fails with an error.

## Error handling

- Transient errors (HTTP 429, 5xx, and network errors) are retried up to 5 times with exponential backoff, honoring `Retry-After` when present (`execute_suiteql`).
- Other 4xx responses, including a 401 for bad credentials, fail immediately with the NetSuite error text and are not retried.
- Invalid configuration values (malformed dates, `date_to` earlier than `date_from`, non-numeric subsidiary IDs, or a malformed account ID) are rejected before any request is made (`validate_configuration`).
- A window or table that reaches NetSuite's row cap and cannot be split further raises an error instead of syncing partial data.
- **Test Connection** runs `SELECT id FROM subsidiary`, so bad credentials or a missing permission are caught at setup time (`connection_test`).
- Because each fresh extraction truncates a table before reloading it, a sync that fails partway can leave that table partially reloaded until the next successful sync completes. Rows already reloaded stay active, and the remaining rows stay soft-deleted.

## Tables created

The connector creates these six tables. The connector selects a curated list of columns for the transaction tables, not every column NetSuite exposes.

- `subsidiary` - primary key `id`. All columns.
- `account` - primary key `id`. Columns: `id`, `acctnumber`, `accountsearchdisplayname`, `accttype`, `subsidiary`, `isinactive`.
- `accountingperiod` - primary key `id`. All columns.
- `transactionline` - primary key `transaction`, `linesequencenumber`. Columns: `transaction`, `id`, `linesequencenumber`, `subsidiary`, `department`, `class`, `location`, `memo`.
- `transaction` - primary key `id`. Columns: `id`, `tranid`, `trandate`, `type`, `entity`, `memo`, `status`.
- `transactionaccountingline` - primary key `transaction`, `transactionline`, `accountingbook`. Columns: `transaction`, `transactionline`, `account`, `accountingbook`, `debit`, `credit`, `amount`, `netamount`, `posting`.

`transactionaccountingline.transactionline` references `transactionline.id`, so the connector syncs `id` on `transactionline` to let you join the two tables in the destination. The `id` value is unique only within a transaction, not across the table.

## NetSuite setup

### 1. Enable NetSuite features

Go to **Setup > Company > Enable Features**:

- On the **SuiteCloud** tab, enable **REST Web Services** and **Token-Based Authentication**.
- On the **Analytics** tab, enable **SuiteAnalytics Workbook**. This is not SuiteAnalytics Connect. Despite the similar name, it is a standard, no-cost feature that this connector's SuiteQL queries depend on.

Click **Save**.

### 2. Deploy the Fivetran role

`sdf/fivetran_netsuite_role` is an SDF (SuiteCloud Development Framework) package that defines a dedicated, read-only role, **Fivetran Integration** (script ID `customrole_fivetran`), with the permissions this connector needs. Install the SuiteCloud CLI on your own machine. This does not contact NetSuite:

```bash
npm install -g --acceptSuiteCloudSDKLicense @oracle/suitecloud-cli
```

Log in to the NetSuite account you want to deploy to, which can be a sandbox or production account. This opens a browser, stores a credential locally in `~/.suitecloud-sdk`, and makes no changes to the account. You are prompted for an authentication ID, which is a local nickname for this login and not a NetSuite value:

```bash
cd sdf/fivetran_netsuite_role
suitecloud account:setup
```

Check that the required features from step 1 are enabled and that the role definition is valid. This makes no changes to the account:

```bash
suitecloud project:validate
```

Deploy the role. This is the only command that changes NetSuite:

```bash
suitecloud project:deploy
```

The deploy creates the **Fivetran Integration** role if it does not exist, or updates it to match `customrole_fivetran.xml` if it does, which overwrites manual edits made to that role since. It does not touch any other role, user, data record, script, or account-wide setting, and it does not create a user, integration record, or access token.

The package requires the `WEBSERVICES` and `SUBSIDIARIES` features (see `sdf/fivetran_netsuite_role/src/manifest.xml`). If either is disabled, validation and deployment fail with an explicit error rather than enabling it. A single-subsidiary (non-OneWorld) account without `SUBSIDIARIES` enabled fails this check.

To test in a sandbox first, log in to the sandbox during `account:setup`, and run `account:setup` again against production when ready. To remove the role later, go to **Setup > Users/Roles > Manage Roles**, find **Fivetran Integration**, and deactivate or delete it.

The role (see `sdf/fivetran_netsuite_role/src/Objects/customrole_fivetran.xml` for the exact list) grants:

- Setup: Log in using Access Tokens (Full), REST Web Services (Full), and Manage Accounting Periods (View). The first two are needed to authenticate through TBA and REST, and the third to sync `accountingperiod`. The two Full permissions only govern API login. They do not grant write access to any data record.
- Reports: SuiteAnalytics Workbook (Edit). SuiteQL queries do not run without it.
- Lists: Accounts (View) and Subsidiaries (View), to sync `account` and `subsidiary`.
- Transactions: View access to every standard transaction type that can post to the GL (115 permissions). Per-transaction-type permissions are the actual data-visibility gate for `transaction`, `transactionline`, and `transactionaccountingline`. NetSuite's generic Find Transaction permission does not grant it. A role with only Find Transaction sees zero transaction rows through SuiteQL, and a role with no Transactions permissions at all makes NetSuite report the table as not existing (`Record 'transaction' was not found`).

Note: If your account has custom transaction types, add View access for each one manually after deploying. See [Troubleshooting](#troubleshooting).

### 3. Create the integration record

1. Go to **Setup > Integration > Manage Integrations > New**.
2. Enter a name, for example `Fivetran NetSuite Integration`.
3. Set **State** to **Enabled**.
4. On the **Authentication** tab, select **Token-Based Authentication** only. Leave the OAuth 2.0 options cleared, because this connector supports TBA only.
5. Click **Save**, then copy the **Consumer Key** and **Consumer Secret**.

NetSuite displays the consumer secret only once, at creation, so store it securely.

### 4. Create a dedicated user and assign the role

Use a dedicated, non-interactive integration user, not a person's own login.

1. Go to **Setup > Users/Roles > Manage Users**, and create a user or select an existing dedicated integration user.
2. Open the user, click **Edit**, and go to the **Access** tab.
3. Select **Give Access**, and add the **Fivetran Integration** role.
4. Click **Save**.

### 5. Create the access token

1. Go to **Setup > Users/Roles > Access Tokens > New**.
2. Select the integration record from step 3.
3. Select the dedicated user from step 4.
4. Select the **Fivetran Integration** role.
5. Click **Save**, then copy the **Token ID** and **Token Secret**.

NetSuite displays the token secret only once, so store it securely.

### 6. Configure the connector in Fivetran

Enter the values from the [Configuration file](#configuration-file) section in the connector's setup form. All fields except **Date To** are required. Click **Test Connection**, which runs a real SuiteQL query, and then **Save**.

## Access model

- Read-only: every data permission the role holds is granted at View level, so the connector cannot create, edit, or delete NetSuite records.
- Scoped: access is limited to the six tables above. No other part of the account is accessible, and NetSuite's role and permission system enforces this at the source, not the connector's code.
- Dedicated credentials: the connector authenticates as a dedicated integration user with a revocable access token, never as a person's own login, and it cannot log in interactively.
- Repeatable: the role is defined in a version-controlled SDF package instead of being assembled by selecting permission boxes one at a time.

### Extending beyond the included tables

The connector code and the role were built, tested, and permissioned for the six tables above only. Nothing in this package has been verified for any other NetSuite table.

To load additional tables, you must change both:

1. The connector code (`connector.py`): add the table definition, columns, and query logic to `__TABLES`.
2. The role (`sdf/fivetran_netsuite_role`): add the permissions NetSuite requires for the new tables.

Required permissions are not always obvious. SuiteQL row visibility depends on per-record-type permissions that differ by table, and a missing permission can appear as zero rows or a "Record not found" error instead of a clear access error. You must investigate and verify the permissions for any new table yourself. They are not covered by this guide or the included role.

## Troubleshooting

- Connection test fails with a 401 or `INVALID_LOGIN` error: check that the four TBA credentials were copied correctly and that the integration record and access token are both enabled. If you reset the integration record's consumer secret, create a new access token as well.
- Connection test succeeds but a sync returns zero rows for transaction tables: confirm the deployed role's Transactions permissions were not trimmed, and that the user's subsidiary and accounting book access covers the configured **Subsidiaries**.
- Some transactions are missing: custom transaction types are not in the deployed role. Add View access for each one under **Setup > Users/Roles > Manage Roles > Fivetran Integration > Permissions > Transactions**.
- Permission changes usually take effect on an existing access token without regenerating it. Try that before creating a new token.

## Additional files

- `sdf/fivetran_netsuite_role/` - The SDF package that deploys the Fivetran Integration role. Its own `README.md` covers deploying the package only.

## Additional considerations

The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
