# E-Commerce Lakehouse on AWS

Production-grade Lakehouse architecture for an e-commerce platform built on AWS using PySpark, Delta Lake, and S3. Orchestrated by AWS Step Functions, deployed via GitHub Actions CI/CD.

## Architecture Overview

```
S3 (raw/incoming/)
    │  EventBridge (Object Created)
    ▼
Step Functions Pipeline
    ├── Parallel Branch A: Products Glue Job
    └── Parallel Branch B: Orders Glue Job → Order Items Glue Job
    ▼
Glue Crawlers → Glue Data Catalog → Athena
    ▼
Archive Lambda (raw/ → archive/)
    ▼
SNS Notification (success/failure)
```

## Data Model

| Table | Source | Partition | Primary Key |
|---|---|---|---|
| `products` | products.csv | none | `product_id` |
| `orders` | orders_apr_YYYY.xlsx | `date` | `order_id` |
| `order_items` | order_items_apr_YYYY.xlsx | `date` | `id` |

## Prerequisites

- Python 3.11+
- AWS CLI configured with appropriate credentials
- Terraform >= 1.7.0
- Java 11+ (for local PySpark)

## Local Development Setup

```bash
# Install dev dependencies
make install

# Run linting
make lint

# Run unit tests
make test-unit

# Run all tests with coverage
make test

# Run the pipeline locally (PySpark local mode)
make local-run
```

## Deployment

See [docs/architecture.md](docs/architecture.md) for the full deployment guide.

Bootstrap the Terraform state backend (one-time, manual):
```bash
bash scripts/bootstrap_terraform_backend.sh
```

Deploy to dev:
```bash
cd infrastructure/environments/dev
terraform init
terraform apply
```

## Project Structure

```
├── src/
│   ├── glue_jobs/        # Three AWS Glue PySpark ETL jobs
│   ├── lib/              # Shared utilities (logging, config, Delta, S3, metrics)
│   ├── data_quality/     # Validation rule engine and quarantine logic
│   └── lambda/           # Archive handler Lambda function
├── infrastructure/       # Terraform IaC (10 modules, 3 environments)
├── tests/                # Unit tests (pytest + moto) — target ≥ 80% coverage
├── config/               # Environment config constants and Glue job params
├── athena_queries/       # Post-pipeline sanity check queries
├── docs/                 # Architecture, runbook, data dictionary, ADRs
└── .github/workflows/    # CI (lint + test + tf plan) and CD (apply + deploy)
```

## Observability

- **CloudWatch Logs**: All Glue jobs emit structured JSON logs with correlation IDs
- **Custom Metrics**: `Lakehouse/Pipeline` namespace — records processed, rejected, job duration
- **CloudWatch Alarms**: Glue errors, quarantine spikes, pipeline SLA breach → SNS
- **CloudWatch Dashboard**: Real-time pipeline health visualization

## Data Quality

All three jobs use a pluggable validation framework (`src/data_quality/`). Invalid records are never dropped — they are quarantined to a dedicated S3 path with an `__error_reason__` column for root-cause analysis.

## Contributing

All changes must go through a PR. The CI pipeline runs lint, unit tests (≥80% coverage), and a Terraform plan on every PR. Merging to `main` triggers automatic deployment.
