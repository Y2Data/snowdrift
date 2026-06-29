#!/usr/bin/env python3
"""snowdrift: audit Snowflake grant drift against a declared YAML spec."""
import argparse, sys, yaml
from pathlib import Path


def load_spec(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def declared_grants(spec):
    # ponytail: tuple-set diff; upgrade to structured objects if grant options (WITH GRANT OPTION, etc.) need tracking
    return {(g["privilege"].upper(), g["on"].upper(), g["to_role"].upper()) for g in spec.get("grants", [])}


def future_probes(declared):
    # For each declared `FUTURE <T>S IN SCHEMA|DATABASE <name>`, the scope (schema or database) is
    # what we must query. The row from SHOW FUTURE GRANTS doesn't tell us the scope; the query does.
    probes = set()
    for _, on, _ in declared:
        parts = on.split()
        if len(parts) >= 5 and parts[0] == "FUTURE" and parts[2] == "IN" and parts[3] in ("SCHEMA", "DATABASE"):
            probes.add((parts[3], parts[4]))  # (SCHEMA|DATABASE, name)
    return probes


def actual_grants(cur, roles, future_probe_set=()):
    # ponytail: probe schemas/databases mentioned in declared future grants only. Blind-scanning every
    # schema in the account explodes for large warehouses; add `--all-schemas` opt-in if anyone asks.
    out = set()
    for role in roles:
        cur.execute(f"SHOW GRANTS TO ROLE {role}")
        for row in cur.fetchall():
            priv, granted_on, name = row[1].upper(), row[2].upper(), row[3].upper()
            out.add((priv, f"{granted_on} {name}", role.upper()))
    # SHOW FUTURE GRANTS IN SCHEMA|DATABASE <name> — row[2] is the object type (TABLE, VIEW, ...),
    # row[5] is the grantee role. Scope (schema/db) comes from the query, not the row.
    for scope, name in future_probe_set:
        cur.execute(f"SHOW FUTURE GRANTS IN {scope} {name}")
        for row in cur.fetchall():
            priv, obj_type, grantee = row[1].upper(), row[2].upper(), row[5].upper()
            out.add((priv, f"FUTURE {obj_type}S IN {scope} {name}", grantee))
    return out


def cmd_check(args):
    spec = load_spec(args.spec)
    import snowflake.connector
    conn = snowflake.connector.connect(connection_name=args.connection) if args.connection else snowflake.connector.connect()
    cur = conn.cursor()
    declared = declared_grants(spec)
    roles = {r for _, _, r in declared}
    actual = actual_grants(cur, roles, future_probes(declared))
    cur.close(); conn.close()

    missing, extra = declared - actual, actual - declared
    print(f"== grants: {len(missing)} missing, {len(extra)} extra ==")
    for p, o, r in sorted(missing): print(f"  MISSING: GRANT {p} ON {o} TO ROLE {r}")
    for p, o, r in sorted(extra):   print(f"  EXTRA:   {p} ON {o} held by {r}")
    return 1 if (missing or extra) else 0


def cmd_selftest(_args):
    assert declared_grants({"grants": [{"privilege": "select", "on": "table a.b.c", "to_role": "r"}]}) == {("SELECT", "TABLE A.B.C", "R")}
    a = {("SELECT", "TABLE A.B.C", "R")}
    b = {("USAGE", "WAREHOUSE W", "R")}
    assert a - b == a and b - a == b

    # SHOW GRANTS TO ROLE returns: created_on, privilege, granted_on, name, granted_to, grantee_name, grant_option, granted_by
    # SHOW FUTURE GRANTS IN SCHEMA|DATABASE: created_on, privilege, grant_on, name, grant_to, grantee_name, grant_option
    # https://docs.snowflake.com/en/sql-reference/sql/show-grants
    # https://docs.snowflake.com/en/sql-reference/sql/show-future-grants
    class FakeCursor:
        def __init__(self, role_rows, future_rows):
            self._role_rows, self._future_rows, self._next = role_rows, future_rows, []
        def execute(self, sql):
            u = sql.upper()
            if u.startswith("SHOW GRANTS TO ROLE"):
                role = sql.rsplit(" ", 1)[-1]
                self._next = [r for r in self._role_rows if r[5] == role]
            elif u.startswith("SHOW FUTURE GRANTS IN"):
                scope, name = sql.split()[-2].upper(), sql.split()[-1]
                self._next = [r for r in self._future_rows if r[8] == (scope, name)]
            else:
                self._next = []
        def fetchall(self): return [r[:8] for r in self._next]  # strip our scope tag

    role_rows = [
        ("2024-01-01", "SELECT", "TABLE", "ANALYTICS.PUBLIC.ORDERS", "ROLE", "REPORTER", "false", "ACCOUNTADMIN"),
        ("2024-01-01", "USAGE",  "WAREHOUSE", "LOAD_WH",              "ROLE", "LOADER",   "false", "ACCOUNTADMIN"),
        ("2024-01-01", "SELECT", "TABLE", "ANALYTICS.PUBLIC.STAGING", "ROLE", "REPORTER", "false", "ACCOUNTADMIN"),  # extra
    ]
    # future-grant rows carry a 9th tag = (scope, name) so the fake cursor can route
    future_rows = [
        ("2024-01-01", "SELECT", "TABLE", "ANALYTICS.PUBLIC.<TABLE>", "ROLE", "REPORTER", "false", "ACCOUNTADMIN", ("SCHEMA", "ANALYTICS.PUBLIC")),
        ("2024-01-01", "INSERT", "TABLE", "ANALYTICS.PUBLIC.<TABLE>", "ROLE", "REPORTER", "false", "ACCOUNTADMIN", ("SCHEMA", "ANALYTICS.PUBLIC")),  # extra (declared SELECT only)
    ]
    declared = {("SELECT", "TABLE ANALYTICS.PUBLIC.ORDERS", "REPORTER"),
                ("USAGE",  "WAREHOUSE LOAD_WH",              "LOADER"),
                ("SELECT", "TABLE ANALYTICS.PUBLIC.CUSTOMERS","REPORTER"),  # missing
                ("SELECT", "FUTURE TABLES IN SCHEMA ANALYTICS.PUBLIC", "REPORTER")}
    probes = future_probes(declared)
    assert probes == {("SCHEMA", "ANALYTICS.PUBLIC")}

    actual = actual_grants(FakeCursor(role_rows, future_rows), ["REPORTER", "LOADER"], probes)
    assert ("SELECT", "TABLE ANALYTICS.PUBLIC.ORDERS", "REPORTER") in actual
    assert ("USAGE",  "WAREHOUSE LOAD_WH",              "LOADER") in actual
    assert ("SELECT", "FUTURE TABLES IN SCHEMA ANALYTICS.PUBLIC", "REPORTER") in actual

    missing, extra = declared - actual, actual - declared
    assert missing == {("SELECT", "TABLE ANALYTICS.PUBLIC.CUSTOMERS", "REPORTER")}
    assert extra == {("SELECT", "TABLE ANALYTICS.PUBLIC.STAGING", "REPORTER"),
                     ("INSERT", "FUTURE TABLES IN SCHEMA ANALYTICS.PUBLIC", "REPORTER")}
    print("ok")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="snowdrift")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="diff declared vs actual grants")
    c.add_argument("--spec", default="grants.yml")
    c.add_argument("--connection", default=None, help="connection name in ~/.snowflake/config.toml")
    c.set_defaults(func=cmd_check)
    s = sub.add_parser("selftest", help="run offline logic checks")
    s.set_defaults(func=cmd_selftest)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
