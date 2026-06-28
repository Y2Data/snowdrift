#!/usr/bin/env python3
"""snowdrift: audit Snowflake grant drift against a declared YAML spec."""
import argparse, sys, yaml
from pathlib import Path


def load_spec(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def declared_grants(spec):
    # ponytail: tuple-set diff; upgrade to structured objects if grant options (WITH GRANT OPTION, etc.) need tracking
    return {(g["privilege"].upper(), g["on"].upper(), g["to_role"].upper()) for g in spec.get("grants", [])}


def actual_grants(cur, roles):
    # ponytail: SHOW GRANTS TO ROLE only — misses future grants, role-to-role, masking policies, RAP, application roles.
    # The whole point of this tool is acknowledging managed-grant blindness; expand coverage as drift surfaces in practice.
    out = set()
    for role in roles:
        cur.execute(f"SHOW GRANTS TO ROLE {role}")
        for row in cur.fetchall():
            priv, granted_on, name = row[1].upper(), row[2].upper(), row[3].upper()
            out.add((priv, f"{granted_on} {name}", role.upper()))
    return out


def cmd_check(args):
    spec = load_spec(args.spec)
    import snowflake.connector
    conn = snowflake.connector.connect(connection_name=args.connection) if args.connection else snowflake.connector.connect()
    cur = conn.cursor()
    declared = declared_grants(spec)
    roles = {r for _, _, r in declared}
    actual = actual_grants(cur, roles)
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
    # https://docs.snowflake.com/en/sql-reference/sql/show-grants
    class FakeCursor:
        def __init__(self, rows): self._rows, self._next = rows, []
        def execute(self, sql):
            role = sql.rsplit(" ", 1)[-1]
            self._next = [r for r in self._rows if r[5] == role]
        def fetchall(self): return self._next
    rows = [
        ("2024-01-01", "SELECT", "TABLE", "ANALYTICS.PUBLIC.ORDERS", "ROLE", "REPORTER", "false", "ACCOUNTADMIN"),
        ("2024-01-01", "USAGE",  "WAREHOUSE", "LOAD_WH",              "ROLE", "LOADER",   "false", "ACCOUNTADMIN"),
        ("2024-01-01", "SELECT", "TABLE", "ANALYTICS.PUBLIC.STAGING", "ROLE", "REPORTER", "false", "ACCOUNTADMIN"),  # extra
    ]
    actual = actual_grants(FakeCursor(rows), ["REPORTER", "LOADER"])
    assert ("SELECT", "TABLE ANALYTICS.PUBLIC.ORDERS", "REPORTER") in actual
    assert ("USAGE", "WAREHOUSE LOAD_WH", "LOADER") in actual
    assert ("SELECT", "TABLE ANALYTICS.PUBLIC.STAGING", "REPORTER") in actual

    declared = {("SELECT", "TABLE ANALYTICS.PUBLIC.ORDERS", "REPORTER"),
                ("USAGE",  "WAREHOUSE LOAD_WH",              "LOADER"),
                ("SELECT", "TABLE ANALYTICS.PUBLIC.CUSTOMERS","REPORTER")}  # missing
    missing, extra = declared - actual, actual - declared
    assert missing == {("SELECT", "TABLE ANALYTICS.PUBLIC.CUSTOMERS", "REPORTER")}
    assert extra == {("SELECT", "TABLE ANALYTICS.PUBLIC.STAGING", "REPORTER")}
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
