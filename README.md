# DynamoDB GSI Scheduled Export & Reporting Dashboard

A single **AWS CloudFormation** template that builds an end-to-end pipeline: export data from a DynamoDB Global Secondary Index (GSI) to S3 as Parquet, make it queryable through Amazon Athena, and serve a live web dashboard via a Lambda Function URL — all without AWS Glue.

---

## Architecture Overview

```
 DynamoDB Table (GSI)
        │
        ▼
 ┌──────────────────┐     EventBridge      ┌──────────────────┐
 │  Scheduled Export │◄────(cron/rate)──────│  EventBridge Rule│
 │  Lambda (Python)  │                      └──────────────────┘
 └────────┬─────────┘
          │  Parquet (Hive-partitioned)
          ▼
 ┌──────────────────┐
 │  S3 Data Bucket  │──── year=YYYY/month=MM/day=DD/data.parquet
 └────────┬─────────┘
          │  Partition Projection (no Glue crawlers)
          ▼
 ┌──────────────────┐     Custom Resource   ┌──────────────────┐
 │  Amazon Athena   │◄─────(auto-setup)─────│  AthenaSetup     │
 │  Database/Table  │                       │  Lambda           │
 └────────┬─────────┘                       └──────────────────┘
          │
          ▼
 ┌──────────────────┐     Lambda Function URL (public)
 │  Report Query    │────────────────────────► Browser Dashboard
 │  Lambda          │     GET  /              (HTML + Charts)
 │  (dual-mode)     │     POST /api/query     Query interface
 │                  │     GET  /api/results   Result rows (JSON)
 │                  │     GET  /api/download  CSV download (302)
 └──────────────────┘
```

---

## Features

- **Scheduled & On-Demand Export** — EventBridge cron triggers nightly exports; a separate Lambda handles ad-hoc exports
- **Parquet + Hive Partitioning** — Data lands in S3 as `year=YYYY/month=MM/day=DD/data.parquet`
- **Athena Partition Projection** — No Glue crawlers needed; Athena discovers partitions automatically
- **Auto-Setup Custom Resource** — Database and table are created automatically on stack deploy
- **Web Dashboard** — Served via Lambda Function URL (no API Gateway required)
  - 4 stat cards (total rows, unique contacts, channels, agents)
  - 4 interactive charts (daily bar, channel doughnut, agent bar, initiation pie)
  - 7 built-in query types + custom SQL
  - CSV download with column selection
  - Click-to-copy table cells
  - 4 colour themes (Light, Dark, Ocean, Sunset) persisted in localStorage
- **Optional DynamoDB Table Creation** — Create a new table with GSI, or point at an existing one
- **CloudWatch Alarm** — Alerts on export Lambda errors
- **Single Template** — Everything deploys from one YAML file

---

## Files

| File | Purpose |
|------|---------|
| `dynamo-gsi-scheduled-export.yaml` | CloudFormation template (all infrastructure) |
| `deploy.py` | Python deployment helper script |
| `dashboard.html` | Standalone copy of the dashboard HTML for reference |

---

## Prerequisites

- **AWS CLI** v2 configured with credentials (`aws configure`)
- **Python 3.8+** with `boto3` installed (`pip install boto3`)
- An AWS account with permissions for CloudFormation, Lambda, S3, DynamoDB, Athena, IAM, EventBridge, CloudWatch

---

## Quick Start

### Option 1: Deploy with the Python script

1. Clone this repository:
   ```bash
   git clone https://github.com/<your-org>/step-by-step-enhancement-reporting.git
   cd step-by-step-enhancement-reporting
   ```

2. Edit `deploy.py` — update the `PARAMETERS` dictionary at the top to match your DynamoDB table and GSI:
   ```python
   STACK_NAME = "gsi-dynamodb-athena"

   PARAMETERS = {
       "DynamoTableName":          "YourTableName",
       "GsiName":                  "YourGSIName",
       "GsiPartitionKeyAttribute": "YourPartitionKey",
       "GsiPartitionKeyValue":     "VALUE_TO_QUERY",
       "GsiSortKeyAttribute":      "YourSortKey",
       "DateFormat":               "ISO",          # ISO | EPOCH | HUMAN_READABLE
       "S3DataPrefix":             "exports",
       "CronExpression":           "rate(1 day)",
       "DateRangeMode":            "LAST_N_HOURS",
       "LookbackHours":            "24",
       "CreateTable":              "false",          # "true" to create new table
       "ExtraDateColumn":          "report_date",
   }
   ```

3. Deploy:
   ```bash
   python deploy.py deploy
   ```

4. The script will:
   - Create an S3 staging bucket (for the template, since it exceeds 51 KB)
   - Upload the template
   - Create or update the CloudFormation stack
   - Wait for completion
   - Print all outputs including the **Dashboard URL**

### Option 2: Deploy with AWS CLI

```bash
aws cloudformation deploy \
  --template-file dynamo-gsi-scheduled-export.yaml \
  --stack-name gsi-dynamodb-athena \
  --s3-bucket <your-staging-bucket> \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    DynamoTableName=YourTableName \
    GsiName=YourGSIName \
    GsiPartitionKeyAttribute=YourPartitionKey \
    GsiPartitionKeyValue=VALUE_TO_QUERY \
    GsiSortKeyAttribute=YourSortKey \
    DateFormat=ISO \
    S3BucketName=<globally-unique-bucket-name> \
    S3DataPrefix=exports \
    "CronExpression=rate(1 day)" \
    DateRangeMode=LAST_N_HOURS \
    LookbackHours=24 \
    CreateTable=false \
    ExtraDateColumn=report_date
```

> **Note:** The template exceeds 51 KB, so `--s3-bucket` is required.

---

## deploy.py Commands

| Command | Description |
|---------|-------------|
| `python deploy.py deploy` | Create or update the CloudFormation stack |
| `python deploy.py delete` | Delete the stack (empties S3 buckets and Athena workgroup first) |
| `python deploy.py outputs` | Show stack outputs (Dashboard URL, bucket names, etc.) |
| `python deploy.py status` | Show current stack status |

---

## Parameters Reference

### DynamoDB Table (optional creation)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CreateTable` | `false` | Set to `true` to create a new DynamoDB table with GSI |
| `DynamoTableName` | *(required)* | Table name (new or existing) |
| `TablePKName` | `pk` | Partition key attribute name (only when creating) |
| `TablePKType` | `S` | Partition key type: `S`, `N`, or `B` |
| `TableSKName` | *(empty)* | Sort key attribute name; leave blank for PK-only table |
| `TableSKType` | `S` | Sort key type: `S`, `N`, or `B` |
| `BillingMode` | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` or `PROVISIONED` |

### GSI Query Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `GsiName` | *(required)* | GSI name to query |
| `GsiPartitionKeyAttribute` | *(required)* | GSI partition key attribute name |
| `GsiPartitionKeyValue` | *(required)* | Value to filter GSI partition key |
| `GsiSortKeyAttribute` | *(required)* | GSI sort key attribute (must hold dates) |
| `DateFormat` | `ISO` | Sort key date format: `ISO`, `EPOCH`, `HUMAN_READABLE` |
| `ExtraDateColumn` | *(empty)* | If set, adds a `YYYY-MM-DD` column derived from the sort key |

### Export Schedule

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CronExpression` | `cron(0 1 * * ? *)` | EventBridge cron/rate expression |
| `DateRangeMode` | `PREVIOUS_DAY` | `PREVIOUS_DAY`, `PREVIOUS_WEEK`, or `LAST_N_HOURS` |
| `LookbackHours` | `24` | Hours to look back (only for `LAST_N_HOURS`) |

### S3 & Athena

| Parameter | Default | Description |
|-----------|---------|-------------|
| `S3BucketName` | *(required)* | Globally unique S3 bucket for Parquet data |
| `S3DataPrefix` | `dynamo-gsi-export` | S3 key prefix for exports |
| `OverwriteMode` | `OVERWRITE` | `OVERWRITE` (idempotent) or `APPEND` (timestamped) |
| `ProjectionYearRange` | `2024,2030` | Start,end year for Athena partition projection |

### Q/A View (BI Unpivot)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QuestionColumnSuffix` | *(empty)* | Suffix identifying question-text columns (e.g., `_Question`). The answer column is the question column minus this suffix. Leave empty to disable. |

### Dashboard

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MaxFetchRows` | `20000` | Maximum number of rows the dashboard API will return per query |

### Operational

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LogRetentionDays` | `14` | CloudWatch log retention in days |

---

## Stack Outputs

After deployment, the stack provides these outputs:

| Output | Description |
|--------|-------------|
| `ReportDashboardURL` | Open in a browser to access the reporting dashboard |
| `ExportDataBucket` | S3 bucket containing Parquet export files |
| `AthenaResultsBucket` | S3 bucket for Athena query results |
| `AthenaWorkgroup` | Athena workgroup name |
| `AthenaDatabase` | Athena database name |
| `AthenaTable` | Fully qualified Athena table name |
| `AthenaQAView` | Q/A view name for BI tools (if suffixes configured) |
| `LambdaFunction` | Scheduled export Lambda function name |
| `OnDemandExportFunction` | On-demand export Lambda function name |
| `ReportQueryFunction` | Report query Lambda function name |
| `EventBridgeRule` | EventBridge schedule rule name |
| `DynamoDBTable` | DynamoDB table name (if created by stack) |

---

## Web Dashboard

The dashboard is served directly from a **Lambda Function URL** (no API Gateway). After deployment, open the `ReportDashboardURL` output in any browser.

### Query Types

| Type | Description | Parameters |
|------|-------------|------------|
| All Records | Fetch all rows | Limit |
| By Date Range | Filter by date range | Start date, End date, Limit |
| By Agent | Filter by agent name | Agent dropdown, Limit |
| By Contact ID | Look up a single contact | Contact ID, Limit |
| Daily Summary (by Agent) | Aggregated daily counts per agent | Start date, End date, Limit |
| Daily Summary (by Channel) | Aggregated daily counts per channel | Start date, End date, Limit |
| Custom SQL | Run any SELECT query | SQL editor, Limit |

### Dashboard Features

- **Statistics & Charts** — Auto-generated from query results (total rows, unique contacts, channels, agents; daily bar chart, channel doughnut, agent bar, initiation pie)
- **Theme Switcher** — Light, Dark, Ocean, Sunset themes; persists across sessions
- **CSV Download** — Select/deselect columns before downloading; CSV generated client-side
- **Click-to-Copy** — Click any table cell to copy its value
- **Custom SQL Editor** — Monospace editor with example query, Load Example button, and Clear button

### API Endpoints

The Lambda Function URL exposes these routes:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve the HTML dashboard |
| `GET` | `/api/stats` | Return aggregated statistics (JSON) |
| `POST` | `/api/query` | Execute an Athena query (JSON body) |
| `GET` | `/api/results?queryExecutionId=xxx` | Fetch result rows (JSON) |
| `GET` | `/api/download?queryExecutionId=xxx` | 302 redirect to presigned CSV URL |
| `GET` | `/api/daily?from=YYYY-MM-DD&to=YYYY-MM-DD` | Daily contact counts for date range |

### Direct Lambda Invocation

The Report Query Lambda also supports direct invocation (backwards compatible):

```bash
aws lambda invoke \
  --function-name <ReportQueryFunction> \
  --payload '{"query":"all_records","limit":10}' \
  out.json
```

---

## Triggering an On-Demand Export

```bash
aws lambda invoke \
  --function-name <OnDemandExportFunction> \
  --payload '{}' \
  out.json
```

The on-demand Lambda uses the same date range configuration as the scheduled export.

---

## Querying Data via Athena CLI

Run a query against the exported data directly from the command line:

```bash
aws athena start-query-execution \
  --query-string "SELECT * FROM <AthenaDatabase>.gsi_export LIMIT 100" \
  --work-group <AthenaWorkgroup> \
  --region us-east-1 \
  --output json
```

Then retrieve the results using the `QueryExecutionId` returned:

```bash
aws athena get-query-results \
  --query-execution-id <QueryExecutionId> \
  --region us-east-1
```

Example queries:

```sql
-- All records
SELECT * FROM gsi_dynamodb_athena_db.gsi_export LIMIT 100;

-- Filter by date range
SELECT * FROM gsi_dynamodb_athena_db.gsi_export
WHERE report_date BETWEEN '2026-01-01' AND '2026-02-19';

-- Daily summary
SELECT report_date, COUNT(*) as contacts
FROM gsi_dynamodb_athena_db.gsi_export
GROUP BY report_date ORDER BY report_date DESC;

-- Filter by partition (most cost-efficient)
SELECT * FROM gsi_dynamodb_athena_db.gsi_export
WHERE year=2026 AND month=2 AND day=19;
```

---

## How the Export Works

1. **Query** — Lambda queries the DynamoDB GSI using the configured partition key value and a date range on the sort key
2. **Transform** — Results are converted to Parquet format with proper type mapping (DynamoDB Numbers become DOUBLEs)
3. **Partition** — Files are written to S3 with Hive-style partitioning: `s3://<bucket>/<prefix>/year=YYYY/month=MM/day=DD/data.parquet`
4. **Athena** — Partition projection automatically discovers new partitions without Glue crawlers

### Dynamic Schema Discovery

The Athena table schema is **not hardcoded** — it is discovered automatically at deployment time:

1. **On stack create/update**, the `AthenaSetup` Custom Resource Lambda scans up to 5000 items from the DynamoDB GSI to discover all unique attribute names and types.
2. It creates (or recreates) the Athena table with every discovered attribute as a column.
3. **After each export** (scheduled or on-demand), the export Lambda runs a schema sync — any new attributes found in the exported items are added to the Athena table via `ALTER TABLE ADD COLUMNS`.

This means:
- **No hardcoded column list** — whatever attributes exist in DynamoDB will appear in Athena
- **New attributes are picked up automatically** — if a DynamoDB item gains a new field (e.g., `WelcomeGuide_Q3`), the next export will add it to the Athena schema
- **Column names are lowercased** — DynamoDB attribute `WelcomeGuide_Q3` becomes Athena column `welcomeguide_q3` (Athena is case-insensitive)

**Type mapping:**
- Numeric attributes (int, float, Decimal) → `DOUBLE`
- All other attributes → `STRING`
- The optional `ExtraDateColumn` → `STRING` (format: `YYYY-MM-DD`)

**Partition columns:** `year INT`, `month INT`, `day INT`

---

## Q/A View for BI Tools

When `QuestionColumnSuffix` is configured (e.g., `_Question`), the pipeline automatically creates an Athena view called `qa_map` that unpivots question/answer columns from **wide format** into **long format** — ideal for BI tools like Power BI, Tableau, and QuickSight.

### How It Works

If your DynamoDB items have attributes like:

| WelcomeGuide_Q1_Question | WelcomeGuide_Q1 | WelcomeGuide_Q2_Question | WelcomeGuide_Q2 |
|---------------------------|-----------------|---------------------------|-----------------|
| How was your experience?  | Great           | Was your issue resolved?  | Yes             |

The `qa_map` view transforms them into:

| topic | question | answer |
|-------|----------|--------|
| WELCOMEGUIDE_Q1 | How was your experience? | Great |
| WELCOMEGUIDE_Q2 | Was your issue resolved? | Yes |

All non-Q/A columns (contactid, agentname, channel, report_date, etc.) are included as passthrough columns in each row.

### Pairing Logic

Columns are paired by suffix stripping:
- `welcomeguide_q1_question` (ends with `_question` suffix) → question text column
- `welcomeguide_q1` (question column minus the suffix) → answer value column
- Topic = answer column name uppercased → `WELCOMEGUIDE_Q1`

The suffix match is case-insensitive (columns are lowercased in Parquet).

### Auto-Regeneration

The view is recreated automatically:
1. **On deploy** — AthenaSetup creates the view after the table
2. **After each export** — Both export Lambdas regenerate the view after schema sync

When a new Q/A pair appears in DynamoDB (e.g., `WelcomeGuide_Q5_Question` / `WelcomeGuide_Q5`):
1. The export writes it to Parquet
2. Schema sync adds the columns to the Athena table
3. The view is regenerated to include the new pair
4. BI tool sees the new question automatically

### Example BI Queries

```sql
-- All Q/A data
SELECT * FROM "gsi_dynamodb_athena_db"."qa_map" LIMIT 100;

-- Answer distribution for a specific topic
SELECT answer, COUNT(*) as count
FROM "gsi_dynamodb_athena_db"."qa_map"
WHERE topic = 'WELCOMEGUIDE_Q1'
GROUP BY answer;

-- Completion rate per topic
SELECT topic, COUNT(answer) as answered, COUNT(*) as total
FROM "gsi_dynamodb_athena_db"."qa_map"
GROUP BY topic;

-- Agent performance by topic
SELECT agentname, topic, answer, COUNT(*) as count
FROM "gsi_dynamodb_athena_db"."qa_map"
GROUP BY agentname, topic, answer;
```

### Disabling the Q/A View

Leave `QuestionColumnSuffix` empty (default) to skip view creation entirely.

---

## Cleanup

### With deploy.py

```bash
python deploy.py delete
```

This will:
1. Empty the S3 data and Athena results buckets
2. Force-delete the Athena workgroup (including query history)
3. Delete the CloudFormation stack

### With AWS CLI

```bash
# Empty buckets first
aws s3 rm s3://<ExportDataBucket> --recursive
aws s3 rm s3://<AthenaResultsBucket> --recursive

# Delete Athena workgroup
aws athena delete-work-group --work-group <AthenaWorkgroup> --recursive-delete-option

# Delete stack
aws cloudformation delete-stack --stack-name gsi-dynamodb-athena
```

---

## Resources Created

The template creates **28 AWS resources**:

| Category | Resources |
|----------|-----------|
| **DynamoDB** | Table with GSI (conditional) |
| **Lambda** | 4 functions — Scheduled Export, On-Demand Export, Athena Setup (Custom Resource), Report Query + Dashboard |
| **IAM** | 4 roles with least-privilege policies |
| **S3** | 2 buckets — Export data, Athena results |
| **Athena** | 1 workgroup, 4 named queries, auto-created database and table |
| **EventBridge** | 1 scheduled rule |
| **CloudWatch** | 4 log groups, 1 error alarm |
| **Lambda URL** | 1 Function URL + public permission |
| **Custom Resource** | 1 Athena auto-setup trigger |

---

## When DynamoDB Attributes Change

If new attributes are added to DynamoDB items (e.g., a new `WelcomeGuide_Q3` field), the pipeline handles this automatically:

1. **Next scheduled/on-demand export** — The export Lambda discovers the new attributes, writes them to Parquet, and runs `ALTER TABLE ADD COLUMNS` to add them to Athena.
2. **No redeployment needed** — Schema sync happens on every export run.
3. **Existing Parquet files** — Old files will have `NULL` for the new columns. Only newly exported files contain the new data.

If you want all historical data to include the new columns, re-export:
```bash
aws lambda invoke \
  --function-name <OnDemandExportFunction> \
  --payload '{}' \
  out.json --region us-east-1
```

---

## Troubleshooting

### Missing Fields in Athena Query Results

If Athena queries don't return all DynamoDB attributes (e.g., `WelcomeGuide_*` fields are missing):

**1. Check that the Parquet files contain the columns**

View a Parquet file's columns using Athena:
```sql
SELECT * FROM "gsi_dynamodb_athena_db"."gsi_export" LIMIT 1;
```
If columns are missing from the result, the Parquet files need to be re-exported.

**2. Re-deploy to update Lambda code and refresh schema discovery**

```bash
# Pull latest code
git pull origin main

# Redeploy — this updates all Lambda functions and re-runs AthenaSetup
python deploy.py deploy
```

Redeployment:
- Updates all Lambda function code (export, setup, dashboard)
- Re-runs `AthenaSetup` which scans DynamoDB and recreates the Athena table with all discovered columns
- Updates IAM roles and environment variables

**3. Re-export data to rewrite Parquet files**

After redeployment, trigger a fresh export to rewrite the Parquet files with the updated code:
```bash
aws lambda invoke \
  --function-name <OnDemandExportFunction> \
  --payload '{}' \
  out.json --region us-east-1
```

This is necessary because:
- Old Parquet files may have mixed-case column names that don't match the Athena table (which uses lowercase)
- Old Parquet files may be missing attributes that weren't extracted by the previous Lambda code

**4. Verify all columns are present**

After the export completes, run:
```sql
SELECT * FROM "gsi_dynamodb_athena_db"."gsi_export" LIMIT 10;
```
All DynamoDB attributes should now appear as lowercase columns.

### Lambda Function URL Returns "Forbidden"

If the dashboard URL returns `{"Message":"Forbidden"}`:
- The stack requires both `lambda:InvokeFunctionUrl` AND `lambda:InvokeFunction` permissions
- Redeploy with the latest template which includes both permissions

### Athena Query Returns No Results

- Check that at least one export has run successfully (check the S3 data bucket for Parquet files)
- Verify the partition dates match your query: `WHERE year=2026 AND month=2 AND day=19`
- Run an on-demand export if no data exists yet

---

## Security Notes

- The Lambda Function URL uses `AuthType: NONE` — the URL is public but auto-generated and not guessable
- Custom SQL validates that queries start with `SELECT` only (read-only)
- All Lambda functions use least-privilege IAM policies
- S3 buckets have `PublicAccessBlockConfiguration` enabled
- CloudWatch logs are retained for a configurable period (default 14 days)
- For production use, consider adding IAM authentication to the Function URL

---

## License

MIT
