# Rydlr MotionBlend Connector Example

## Connector overview
The MotionBlend connector catalogs motion-capture (MoCap) file inventory from Google Cloud Storage (GCS) and delivers it to BigQuery for downstream transformation and analytics. It scans folders containing `.bvh` and `.fbx` files, extracts GCS blob metadata (file URIs, update timestamps, and file sizes), and loads this file catalog into BigQuery.

This connector supports three motion categories – `seed_motions`, `build_motions`, and `blend_motions` – and is designed for AI and animation pipelines that analyze or generate blended human motion sequences.

Current limitations:
- Motion-specific metadata (frame count, FPS, joint counts, skeleton IDs) use static placeholder values
- Quality metrics in blend records are set to NULL and require post-processing
- File contents are not parsed; only GCS blob metadata (URI, timestamps, size) is extracted
- Suitable for building a file catalog and tracking file locations; full metadata extraction requires additional processing steps

Typical use cases include:
- Motion analytics for animation and gaming studios
- Behavior modeling for robotics and simulation
- Training data pipelines for large motion-blend models (e.g., MotionBlendAI)
- Centralizing motion capture assets from distributed storage into a data warehouse
- Supporting downstream dbt transformations for motion blend analytics

## Accreditation
This example was contributed by Ted Iro, [Rydlr Cloud Services Ltd](https://github.com/RydlrCS).

## Requirements
- [Supported Python versions](https://github.com/fivetran/fivetran_connector_sdk/blob/main/README.md#requirements)
- Operating system:
  - Windows: 10 or later (64-bit only)
  - macOS: 13 (Ventura) or later (Apple Silicon [arm64] or Intel [x86_64])
  - Linux: Distributions such as Ubuntu 20.04 or later, Debian 10 or later, or Amazon Linux 2 or later (arm64 or x86_64)
- Google Cloud Platform account with GCS bucket access (Storage Object Viewer role)

## Getting started
Refer to the [Connector SDK Setup Guide](https://fivetran.com/docs/connectors/connector-sdk/setup-guide) to get started.

## Features
- Lists and catalogs motion-capture files from GCS
- Normalizes file inventory into three logical streams: `seed_motions`, `build_motions`, `blend_motions`
- Incremental sync using blob `updated` timestamps to process only new or modified files
- Batch-local state tracking prevents data loss when files arrive out of chronological order
- Stable record IDs using GCS object identifiers (persists across file renames/moves)
- Exponential backoff retry logic (max 3 attempts) for transient GCS failures
- Checkpointing every 100 records for fault tolerance on large datasets
- Bounded buffering (1000 files per batch) prevents out-of-memory errors
- SDK-based structured logging with runtime warnings for testing parameters
- Configurable batch limit for development testing (logs warning, not for production use)
- Robust validation for configuration parameters (empty strings, type checks, range validation)

## Configuration file
`configuration.json` defines the connector parameters uploaded to Fivetran.

```json
{
  "google_cloud_storage_bucket": "<YOUR_GCS_BUCKET_NAME>",
  "google_cloud_storage_prefixes": "<YOUR_COMMA_SEPARATED_PREFIXES>",
  "batch_limit": "<YOUR_OPTIONAL_BATCH_LIMIT>",
  "include_extensions": "<YOUR_OPTIONAL_FILE_EXTENSIONS>",
  "max_blend_pairs": "<YOUR_OPTIONAL_MAX_BLEND_PAIRS>",
  "max_motion_buffer_size": "<YOUR_OPTIONAL_MAX_BUFFER_SIZE>"
}
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `google_cloud_storage_bucket` | Yes | N/A | GCS bucket name containing motion files |
| `google_cloud_storage_prefixes` | Yes | N/A | Comma-separated list of prefixes to scan (e.g., `mocap/seed/,mocap/build/`) |
| `batch_limit` | No | None (unlimited) | **TESTING ONLY** – Maximum number of files to process per prefix per sync. Omit for production to process all files. When configured, connector logs a warning at runtime. State is updated with the last processed file's timestamp and remaining files are processed in subsequent syncs. May cause incomplete syncs if new files arrive during processing. |
| `include_extensions` | No | <YOUR_OPTIONAL_FILE_EXTENSIONS> | File extensions to process (comma-separated) |
| `max_blend_pairs` | No | <YOUR_OPTIONAL_MAX_BLEND_PAIRS> | Maximum number of blend pairs to generate per sync |
| `max_motion_buffer_size` | No | <YOUR_OPTIONAL_MAX_BUFFER_SIZE> | Maximum number of seed/build motions to buffer before generating blend pairs |

Note: Ensure that the `configuration.json` file is not checked into version control to protect sensitive information.

## Requirements file
`requirements.txt` lists third-party Python dependencies used by the connector.

Example content:
```
google-cloud-storage==2.18.2
```

Key dependencies:
- `google-cloud-storage` – GCS client for blob iteration and file discovery

Note: The `fivetran_connector_sdk:latest` and `requests:latest` packages are pre-installed in the Fivetran environment. To avoid dependency conflicts, do not declare them in your `requirements.txt`.

## Authentication
This connector uses Google Cloud Application Default Credentials (ADC) for GCS authentication. The connector initializes the GCS client as `storage.Client()` without explicit credentials, relying on the runtime environment to provide authentication.

### Local development
Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to point to your service account JSON key:

```bash
# Create service account with required permissions
gcloud iam service-accounts create motionblend-connector \
  --display-name="MotionBlend Connector"

# Grant Storage Object Viewer role for GCS read access
gcloud projects add-iam-policy-binding YOUR_PROJECT \
  --member="serviceAccount:motionblend-connector@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Download service account key
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=motionblend-connector@YOUR_PROJECT.iam.gserviceaccount.com

# Set environment variable for local testing
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
```

### Fivetran deployment
When deploying to Fivetran, credentials must be configured through the Fivetran platform:

1. In the Fivetran connector setup UI, provide the service account JSON key content in the designated credentials field
2. Fivetran will inject these credentials into the runtime environment as ADC
3. The connector will automatically discover and use these credentials via `storage.Client()`

Note: The connector does not accept credentials via `configuration.json`. All authentication is handled through Fivetran's secure credential management system.

### Required permissions
The service account needs the following IAM role:
- `roles/storage.objectViewer` - Read access to GCS buckets and objects

## Pagination
The connector uses streaming iteration for GCS objects with configurable batching. It iterates through GCS object listings with a configurable limit (`batch_limit`). See `list_gcs_files()` function in `connector.py`.

The connector implements:
- Lazy iteration using `storage.Client().bucket().list_blobs(prefix=prefix)` iterator
- No pagination tokens required; processes blobs as they are discovered
- Configurable `limit` parameter for testing (processes first N files per prefix)
- Filters out directories (names ending with `/`) and non-BVH/FBX files

Important - Testing Only: The `batch_limit` parameter limits how many files are processed per prefix per sync. When the limit is reached:
- State is updated with the last processed file's timestamp
- Next sync will resume from that point and process the next batch
- This is ONLY for testing/development to avoid processing large datasets during development
- Production use: Remove `batch_limit` entirely or set to a very high value

For incremental sync, the connector tracks cursors in the `update()` function by recording the `updated_at` timestamp from each successfully processed file in the main processing loop.

## Data handling
Files are discovered via GCS API, cataloged with blob metadata, and streamed to the destination via Fivetran operations. Each stream (seed/build/blend) maps to its own table (refer to `transform_seed_record()`, `transform_build_record()`, and `transform_blend_record()` functions in `connector.py`).

Schemas are defined in the `schema()` function and correspond to the table definitions below. Date fields are UTC ISO-8601 strings.

### Record ID Generation Strategy

The connector uses stable GCS object identifiers to generate record IDs, ensuring data integrity across file renames and reorganizations:

ID Generation Logic (`generate_record_id()` function):
- Primary: Uses GCS `blob.id` (format: `bucket/object/generation`)
  - Stable across file path changes (renames, moves within bucket)
  - Unique per object version (immutable)
  - Recommended for production use
- Fallback: SHA-1 hash of `file_uri` (when GCS ID unavailable)
  - Legacy compatibility mode
  - Caveat: File renames/moves create new IDs and duplicate records

Behavior Examples:
```
# File remains at same path
gs://bucket/motions/walk.bvh (generation 123) → ID: a1b2c3d4e5f6g7h8
gs://bucket/motions/walk.bvh (generation 123) → ID: a1b2c3d4e5f6g7h8 ✓ Same ID

# File renamed/moved (with GCS ID available)
gs://bucket/motions/walk.bvh (generation 123) → ID: a1b2c3d4e5f6g7h8
gs://bucket/archive/walk_v1.bvh (generation 123) → ID: a1b2c3d4e5f6g7h8 ✓ Same ID

# File content updated (new version)
gs://bucket/motions/walk.bvh (generation 123) → ID: a1b2c3d4e5f6g7h8
gs://bucket/motions/walk.bvh (generation 456) → ID: x9y8z7w6v5u4t3s2 ✓ New ID (new content)
```

Blend Motions ID Strategy:
- Blend pairs: SHA-1 hash of both motion URIs concatenated (`left_uri|right_uri`)
  - Stable for specific blend combinations
  - Independent of blend result file location
  - Generated by `blend_utils.generate_blend_id()`
- File-based records: Uses standard `generate_record_id()` with GCS object ID
  - For cataloging individual blend result files
  - `left_motion_id` and `right_motion_id` set to NULL

Important Notes:
- GCS object IDs are only available when files are accessed via GCS API
- Files uploaded as new objects (even with same name) get new generation numbers
- For immutable datasets where renames are rare, file_uri-based IDs are acceptable
- Downstream systems should treat record IDs as opaque stable identifiers

Data Transformation Pipeline:
1. Extract (`list_gcs_files()` function) – List blobs from GCS, filter by file extension, yield GCS metadata:
   - Actual extracted data: `file_uri`, `updated_at` (from GCS blob), `size`, `name`, `gcs_id`, `gcs_generation`
   - Not extracted: File contents are not parsed; motion-specific metadata is not extracted
2. Transform (transform functions) – Normalize records based on category:
   - Generate stable deterministic ID using GCS object identifier (`generate_record_id()` function)
     - Primary: Uses GCS `blob.id` (stable across file renames/moves)
     - Fallback: SHA-1 hash of file_uri if GCS ID unavailable (legacy compatibility)
   - ID stability: File renames/moves do not create duplicate records when GCS object ID is available
   - Insert STATIC placeholder values (not extracted from file contents):
     - `skeleton_id`: "mixamo24" (hardcoded constant)
     - `fps`: 30 (hardcoded constant)
     - `joints_count`: 24 (hardcoded constant)
     - `frames`: 0 (hardcoded constant)
     - `build_method`: "ganimator" for build_motions (hardcoded constant)
   - Preserve actual GCS blob metadata: file URIs, timestamps, file sizes
   - Quality metrics (blend_quality, transition_smoothness) are set to NULL
3. Load (`update()` function) – Upsert records to destination:
   - Files are collected in bounded batches (1000 files per batch) and sorted by `updated_at` timestamp before processing
   - Chronological sorting prevents data loss: even if connector fails mid-sync, next sync resumes from last processed timestamp
   - Tables are automatically created by Fivetran based on schema definition
   - Uses `op.upsert()` operation for inserting/updating records
   - State is updated after each successful upsert with that file's timestamp
   - Checkpoints state every 100 records and after each prefix completes
   - Memory safety: Bounded buffering (1000 files per batch) prevents out-of-memory errors for large GCS prefixes

State Management & Data Loss Prevention:
- Files are collected in bounded batches (1000 files per batch) and sorted by `updated_at` timestamp before processing (chronological order within batch)
- State tracks the timestamp of the last successfully processed file **within the current batch** (batch-local tracking)
- If connector fails mid-sync, next run resumes from last successful file timestamp
- Chronological sorting within batches ensures data integrity for incremental sync
- Example: Batch 1 processes files A (Jan 10), C (Jan 12), B (Jan 15) → sorted to A, C, B → state = Jan 15 after batch completion
- Critical: State updates sequentially as files are processed, not based on global maximum across all batches
- This prevents data loss when files arrive out of chronological order across different batches
- Memory safety: Bounded buffering (1000 files per batch) prevents out-of-memory errors while maintaining processing order
- Checkpointing: State is saved every 100 records and after each batch completes for fault tolerance

Data Accuracy:
- ✅ Accurate: File URIs, GCS update timestamps, file names, file sizes, GCS object IDs
- ⚠️ STATIC placeholders (not extracted): Frame counts (0), FPS (30), skeleton IDs ("mixamo24"), joint counts (24), build_method ("ganimator")
- ❌ Not extracted: Actual motion data requires parsing BVH/FBX file contents (frames, actual FPS, skeleton structure)

Blend Metadata Calculation (blend_utils):
When motion pairs are provided to `transform_blend_record()` with `left_motion` and `right_motion` parameters, the connector uses `blend_utils.create_blend_metadata()` to calculate:
- `blend_ratio`: Based on motion duration ratios (heuristic)
- `transition_start_frame` / `transition_end_frame`: Calculated from blend ratio and transition window
- `estimated_quality`: Heuristic score based on duration similarity and blend parameters

Important: These calculations use placeholder frame counts (0) from the catalog, so they produce theoretical values. For production-quality blend metadata, you need to:
1. Parse actual BVH/FBX files to extract real frame counts and motion data
2. Use the [blendanim framework](https://github.com/RydlrCS/blendanim) for neural network-based blending
3. Calculate L2 velocity/acceleration metrics on generated motion sequences

Type Conversions:
- File sizes (bytes) → INTEGER
- GCS blob timestamps → UTC ISO-8601 strings

## Error handling
Refer to the `list_gcs_files()` and `update()` functions in `connector.py`.

The connector implements:
- Exponential backoff with retry logic for transient GCS failures
- Specific exception handling for permanent vs. transient errors
- Comprehensive logging using the Fivetran SDK logging module

Retry Logic (refer to `list_gcs_files()` function):
- Exponential backoff: delays of 1s, 2s, 4s (capped at 60s)
- Max attempts: 3 retries before raising RuntimeError
- Retryable errors: Transient GCS/network failures (GoogleAPIError, RetryError, ServerError, ConnectionError, Timeout, HTTPError)
- Non-retryable: Authentication errors (PermissionDenied, Unauthenticated), invalid requests (NotFound, ValueError)

Error Categories:
1. Transient errors – Retried with exponential backoff:
   - `google_exceptions.GoogleAPIError`
   - `google_exceptions.RetryError`
   - `google_exceptions.ServerError`
   - `requests_exceptions.ConnectionError`
   - `requests_exceptions.Timeout`
   - `requests_exceptions.HTTPError`

2. Permanent errors – Fail immediately:
   - `google_exceptions.PermissionDenied`
   - `google_exceptions.Unauthenticated`
   - `google_exceptions.NotFound`
   - `ValueError`

Logging (using Fivetran SDK `log` module throughout):
- `log.info()` – Progress updates and operation completion
- `log.warning()` – Retry attempts, recoverable issues, and testing parameter usage (batch_limit)
- `log.severe()` – Fatal errors and exceptions
- `log.fine()` – Detailed debugging information (category inference, record ID generation)

State Management:
- State updates occur sequentially as files are processed (batch-local tracking)
- Checkpointing every 100 records preserves progress for large datasets
- Files within each batch are sorted chronologically before processing
- This ensures incremental sync correctness even when files arrive out of order across batches
- On failure, next sync resumes from last checkpointed file timestamp

## Tables created

The MotionBlend schema produces three tables in BigQuery:

| Table | Primary Key | Incremental Field | Description |
|-------|-------------|-------------------|-------------|
| `seed_motions` | `id` | `updated_at` | Base motion files providing raw sequences |
| `build_motions` | `id` | `updated_at` | Derived motions built from seeds |
| `blend_motions` | `id` | `updated_at` | Blended motion pairs with transition metadata |

Example schema snippet (`blend_motions`):
```json
{
  "id": "string",
  "left_motion_id": "string",
  "right_motion_id": "string",
  "blend_ratio": "float",
  "transition_start_frame": "integer",
  "transition_end_frame": "integer",
  "file_uri": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

For optimal query performance and cost optimization, we recommend configuring daily partitioning on the `created_at` field in BigQuery. This must be set up in your BigQuery destination; the connector delivers the `created_at` field but does not configure partitioning automatically.

## Additional files
The connector uses the following additional file:
- **blend_utils.py** – Motion blending metadata calculation module

This lightweight Python module calculates blend metadata for motion pairs and provides the following core functions:

- `create_blend_metadata(left_motion, right_motion, transition_frames)` - Generates complete blend record with calculated parameters
- `calculate_blend_ratio(left_duration, right_duration)` - Computes blend ratio based on motion durations  
- `calculate_transition_window(left_frames, right_frames, ratio)` - Determines transition start/end frames
- `estimate_blend_quality(params)` - Heuristic quality score (0.0-1.0) based on motion compatibility
- `generate_blend_id(left_uri, right_uri)` - Deterministic SHA-1 hash for blend pair identification
- `generate_blend_pairs(seed_motions, build_motions, max_pairs)` - Generates blend motion pairs from seed and build motion collections

Example Usage:
```python
from blend_utils import create_blend_metadata

# Input motion records
seed_motion = {'id': 'seed_001', 'file_uri': 'gs://bucket/walk.bvh', 'frames': 150, 'fps': 30}
build_motion = {'id': 'build_001', 'file_uri': 'gs://bucket/run.bvh', 'frames': 180, 'fps': 30}

# Generate blend metadata
blend = create_blend_metadata(seed_motion, build_motion, transition_frames=30)
# Returns: {'id': '...', 'blend_ratio': 0.455, 'transition_start_frame': 53, 
#           'transition_end_frame': 83, 'estimated_quality': 0.884, ...}
```

Important Limitations:
- Metadata calculation only – does not perform actual motion synthesis
- Quality estimates are heuristic (duration/ratio-based), not motion-aware
- For neural network-based blending, use [blendanim framework](https://github.com/RydlrCS/blendanim)
- File contents (BVH/FBX) are not parsed; frame counts use placeholder values (0)
- Actual blend quality requires L2 velocity/acceleration analysis on generated motions

The blend_utils module is designed for cataloging blend operations and generating metadata records for the `blend_motions` table. Refer to the "Blend Metadata Calculation (blend_utils)" subsection in the Data handling section for usage details.

## Testing

### Local Testing with Fivetran SDK

The connector can be tested locally using the Fivetran SDK debug mode:

```bash
# Install dependencies
pip install -r requirements.txt

# Set up authentication
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json

# Configure test parameters in configuration.json
# Use batch_limit for testing with small datasets

# Run connector in debug mode
python connector.py
```

### Test Configuration for Development

For testing during development, use a limited configuration to avoid processing large datasets:

```json
{
  "google_cloud_storage_bucket": "your-test-bucket",
  "google_cloud_storage_prefixes": "test/seed/,test/build/",
  "batch_limit": 10,
  "include_extensions": ".bvh,.fbx",
  "max_blend_pairs": 5,
  "max_motion_buffer_size": 100
}
```

**Important Testing Notes:**
- `batch_limit` is for TESTING ONLY and triggers a runtime warning
- Remove `batch_limit` for production deployment
- Use small test datasets (10-100 files) to validate functionality
- Verify state persistence by stopping and resuming connector mid-sync
- Check logs for retry attempts, checkpointing, and error handling

### Validation Checklist

Before deploying to production, verify:

1. **Authentication**
   - [ ] Service account has `roles/storage.objectViewer` permission
   - [ ] GCS client initializes successfully with ADC
   - [ ] Access denied errors handled gracefully

2. **Data Integrity**
   - [ ] Files processed in chronological order within batches
   - [ ] State cursor advances correctly after each batch
   - [ ] Incremental sync skips already-processed files
   - [ ] Record IDs remain stable across file renames (when GCS ID available)
   - [ ] No duplicate records created for same files

3. **Error Handling**
   - [ ] Transient GCS errors trigger exponential backoff retries (max 3 attempts)
   - [ ] Permanent errors (authentication, not found) fail immediately without retries
   - [ ] Connector logs errors at appropriate severity levels
   - [ ] State is preserved on failure for next sync resumption

4. **Performance & Memory**
   - [ ] Large prefixes (1000+ files) processed without out-of-memory errors
   - [ ] Bounded buffering maintains memory footprint
   - [ ] Checkpointing occurs every 100 records
   - [ ] Motion buffers cleared after generating blend pairs

5. **Configuration Validation**
   - [ ] Missing required parameters raise `ValueError` with clear messages
   - [ ] Empty/whitespace parameters rejected
   - [ ] File extensions validated (must start with '.')
   - [ ] Integer parameters validated for range and type
   - [ ] `batch_limit` triggers runtime warning

### Test Scenarios

**Scenario 1: First Sync (Full Load)**
- Expected: All files in configured prefixes processed
- State: Updated with timestamp of last processed file per prefix
- Verify: All records appear in destination tables

**Scenario 2: Incremental Sync**
- Add new files with recent timestamps to GCS
- Expected: Only new files (timestamp > last sync) processed
- Verify: State advances to newest file timestamp

**Scenario 3: Mid-Sync Failure Recovery**
- Set `batch_limit` to small value (e.g., 5)
- Manually stop connector after first batch completes
- Restart connector
- Expected: Resumes from last checkpointed state, processes remaining files
- Verify: No duplicate records, all files eventually processed

**Scenario 4: Out-of-Order File Arrivals**
- Create files with timestamps: Jan 10, Jan 15, Jan 12 (out of order)
- Expected: Files sorted and processed as Jan 10 → Jan 12 → Jan 15
- State: Jan 15 after batch completes
- Verify: Next sync skips all three files (timestamps ≤ Jan 15)

**Scenario 5: Transient GCS Errors**
- Simulate network interruption or GCS API throttling
- Expected: Connector retries with exponential backoff (1s, 2s, 4s)
- Verify: Logs show retry attempts, eventual success or failure after 3 attempts

**Scenario 6: File Rename/Move**
- Process file `gs://bucket/walk.bvh` (generates record with GCS object ID)
- Rename file to `gs://bucket/archive/walk_v1.bvh` (same GCS generation)
- Reprocess renamed file
- Expected: Same record ID, no duplicate created
- Verify: Only one record exists in destination table

### Log Analysis

Monitor connector logs for expected patterns:

```
# Successful batch processing
[INFO] Listing files from GCS bucket 'bucket' with prefix 'seed/'
[INFO] Processing batch of 50 files (sorted chronologically)
[INFO] Synced 100 total records (50 from prefix 'seed/')
[INFO] Completed processing prefix 'seed/': 50 records synced

# Retry on transient error
[WARNING] GCS connection attempt 1/3 failed (transient error), retrying in 1s: ...
[WARNING] GCS connection attempt 2/3 failed (transient error), retrying in 2s: ...
[INFO] GCS connection successful on attempt 3

# batch_limit warning
[WARNING] batch_limit is set to 10. This parameter is for TESTING ONLY...
[WARNING] Reached batch limit of 10 files for prefix 'seed/'...

# Permanent error (immediate failure)
[SEVERE] GCS connection failed with permanent error: 403 Forbidden
```

### Known Limitations & Edge Cases

1. **Empty String Parameters**
   - Configuration validation rejects empty or whitespace-only values
   - Special handling for "0" values (correctly validated as integer, not empty)

2. **Files Without Timestamps**
   - Files missing `updated_at` timestamp are skipped with warning
   - Cannot be tracked for incremental sync

3. **Zero-Length Motions**
   - Blend quality calculation returns `None` for motions with 0 frames
   - Division by zero prevented in `blend_utils.estimate_blend_quality()`

4. **Batch Processing Order**
   - Files sorted chronologically **within** each batch (1000 files)
   - Not guaranteed globally chronological across all batches
   - State tracking ensures correctness despite batch boundaries

### Production Deployment

Before production deployment:

1. Remove `batch_limit` from configuration (or set to very high value)
2. Configure BigQuery partitioning on `created_at` field (recommended: daily)
3. Set up monitoring for connector logs (INFO/WARNING/SEVERE levels)
4. Verify service account credentials in Fivetran platform
5. Test with representative dataset (similar file count and structure)
6. Document expected sync frequency and data volume

## Additional considerations
The examples provided are intended to help you effectively use Fivetran's Connector SDK. While we've tested the code, Fivetran and Rydlr cannot be held responsible for any unexpected or negative consequences that may arise from using these examples. For inquiries, please reach out to our Support team.
