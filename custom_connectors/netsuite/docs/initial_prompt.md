I need to build a connector to extract data from Netsuite which DOES NOT require having a SuiteAnalytics subscription. 
We will place all artifacts into the folder /Users/sean.odriscoll/Github/connector_sdk/custom_connectors/netsuite
For context, can you do the following:
- Check any examples that might already be available in Fivetran using fivetran_ai mcp or any other context you have
- Research NetSuite documentation to understand what is possible and what configuration would be required to make the connection (auth, permissions, secrets needed, etc.)
- Check if there are any public examples (e.g. Git projects, Medium articles etc.) which we can use as a starting point for development. Try to verify that any projects / code / methods being considered and used as context are tested and verified to work
Some key features that the connector should have is: 
- There is no requirement for incremental replication. Only initial sync is required. 
- The ability to specify which tables and columns are extracted
- The ability to apply filters to data, ideally even complex filtering like INNER JOIN style filters
    - An example of this is filtering the transactionline table by date and subsidiary, and then using the distinct Transaction IDs from the resulting table to filter the transaction table's records (since this table does not have a column for subsidiary)
- Use methods which allow us to handle large data volumes efficiently without placing excessive load on the source system
- If there is a SQL method to extract data from NetSuite, it does not require SuiteAnalytics and it is performant enough (from a load and speed perspective) then we should consider it as an architecture choice. If there is another method which is significantly more efficient, then we should use that instead
I have admin access to a demo NetSuite instance which we can use for testing, and I can provide any credentials or complete any configuration needed to support that. 
Initially, I would like you to present a concise plan which explains your proposed method for how the connector should work, keeping the explanation high-level, but techincal enough for an SE to confirm what methods are being used, how the high-level logic would work, what parameters would be needed to configure the connection, what configuration would be required inside NetSuite, etc. 
Once we have confirmed the plan, we would then build the connector and enter a build-test framework
After building, you should test it and if the test fails, diagnose the errors, fix them, and re-test
Repeat automatically without asking for confirmation until you get a clean Sync SUCCEEDED with zero errors or warnings. 
Once it passes, confirm the record counts for each table.
