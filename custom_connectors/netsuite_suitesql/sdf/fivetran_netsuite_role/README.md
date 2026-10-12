# fivetran_netsuite_role (SDF package)

Deployable [SuiteCloud (SDF)](https://github.com/oracle/netsuite-suitecloud-sdk) package defining
the **Fivetran Integration** role (script ID `customrole_fivetran`) - the dedicated, read-only NetSuite role this connector's Fivetran setup
guide asks you to deploy. See the main **[../../README.md](../../README.md)** for the full setup
walkthrough (NetSuite feature enablement, integration record, user, access token, Fivetran
configuration). This file only covers deploying the package itself.

## Deploy

```bash
npm install -g --acceptSuiteCloudSDKLicense @oracle/suitecloud-cli
cd sdf/fivetran_netsuite_role
suitecloud account:setup
suitecloud project:validate
suitecloud project:deploy
```

`account:setup` prompts for an **Authentication ID** - any memorable local name (e.g.
`customer-netsuite`) works; it's a CLI-local alias, not a NetSuite-side value.

`project:deploy` creates or updates the custom role **Fivetran Integration** (script ID `customrole_fivetran`) in
whichever NetSuite account `account:setup` authenticated against. It does not create a user,
integration record, or access token.

## What's deployed

`src/Objects/customrole_fivetran.xml` is the definitive permission list - 115 Transactions
permissions (View) covering every standard NetSuite transaction type that can post to the
General Ledger, plus the minimum Setup/Reports/Lists permissions needed to authenticate and sync
(`account`, `subsidiary`, `accountingperiod`). Every permkey in that file was verified against a
live NetSuite permission export, not looked up from a static reference table.
