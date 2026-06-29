# snowdrift

Audit Snowflake grant drift against a declared YAML spec.

## Usage

```bash
pip install -r requirements.txt
snowdrift check --spec grants.yml [--connection my_conn]
```

`--connection` names a connection in `~/.snowflake/config.toml`. Omit it to use Snowflake's default connection-resolution.

Exit code is non-zero when drift is detected (CI-friendly).

## Spec format

```yaml
grants:
  - privilege: SELECT
    on: TABLE ANALYTICS.PUBLIC.ORDERS
    to_role: REPORTER
  - privilege: USAGE
    on: WAREHOUSE LOAD_WH
    to_role: LOADER
  - privilege: SELECT
    on: FUTURE TABLES IN SCHEMA ANALYTICS.PUBLIC
    to_role: REPORTER
  - privilege: USAGE
    on: FUTURE SCHEMAS IN DATABASE ANALYTICS
    to_role: LOADER
```

Objects must be fully qualified. `on:` mirrors Snowflake's `GRANT ... ON <object>` syntax. Future grants use `FUTURE <OBJECT_TYPE>S IN SCHEMA <db>.<schema>` or `FUTURE <OBJECT_TYPE>S IN DATABASE <db>`.

## Coverage

- `SHOW GRANTS TO ROLE` — object grants held by each declared role.
- `SHOW FUTURE GRANTS IN SCHEMA|DATABASE` — future grants in the schemas/databases mentioned in declared future grants (no blind-scan).
- Declared − actual = MISSING. Actual − declared = EXTRA. Non-zero exit on drift.

Known coverage gaps: role-to-role / role hierarchy, masking policies, row-access policies, application roles. The whole point of this tool is acknowledging managed-grant blindness — coverage expands as drift surfaces in practice.

Out of scope: auto-remediation (snowdrift never `GRANT`s or `REVOKE`s — fixes belong in your IaC), Terraform state ingestion, naming-convention checks, web UI.

## Dev

```bash
python snowdrift.py selftest
```
