# FHIR R4 Healthcare Intelligence Connector Example

## Connector overview

This connector syncs clinical data from a FHIR R4 server and enriches it with AI-powered hybrid analysis using Databricks `ai_query()`. It implements the Hybrid pattern (Discovery + Debate) to provide population health risk stratification and per-patient intervention recommendations.

The connector fetches Patient, Condition, Observation, and MedicationRequest resources from any FHIR R4-compliant server, then applies two AI enrichment phases: a Discovery phase that analyzes the patient cohort to identify at-risk populations, and a Debate phase where a Clinical Risk Analyst and a Resource Allocation Analyst debate intervention priorities for each patient, producing a consensus intervention level with a disagreement flag.

Optionally, the connector can create a [Genie Space in Databricks](https://docs.databricks.com/aws/en/genie/) for natural language clinical analytics.

## Accreditation

This connector was built by David Millman during a working session with Kelly Kohlleffel. It follows the Hybrid (Discovery + Debate) pattern established by the [NOAA Weather Risk Intelligence connector](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/tutorials/databricks-fm-noaa-weather-risk-intelligence) and the [FDA FAERS Pharmacovigilance Intelligence connector](https://github.com/fivetran/connector_sdk/tree/main/all_things_ai/tutorials/databricks-fm-fda-faers-pv-intelligence). The HAPI FHIR public test server (`https://hapi.fhir.org/baseR4`) is used as the default data source and contains synthetic clinical data suitable for demonstration purposes.

## Requirements

- [Supported Python versions](https://github.com/fivetran/connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- Databricks workspace with a SQL warehouse and Foundation Model API access (required if AI enrichment is enabled)
- Access to a FHIR R4 server (default: HAPI FHIR public test server, no credentials required)

## Getting started

Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connector-sdk/setup-guide) to get started.

To initialize a new Connector SDK project using this connector as a starting point, run:

```bash
fivetran init --template all_things_ai/tutorials/databricks-fm-fhir-healthcare-intelligence
```

`fivetran init` initializes a new Connector SDK project by setting up the project structure, configuration files, and a connector you can run immediately with `fivetran debug`.
If you do not specify a project path, Fivetran creates the project in your current directory.
For more information on `fivetran init`, refer to the [Connector SDK `init` documentation](https://fivetran.com/docs/connector-sdk/setup-guide#createyourcustomconnector).

> Note: Ensure you have updated the `configuration.json` file with the necessary parameters before running `fivetran debug`. See the [Configuration file](#configuration-file) section for details on the required configuration parameters.

## Features

- Fetches Patient, Condition, Observation, and MedicationRequest resources from any FHIR R4-compliant server
- Supports optional ICD-10 code prefix filtering to target a specific patient cohort (e.g., `E11` for diabetes)
- Supports incremental sync using FHIR `_lastUpdated` filtering based on the previous sync timestamp
- Discovery phase: calls Databricks `ai_query()` to identify at-risk populations, dominant conditions, and recommended screenings across the cohort
- Debate phase: for each patient, a Clinical Risk Analyst and a Resource Allocation Analyst independently assess the patient, then a Consensus Agent synthesizes a final intervention level with a disagreement flag
- Produces eight destination tables: four FHIR resource tables and four AI enrichment tables
- Optional Genie Space creation in Databricks for natural language clinical analytics

## Configuration file

The `configuration.json` file contains the following parameters:

```json
{
  "fhir_base_url": "<FHIR_BASE_URL>",
  "databricks_workspace_url": "<DATABRICKS_WORKSPACE_URL>",
  "databricks_token": "<DATABRICKS_TOKEN>",
  "databricks_warehouse_id": "<DATABRICKS_WAREHOUSE_ID>",
  "databricks_model": "<DATABRICKS_MODEL_NAME>",
  "enable_enrichment": "<TRUE_OR_FALSE_DEFAULT_TRUE>",
  "enable_discovery": "<TRUE_OR_FALSE_DEFAULT_TRUE>",
  "enable_genie_space": "<TRUE_OR_FALSE_DEFAULT_FALSE>",
  "genie_table_identifier": "<CATALOG.SCHEMA.TABLE>",
  "max_patients": "<MAX_PATIENTS_PER_SYNC>",
  "max_enrichments": "<MAX_ENRICHMENTS_PER_SYNC>",
  "condition_filter": "<ICD10_CODE_PREFIX>",
  "databricks_timeout": "<DATABRICKS_TIMEOUT_SECONDS>"
}
```

| Parameter | Description | Required | Default |
|---|---|---|---|
| `fhir_base_url` | Base URL of the FHIR R4 server | No | `https://hapi.fhir.org/baseR4` |
| `databricks_workspace_url` | Databricks workspace URL, including `https://` | Yes, if enrichment is enabled | None |
| `databricks_token` | Databricks Personal Access Token | Yes, if enrichment is enabled | None |
| `databricks_warehouse_id` | Databricks SQL warehouse ID | Yes, if enrichment is enabled | None |
| `databricks_model` | Databricks Foundation Model name | No | `databricks-claude-sonnet-4-6` |
| `enable_enrichment` | Enable AI enrichment phases | No | `true` |
| `enable_discovery` | Enable Discovery phase | No | `true` |
| `enable_genie_space` | Create Databricks Genie Space | No | `false` |
| `genie_table_identifier` | Genie Space table identifier in `catalog.schema.table` format | Yes, if Genie is enabled | None |
| `max_patients` | Maximum patients to sync per run | No | `20` |
| `max_enrichments` | Maximum patients to enrich per run | No | `5` |
| `condition_filter` | ICD-10 code prefix to filter patients, such as `E11` | No | None |
| `databricks_timeout` | Databricks API timeout in seconds | No | `120` |

> Note: When submitting connector code as a [Community Connector](https://github.com/fivetran/connector_sdk/tree/main/connectors) or enhancing an [example](https://github.com/fivetran/connector_sdk/tree/main/examples) in the open-source [Connector SDK repository](https://github.com/fivetran/connector_sdk/tree/main), ensure the `configuration.json` file has placeholder values.
When adding the connector to your production repository, ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Authentication

The FHIR R4 data source uses no authentication by default. The HAPI FHIR public test server (`https://hapi.fhir.org/baseR4`) is an open server that requires no credentials. If you configure a private FHIR server that requires authentication, add the appropriate authorization header to the session in `connector.py`.

Databricks authentication uses a Personal Access Token (PAT). Generate a PAT from your Databricks workspace under Settings > Developer > Access tokens, then set it as the `databricks_token` configuration value. The token is passed as a `Bearer` token in the `Authorization` header for all Databricks SQL Statement API calls.

## Pagination

FHIR R4 servers return resources as paginated Bundle resources. The connector follows `Bundle.link` entries with `relation=next` to retrieve subsequent pages until no next link is present or the configured `max_patients` limit is reached. The next-page URL is used directly as provided by the server; query parameters are only passed on the initial request.

Databricks SQL Statement API responses can be paginated via `next_chunk_internal_link`, but this tutorial connector reads the immediate `ai_query()` result only and does not follow chunk-pagination links. The included AI queries return a single result value rather than a large multi-row result set.

## Data handling

FHIR resources use deeply nested JSON structures (CodeableConcept, Reference, Quantity, HumanName). The connector normalizes these using dedicated extraction helpers:

- `extract_codeable_concept()` - extracts the first code and display text from a CodeableConcept
- `extract_reference_id()` - extracts the resource ID from a FHIR Reference string
- `extract_quantity()` - extracts the numeric value and unit from a Quantity

All remaining nested dictionaries are flattened using `flatten_dict()` before upsert. Arrays and lists are serialized to JSON strings. AI enrichment fields that return JSON arrays (e.g., `dominant_conditions`, `immediate_actions`) are stored as JSON strings in the destination.

## Error handling

FHIR API requests are retried up to 3 times with exponential backoff for status codes 429, 500, 502, 503, and 504. Authentication errors (401, 403) are not retried and raise an immediate error with a credential check message.

Databricks `ai_query()` calls retry the initial POST up to 3 times with exponential backoff for status codes 429, 500, 502, 503, and 504. If all retry attempts fail, or if the statement returns a final FAILED state, that patient's assessment is skipped and a warning is logged, but the sync continues. Checkpoints are written after each patient debate and after each enrichment phase so that progress is not lost if a sync is interrupted.

## Tables created

The connector creates the following tables in the destination:

### Patients

The `patients` table consists of the following columns:

| Column | Description |
|---|---|
| `patient_id` | Unique FHIR Patient resource ID (primary key) |
| `mrn` | Medical record number from identifier |
| `given_name` | Patient first name |
| `family_name` | Patient last name |
| `gender` | Administrative gender |
| `birth_date` | Date of birth (YYYY-MM-DD) |
| `deceased_boolean` | True if patient is deceased |
| `deceased_date_time` | Date and time of death if applicable |
| `marital_status` | Marital status display text |
| `language` | Preferred communication language |
| `address_line` | Street address |
| `city` | City |
| `state` | State or province |
| `postal_code` | Postal code |
| `country` | Country |
| `active` | Whether the patient record is active |
| `last_updated` | FHIR resource last updated timestamp |

### Conditions

The `conditions` table consists of the following columns:

| Column | Description |
|---|---|
| `condition_id` | Unique FHIR Condition resource ID (primary key) |
| `patient_id` | Reference to the patient |
| `code` | ICD-10 or SNOMED condition code |
| `display` | Human-readable condition name |
| `code_system` | Coding system URI |
| `category` | Condition category code |
| `clinical_status` | active, resolved, inactive |
| `verification_status` | confirmed, unconfirmed, refuted |
| `onset_date` | Date condition began |
| `abatement_date` | Date condition resolved |
| `recorded_date` | Date condition was recorded |
| `last_updated` | FHIR resource last updated timestamp |

### Observations

The `observations` table consists of the following columns:

| Column | Description |
|---|---|
| `observation_id` | Unique FHIR Observation resource ID (primary key) |
| `patient_id` | Reference to the patient |
| `code` | LOINC observation code |
| `display` | Human-readable observation name |
| `code_system` | Coding system URI |
| `category` | Observation category (laboratory, vital-signs) |
| `value` | Observation result value |
| `value_unit` | Unit of measure |
| `status` | final, preliminary, amended |
| `effective_date` | Date observation was made |
| `issued` | Date result was issued |
| `interpretation` | Normal, High, Low, Critical |
| `reference_range_low` | Lower bound of normal range |
| `reference_range_high` | Upper bound of normal range |
| `last_updated` | FHIR resource last updated timestamp |

### Medications

The `medications` table consists of the following columns:

| Column | Description |
|---|---|
| `medication_id` | Unique FHIR MedicationRequest resource ID (primary key) |
| `patient_id` | Reference to the patient |
| `medication_code` | RxNorm or NDC medication code |
| `medication_display` | Human-readable medication name |
| `medication_system` | Coding system URI |
| `status` | active, completed, stopped |
| `intent` | order, plan, proposal |
| `authored_on` | Date prescription was written |
| `dosage_text` | Free-text dosage instructions |
| `dosage_timing` | Dosage timing details (JSON) |
| `dosage_route` | Route of administration |
| `last_updated` | FHIR resource last updated timestamp |

### Population insights

The `population_insights` table consists of the following columns:

| Column | Description |
|---|---|
| `insight_id` | Unique insight identifier (primary key) |
| `condition_filter` | ICD-10 prefix used to filter cohort, or "none" |
| `patient_count` | Number of patients analyzed |
| `dominant_conditions` | Most prevalent conditions in cohort (JSON array) |
| `risk_factors` | Key risk factors identified (JSON array) |
| `high_risk_indicators` | Summary of high-risk indicators |
| `recommended_screenings` | Preventive screenings recommended (JSON array) |
| `comorbidities_to_investigate` | Comorbidities flagged for investigation (JSON array) |
| `population_risk_summary` | Narrative population risk summary |

### Clinical assessments

The `clinical_assessments` table consists of the following columns:

| Column | Description |
|---|---|
| `patient_id` | Reference to the patient (primary key) |
| `assessment_type` | Always "clinical" |
| `clinical_risk_score` | Risk score 1-10 (urgency-maximizing) |
| `worst_case_scenario` | Description of worst-case clinical outcome |
| `intervention_recommendation` | INPATIENT_CARE_MGMT, OUTPATIENT_INTENSIFY, TELEHEALTH, or ROUTINE |
| `immediate_actions` | Immediate actions recommended (JSON array) |
| `complication_risks` | Complication risks identified (JSON array) |
| `reasoning` | Clinical analyst reasoning narrative |

### Resource assessments

The `resource_assessments` table consists of the following columns:

| Column | Description |
|---|---|
| `patient_id` | Reference to the patient (primary key) |
| `assessment_type` | Always "resource" |
| `resource_risk_score` | Risk score 1-10 (proportional) |
| `expected_risk` | Probability-weighted expected risk description |
| `intervention_recommendation` | INPATIENT_CARE_MGMT, OUTPATIENT_INTENSIFY, TELEHEALTH, or ROUTINE |
| `cost_effective_actions` | Cost-effective actions recommended (JSON array) |
| `mitigating_factors` | Factors that reduce risk (JSON array) |
| `reasoning` | Resource analyst reasoning narrative |

### Debate consensus

The `debate_consensus` table consists of the following columns:

| Column | Description |
|---|---|
| `patient_id` | Reference to the patient (primary key) |
| `assessment_type` | Always "consensus" |
| `intervention_level` | Final intervention: INPATIENT_CARE_MGMT, OUTPATIENT_INTENSIFY, TELEHEALTH, or ROUTINE |
| `consensus_risk_score` | Balanced risk score 1-10 |
| `debate_winner` | CLINICAL, RESOURCE, or DRAW |
| `winner_rationale` | Why one analyst was more persuasive |
| `agreement_areas` | Areas of analyst agreement (JSON array) |
| `disagreement_areas` | Areas of analyst disagreement (JSON array) |
| `disagreement_flag` | True if analysts significantly disagreed |
| `disagreement_severity` | NONE, MINOR, SIGNIFICANT, or FUNDAMENTAL |
| `recommended_next_step` | Recommended immediate next step |
| `executive_summary` | Narrative summary of the debate consensus |

## Additional considerations


The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
