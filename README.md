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
```

Objects must be fully qualified. `on:` mirrors Snowflake's `GRANT ... ON <object>` syntax.

## v0 scope

- Reads YAML grant spec.
- Connects to Snowflake.
- Diffs declared vs actual using `SHOW GRANTS TO ROLE`.
- Prints missing and extra grants.

Known coverage gaps (deliberate, v0): future grants, role-to-role grants, masking/row-access policies, application roles. The whole point of this tool is acknowledging managed-grant blindness — coverage expands as drift surfaces in practice.

Out of scope for v0: auto-remediation, Terraform state ingestion, naming-convention checks, web UI.

## Dev

```bash
python snowdrift.py selftest
```
