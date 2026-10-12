# NetSuite Connector Setup Guide

This guide walks you through preparing your NetSuite account and connecting it to Fivetran using
this connector. It extracts General Ledger and Trial Balance source data via **SuiteQL over
SuiteTalk REST Web Services**, authenticated with NetSuite **Token-Based Authentication (TBA)**.

**It does not require a SuiteAnalytics Connect subscription, and does not use the Data Warehouse
Integrator role.** If a NetSuite admin asks whether this needs the paid SuiteAnalytics Connect
add-on, the answer is no.

## Access model

- **Read-only.** Every data permission the connector's role holds is granted at View level. It
  cannot create, edit, or delete NetSuite records.
- **Scoped.** Access is limited to six tables: `subsidiary`, `account`, `accountingperiod`,
  `transaction`, `transactionline`, `transactionaccountingline` - the data behind General
  Ledger and Trial Balance reconstruction. No other part of the account is accessible. The
  connector and role are built for these tables only - loading others requires code and role
  changes (see [Extending beyond the included tables](#extending-beyond-the-included-tables)).
- **Enforced by NetSuite.** Access restrictions are applied by NetSuite's own role/permission
  system at the source - not by the connector's code.
- **Dedicated credentials.** The connector authenticates as a dedicated integration user via a
  revocable access token, never as a person's own login.
- **Repeatable, verifiable role definition.** The role is defined in a version-controlled
  [SuiteCloud (SDF)](https://github.com/oracle/netsuite-suitecloud-sdk) package and deployed with
  a handful of commands, instead of being manually assembled by checking permission boxes one at a time.

### Scope of access

| The connector can | The connector cannot |
|---|---|
| Read the 6 tables listed above (View only) | Create, edit, or delete any NetSuite record |
| Read every transaction type that can post to the General Ledger | Access unrelated data - customers, vendors, items, HR, payroll, web store, etc. |
| Connect via a token you issue and control | Log in interactively or act as a person |
| — | Require a SuiteAnalytics Connect subscription |

### Extending beyond the included tables

**The connector code and the role were built, tested, and permissioned for these six tables only**
(`subsidiary`, `account`, `accountingperiod`, `transaction`, `transactionline`,
`transactionaccountingline`). Nothing in this package has been verified for any other NetSuite
table.

To load additional tables, you must change **both**:

1. **The connector code** (`connector.py`) - add the table definition, columns, and query logic.
2. **The role** (`sdf/fivetran_netsuite_role`) - add the permissions NetSuite requires for the new
   tables.

Required permissions are not always obvious. NetSuite's SuiteQL row visibility depends on
per-record-type permissions that differ by table, and a missing permission can show up as zero
rows or a "Record not found" error rather than a clear access error. You will need
to investigate and verify the permissions for any new table yourself; they are not covered by this
guide or supported by the included role.

## Prerequisites

- A NetSuite administrator who can enable features, deploy the role, create an integration
  record, manage users/roles, and create an access token.
- [Node.js](https://nodejs.org) and the Oracle SuiteCloud CLI, to deploy the pre-built role.
- SuiteCloud Development Framework enabled in the NetSuite account (*Setup > Company > Enable
  Features > SuiteCloud > SuiteCloud Development Framework*).
- The NetSuite account ID.

## 1. Enable NetSuite features

Go to **Setup > Company > Enable Features**:

- **SuiteCloud** tab: enable **REST Web Services** and **Token-Based Authentication**.
- **Analytics** tab: enable **SuiteAnalytics Workbook** - not SuiteAnalytics Connect. Despite
  the similar name, this is a standard, no-cost feature this connector's SuiteQL queries
  actually depend on; it's unrelated to the paid Connect/ODBC product.

Click **Save**.

## 2. Deploy the Fivetran role

`sdf/fivetran_netsuite_role` is an SDF (SuiteCloud Development Framework) package defining a
dedicated, read-only role (**Fivetran Integration**, script ID `customrole_fivetran`) with exactly the permissions this connector
needs, built from a verified live permission export rather than hand-picked guesses.

```bash
npm install -g --acceptSuiteCloudSDKLicense @oracle/suitecloud-cli
```

This installs the SuiteCloud CLI on your own machine. It does not contact NetSuite.

```bash
cd sdf/fivetran_netsuite_role
suitecloud account:setup
```

This opens a browser and prompts you to log into NetSuite. The account you deploy to is whichever
one you log into here - sandbox or production, your choice. It stores a credential locally
(`~/.suitecloud-sdk`) and makes no changes to the account. You will also be prompted for an
**Authentication ID**, which is a local nickname for this login, not a NetSuite value.

```bash
suitecloud project:validate
```

This checks that the required features from Step 1 are enabled and that the role definition is
valid. It makes no changes to the account.

```bash
suitecloud project:deploy
```

This is the only command that changes NetSuite. It deploys exactly what `deploy.xml` lists - one
object, `customrole_fivetran.xml`. It creates the role **Fivetran Integration** if it doesn't
already exist, or updates it to match the file if it does, so a re-deploy will overwrite any
manual edits made to that role since. It does not touch any other role, user, data record,
script, or account-wide setting, and it does not create a user, integration record, or access
token - those are separate steps below.

**Feature dependencies**: the package requires `WEBSERVICES` and `SUBSIDIARIES` (see
`sdf/fivetran_netsuite_role/src/manifest.xml`). If either is disabled, `project:validate`/
`project:deploy` fail with an explicit error rather than enabling it. A single-subsidiary
(non-OneWorld) account without `SUBSIDIARIES` enabled will fail this check.

To test in a sandbox first, log into it during `account:setup`; run `account:setup` again against
production when ready. To remove the role later: **Setup > Users/Roles > Manage Roles >
Fivetran Integration** - deactivate or delete.

**What's in the role** (see `sdf/fivetran_netsuite_role/src/Objects/customrole_fivetran.xml`
for the exact list):

| Category | Grants | Why |
|---|---|---|
| Setup | Log in using Access Tokens (Full), REST Web Services (Full), Manage Accounting Periods (View) | required to authenticate via TBA/REST, and to sync `accountingperiod`. The two Full permissions only govern API login; they don't grant write access to any data record |
| Reports | SuiteAnalytics Workbook (Edit) | required for any SuiteQL query to execute at all |
| Lists | Accounts (View), Subsidiaries (View) | required to sync `account` and `subsidiary` |
| Transactions | View access to every standard transaction type that can post to the General Ledger (115 permissions) | the actual data-visibility gate for `transaction`/`transactionline`/`transactionaccountingline` - NetSuite's generic "Find Transaction" permission does **not** grant this |

> **Custom transaction types**: if your account has custom transaction types (not part of
> NetSuite's standard set), add View access for each one manually after deploying - see
> Troubleshooting below.

## 3. Create the integration record

1. Go to **Setup > Integration > Manage Integrations > New**.
2. Enter a name, e.g. `Fivetran NetSuite Integration`.
3. Set **State** to **Enabled**.
4. On the **Authentication** tab, check **Token-Based Authentication** only. Leave OAuth 2.0
   options unchecked - this connector only supports TBA.
5. Click **Save**, then copy the **Consumer Key** and **Consumer Secret**.

NetSuite displays the consumer secret only once, at creation - store it securely.

## 4. Create a dedicated user and assign the role

Use a dedicated, non-interactive integration user - not a person's own login.

1. Go to **Setup > Users/Roles > Manage Users**, and create a user or select an existing
   dedicated integration user.
2. Open the user, click **Edit**, go to the **Access** tab.
3. Check **Give Access**, add the **Fivetran Integration** role.
4. Click **Save**.

## 5. Create the access token

1. Go to **Setup > Users/Roles > Access Tokens > New**.
2. Select the integration record from step 3.
3. Select the dedicated user from step 4.
4. Select the **Fivetran Integration** role.
5. Click **Save**, then copy the **Token ID** and **Token Secret**.

NetSuite displays the token secret only once - store it securely.

## 6. Configure the connector in Fivetran

Enter these values in the connector's setup form (all fields except **Date To** are required):

| Field | Description |
|---|---|
| Account ID | NetSuite account id, e.g. `TSTDRV1234567`. |
| Consumer Key | Integration record's consumer key. |
| Consumer Secret | Integration record's consumer secret (masked). |
| Token ID | Access token's token ID. |
| Token Secret | Access token's token secret (masked). |
| Date From | Lower bound (inclusive) for transaction data, `YYYY-MM-DD`. |
| Date To *(optional)* | Upper bound (inclusive), `YYYY-MM-DD`. Leave blank to sync through the present. |
| Subsidiaries | Comma-separated subsidiary internal IDs to sync, e.g. `1,2,3`. |

There is no "Role ID" field and no authentication-method selector - this connector always
authenticates via TBA using the four credential fields above, and the role is identified
implicitly by whichever role the access token was created against in step 5.

Click **Test Connection** (this runs a real SuiteQL query, not just a field-presence check), then
**Save**.

## Troubleshooting

- **Connection test fails with a 401 / `INVALID_LOGIN` error**: double-check the four TBA
  credentials were copied correctly, and that the integration record and access token are both
  **Enabled**.
- **Connection test succeeds but a sync returns zero rows for transaction-related tables**:
  confirm the deployed role's Transactions permissions weren't trimmed after deployment, and that
  the assigned user's subsidiary/accounting-book access covers what's configured in
  **Subsidiaries**.
- **Some transactions are missing**: if the account uses custom transaction types, they aren't
  included in the deployed role automatically - add View access for each one manually (*Setup >
  Users/Roles > Manage Roles > Fivetran Integration > Transactions subtab*).
