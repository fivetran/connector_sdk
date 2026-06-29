# Cortex Agent Setup Guide

Complete guide for configuring Snowflake Cortex Agent for the Livestock Weather Intelligence connector.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Data Setup](#data-setup)
3. [Semantic View Creation](#semantic-view-creation)
4. [Agent Configuration via UI](#agent-configuration-via-ui)
5. [Connector Integration](#connector-integration)
6. [Testing Your Setup](#testing-your-setup)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Snowflake Features

- ✅ Snowflake account with Cortex AI enabled
- ✅ Database (e.g., `YOUR_DATABASE`)
- ✅ Schema (e.g., `YOUR_SCHEMA`)
- ✅ User with appropriate permissions (ACCOUNTADMIN or granted privileges)

### Required Permissions

```sql
-- Grant database and schema access
GRANT USAGE ON DATABASE YOUR_DATABASE TO ROLE YOUR_ROLE;
GRANT USAGE ON SCHEMA YOUR_DATABASE.YOUR_SCHEMA TO ROLE YOUR_ROLE;

-- Grant table access
GRANT SELECT ON ALL TABLES IN SCHEMA YOUR_DATABASE.YOUR_SCHEMA TO ROLE YOUR_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA YOUR_DATABASE.YOUR_SCHEMA TO ROLE YOUR_ROLE;

-- Grant Cortex privileges
GRANT CREATE VIEW ON SCHEMA YOUR_DATABASE.YOUR_SCHEMA TO ROLE YOUR_ROLE;
```

---

## Data Setup

### Step 1: Create AGR_RECORDS Table

The connector requires livestock health data with the following structure:

```sql
CREATE OR REPLACE TABLE YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS (
    -- Primary identifiers
    RECORD_ID VARCHAR(50) PRIMARY KEY,
    ANIMAL_ID VARCHAR(50),
    FARM_ID VARCHAR(50),
    
    -- Animal characteristics
    SPECIES VARCHAR(50),
    BREED VARCHAR(100),
    AGE INTEGER,
    WEIGHT DECIMAL(10,2),
    
    -- Health information
    HEALTH_STATUS VARCHAR(50),
    VACCINATION_HISTORY VARCHAR(500),
    MEDICATION_HISTORY VARCHAR(500),
    
    -- Environmental conditions
    TEMPERATURE DECIMAL(5,2),
    HUMIDITY DECIMAL(5,2)
);
```

### Step 2: Load Sample Data

Use the provided `agr_records.csv` file (included in this submission):

```sql
-- Create stage for CSV file
CREATE OR REPLACE STAGE YOUR_DATABASE.YOUR_SCHEMA.AGR_STAGE;

-- Upload agr_records.csv to the stage using Snowflake UI:
-- 1. Go to Data > Databases > YOUR_DATABASE > YOUR_SCHEMA > Stages
-- 2. Click on AGR_STAGE
-- 3. Click "+ Files" button (top right)
-- 4. Upload agr_records.csv
-- 5. Click "Upload"

-- Load data from CSV
COPY INTO YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS
FROM @YOUR_DATABASE.YOUR_SCHEMA.AGR_STAGE/agr_records.csv
FILE_FORMAT = (
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
)
ON_ERROR = 'CONTINUE';

-- Verify data loaded
SELECT COUNT(*) FROM YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS;
-- Expected: 42 records

-- View sample data
SELECT * FROM YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS LIMIT 5;
```

**Sample Data Overview:**
- **42 animals** across **4 farms** (FARM_000000 through FARM_000003)
- **Species**: Beef Cattle (21), Chickens (10), Pigs (7), Goats (4)
- **Health Status**: Mostly healthy (38), with some injured (4)
- **Realistic data**: Proper breeds, weights, ages, vaccinations, environmental conditions

---

## Semantic View Creation

### What is a Semantic View?

A semantic view is a YAML-based specification that tells Cortex Analyst how to understand and query your data. It defines:
- **Tables**: What data tables exist
- **Columns**: What each column represents and its meaning
- **Relationships**: How tables connect (if multiple tables)
- **Filters**: Pre-defined query constraints

### Step 3: Create Semantic View YAML

Create a file named `agr_livestock_semantic_view.yaml`:

```yaml
name: Livestock Health Performance
tables:
  - name: AGR_RECORDS
    base_table:
      database: YOUR_DATABASE
      schema: YOUR_SCHEMA
      table: AGR_RECORDS
    description: "Livestock health records with environmental conditions for weather impact analysis"
    columns:
      - name: RECORD_ID
        description: "Unique record identifier"
        data_type: TEXT
        unique: true
      
      - name: ANIMAL_ID
        description: "Unique animal identifier"
        data_type: TEXT
      
      - name: FARM_ID
        description: "Farm identifier (FARM_000000 through FARM_000003)"
        data_type: TEXT
      
      - name: SPECIES
        description: "Animal species: Beef Cattle, Chickens, Pigs, or Goats"
        data_type: TEXT
      
      - name: BREED
        description: "Specific breed of animal"
        data_type: TEXT
      
      - name: AGE
        description: "Age in months"
        data_type: NUMBER
      
      - name: WEIGHT
        description: "Weight in pounds (or ounces for chickens)"
        data_type: NUMBER
      
      - name: HEALTH_STATUS
        description: "Current health status: Healthy, Injured, Sick, etc."
        data_type: TEXT
      
      - name: VACCINATION_HISTORY
        description: "Vaccination records with dates and types"
        data_type: TEXT
      
      - name: MEDICATION_HISTORY
        description: "Medication treatment records (Current, Previous, None)"
        data_type: TEXT
      
      - name: TEMPERATURE
        description: "Environmental temperature in Fahrenheit"
        data_type: NUMBER
      
      - name: HUMIDITY
        description: "Environmental humidity percentage"
        data_type: NUMBER
    
    filters:
      - name: "By Farm"
        description: "Filter by specific farm ID"
        synonyms: ["farm", "location", "site"]
      
      - name: "By Species"
        description: "Filter by animal species"
        synonyms: ["animal type", "livestock type", "species"]
      
      - name: "By Health Status"
        description: "Filter by health condition"
        synonyms: ["health", "condition", "status"]
```

### Step 4: Upload Semantic View to Snowflake

**Option A: Via Snowflake UI (Recommended)**

1. **Navigate to Snowsight UI**
   - Go to https://app.snowflake.com/
   - Select your account and login

2. **Create Stage for YAML File**
   ```sql
   CREATE OR REPLACE STAGE YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS;
   ```

3. **Upload YAML File**
   - Go to: Data > Databases > YOUR_DATABASE > YOUR_SCHEMA > Stages
   - Click on `SEMANTIC_VIEWS` stage
   - Click "+ Files" button
   - Upload `agr_livestock_semantic_view.yaml`

4. **Verify Upload**
   ```sql
   LIST @YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS;
   ```

**Option B: Via SnowSQL CLI**

```bash
# Upload YAML file
snowsql -a YOUR_ACCOUNT -u YOUR_USERNAME \
  -q "PUT file://agr_livestock_semantic_view.yaml @YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS;"

# Verify upload
snowsql -a YOUR_ACCOUNT -u YOUR_USERNAME \
  -q "LIST @YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS;"
```

---

## Agent Configuration via UI

### Step 5: Create Cortex Agent in Snowflake UI

1. **Navigate to Cortex Agents**
   - In Snowsight, go to **AI & ML** > **Cortex** > **Agents**
   - Click **+ Agent** button

2. **Configure Agent Basic Info**
   - **Name**: `LIVESTOCK_HEALTH_GUARDIAN_AGENT` (or your choice)
   - **Database**: Select your database (e.g., `YOUR_DATABASE`)
   - **Schema**: Select your schema (e.g., `YOUR_SCHEMA`)
   - **Model**: Select `llama3.3-70b` (recommended for complex reasoning)

3. **Add Cortex Analyst Tool**
   - Click **+ Add Tool**
   - Select **Cortex Analyst**
   - **Tool Name**: `Analyst1` (or your choice)
   - **Semantic View**: Select the YAML file you uploaded
     - Path should be: `@YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS/agr_livestock_semantic_view.yaml`

4. **Configure Agent Instructions**

   **System Instructions:**
   ```
   You are a livestock health expert analyzing weather impacts on farm animals. 
   Use your Cortex Analyst tool to query the AGR_RECORDS table for current 
   livestock health data and provide data-driven risk assessments based on 
   weather forecasts.
   ```

   **Response Instructions:**
   ```
   When analyzing weather impacts on livestock:
   1. Query AGR_RECORDS to get current health status for the specified farms
   2. Identify animals at elevated risk based on their current condition
   3. Provide specific, actionable recommendations with timeframes
   4. Reference historical patterns when available
   5. Format your response with clear sections as requested
   ```

5. **Save Agent**
   - Click **Save** button
   - Note the agent name for use in connector configuration

### Step 6: Test Agent in UI (Optional but Recommended)

Before using the agent via REST API, test it in the Snowflake UI:

```
Test Query:
"Analyze current livestock health for FARM_000000 and FARM_000001. 
Which animals are most vulnerable to cold weather based on their 
current health status?"
```

**Expected Response:**
- Should query AGR_RECORDS table
- Should identify injured animals and those with overdue vaccinations
- Should provide species-specific recommendations
- Should reference current health data from the table

---

## Connector Integration

### Step 7: Update connector.py with Your Settings

The connector uses the **Cortex Agent REST API**, which requires you to update the semantic view path in the code.

**In the constants section of the `connector.py`, change the __SEMANTIC_VIEW_PATH:**

```python
__SEMANTIC_VIEW_PATH = "HOL_DATABASE.AGR_0729_CLAUDE.AGR_LIVESTOCK_OVERALL_PERFORMANCE_SV"
```

**Replace with your actual path:**

```python
__SEMANTIC_VIEW_PATH = "YOUR_DATABASE.YOUR_SCHEMA.YOUR_SEMANTIC_VIEW_NAME"
```

**Important Notes:**
- The REST API doesn't use the UI-created agent by name
- It dynamically constructs the agent configuration in each request
- You must update the semantic view path to match your setup
- The tool name (`Analyst1`) can be anything, but must match between `tools` and `tool_resources`

### Step 8: Configure connector settings

In your `configuration.json`:

```json
{
  "zip_codes": "77429,77856,81611",
  "user_agent": "LivestockWeatherIntelligence/1.0 (your-email@example.com)",
  "farm_zip_mapping": "77429:FARM_000000,FARM_000001|77856:FARM_000002|81611:FARM_000003",
  "enable_cortex_enrichment": "true",
  "snowflake_account": "YOUR_ACCOUNT.REGION.snowflakecomputing.com",
  "snowflake_pat_token": "ver:1-hint:YOUR_TOKEN_HERE",
  "cortex_timeout": "60",
  "max_enrichments": "5"
}
```

---

## Testing Your Setup

### Step 9: Test the Complete Pipeline

```bash
# Test with local debug
fivetran debug --configuration configuration.json

# Expected output:
# ✓ Enriched forecast for 77429 This Afternoon
# ✓ Enriched forecast for 77429 Tonight
# Sync complete: 42 forecasts from 3 ZIP codes, 5 enriched
```

### Step 10: Verify Data in Snowflake

```sql
-- Check if data arrived
SELECT COUNT(*) 
FROM YOUR_DESTINATION_SCHEMA.LIVESTOCK_WEATHER_INTELLIGENCE;

-- View enriched records
SELECT 
    zip_code,
    place_name,
    period_name,
    temperature,
    agent_livestock_risk_assessment,
    agent_affected_farms,
    agent_recommended_actions
FROM YOUR_DESTINATION_SCHEMA.LIVESTOCK_WEATHER_INTELLIGENCE
WHERE agent_livestock_risk_assessment != 'No assessment available'
LIMIT 5;
```

### Step 11: Validate AI Enrichments

Check that enriched records have meaningful data:

```sql
-- Should see real analysis, not defaults
SELECT 
    agent_livestock_risk_assessment,
    agent_affected_farms,
    agent_species_risk_matrix,
    agent_recommended_actions
FROM YOUR_DESTINATION_SCHEMA.LIVESTOCK_WEATHER_INTELLIGENCE
WHERE agent_livestock_risk_assessment NOT LIKE '%No assessment%'
LIMIT 1;
```

**Good indicators:**
- ✅ Risk assessment mentions specific conditions and animals
- ✅ Affected farms lists actual FARM_IDs (not empty array)
- ✅ Species risk matrix has multiple species with risk levels
- ✅ Recommendations are specific with timeframes (not generic defaults)

---

## Troubleshooting

### Common Issues

#### Issue 1: "Semantic view not found"

**Symptoms:**
- 400 Bad Request from Cortex Agent API
- Error message mentions semantic view

**Solutions:**
1. Verify YAML file is uploaded to stage:
   ```sql
   LIST @YOUR_DATABASE.YOUR_SCHEMA.SEMANTIC_VIEWS;
   ```

2. Check semantic view path in connector.py matches exactly:
   ```python
   "semantic_view": "YOUR_DATABASE.YOUR_SCHEMA.YOUR_SEMANTIC_VIEW_NAME"
   ```

3. Verify user has SELECT permission on AGR_RECORDS:
   ```sql
   SHOW GRANTS ON TABLE YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS;
   ```

#### Issue 2: "Empty agent responses"

**Symptoms:**
- Connector runs successfully
- All records have default messages like "No assessment available"

**Solutions:**
1. Check farm IDs in `farm_zip_mapping` match AGR_RECORDS:
   ```sql
   SELECT DISTINCT FARM_ID 
   FROM YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS 
   ORDER BY FARM_ID;
   ```

2. Verify `max_enrichments` > 0 in configuration.json

3. Check `enable_cortex_enrichment` is string `"true"` not boolean

4. Increase `cortex_timeout` from 60 to 90 or 120 seconds

5. Test agent in Snowflake UI first to confirm it works

#### Issue 3: "401 Unauthorized"

**Symptoms:**
- Authentication error from Snowflake

**Solutions:**
1. Verify PAT token is valid:
   - Go to Snowflake UI > Profile > Account Settings > Security > Personal Access Tokens
   - Check token hasn't expired
   - Generate new token if needed

2. Check token format starts with `ver:1-hint:`

3. Verify Snowflake account URL includes region:
   ```
   Correct: abc12345.us-west-2.snowflakecomputing.com
   Wrong: abc12345.snowflakecomputing.com
   ```

#### Issue 4: "Agent timeout"

**Symptoms:**
- Connector logs: "Agent timeout after 60s for ZIP ..."
- Some enrichments succeed, others timeout

**Solutions:**
1. Increase timeout in configuration.json:
   ```json
   "cortex_timeout": "120"
   ```

2. Check Snowflake warehouse is running and has capacity

3. Consider optimizing semantic view or adding indexes to AGR_RECORDS:
   ```sql
   CREATE INDEX idx_farm_id ON YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS(FARM_ID);
   CREATE INDEX idx_species ON YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS(SPECIES);
   ```

4. Reduce number of farms per ZIP in `farm_zip_mapping`

#### Issue 5: "No data returned from Cortex Analyst"

**Symptoms:**
- Agent responds but doesn't include query results
- Generic responses without specific data

**Solutions:**
1. Test the semantic view directly:
   ```sql
   -- This should work if semantic view is correct
   SELECT * FROM YOUR_DATABASE.YOUR_SCHEMA.AGR_RECORDS 
   WHERE FARM_ID = 'FARM_000000';
   ```

2. Verify YAML column names match table exactly (case-sensitive)

3. Check YAML `base_table` section has correct database/schema/table

4. Ensure data exists for the farms in your `farm_zip_mapping`

### Getting Help

If issues persist:

1. **Check Connector Logs**: Review full output from `fivetran debug`
2. **Test Components Separately**:
   - Test weather API calls work (disable enrichment)
   - Test agent in Snowflake UI first
   - Test PAT token with simple REST call
3. **Review Documentation**:
   - [Snowflake Cortex Agents REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api)
   - [Cortex Analyst Semantic Model](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec)
4. **Open GitHub Issue**: Include logs, configuration (scrub credentials), and error messages

---

## Next Steps

Once your setup is working:

1. **Expand Coverage**: Add more ZIP codes and farms to `configuration.json`
2. **Optimize Costs**: Adjust `max_enrichments` based on your needs
3. **Schedule Syncs**: Set up regular sync schedule in Fivetran (every 12-24 hours)
4. **Monitor Usage**: Track Cortex Agent API usage and costs in Snowflake
5. **Enhance Data**: Add more livestock data to AGR_RECORDS for richer analysis

## Additional Resources

- **Fivetran Connector SDK**: https://fivetran.com/docs/connector-sdk
- **Snowflake Cortex Agents**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
- **Cortex Analyst**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
- **National Weather Service API**: https://www.weather.gov/documentation/services-web-api
