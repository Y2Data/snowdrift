# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`snowdrift` is a CLI that audits **Snowflake permission drift**: declare expected grants in YAML, connect to a live Snowflake account, diff actual vs declared, report.

This is a personal open-source tool, owned and authored by the repo owner (not derived from any employer's work). It exists to fill a real gap the author hit in production: Terraform/DCM managed-grant blindness and incomplete drift detection on `GRANT`s — the highest-risk, least-observed surface in Snowflake access control. Adjacent prior art: GitLab's Permifrost.

## v0 scope (do not exceed without being asked)

The first shippable version is intentionally tiny:

- Read a YAML grant spec.
- Connect to Snowflake.
- Diff: `declared - actual` (missing grants) and `actual - declared` (extra grants).
- Print the diff.

First command: `snowdrift check --spec grants.yml`.

**Explicitly out of scope for v0**: auto-remediation, full coverage of every Snowflake object type, web UI, pricing/billing, AI features, Terraform state ingestion (YAML only for now). These are *later layers*, not day-one features. Resist scope creep — if a request looks like one of these, flag it and confirm before building.

## Status

Repo is empty (LICENSE + stub README only). No language/toolchain chosen yet, no build/test/lint commands exist. Do not invent commands in this file until they exist on disk. Update this section as soon as the first command lands.

## Working style

The author favors the laziest solution that actually works: stdlib over deps, native features over libraries, shortest diff that ships. Don't add abstractions, config knobs, or "for later" scaffolding without being asked. Boring beats clever.

## gstack (REQUIRED — global install)

**Before doing ANY work, verify gstack is installed:**

```bash
test -d ~/.claude/skills/gstack/bin && echo "GSTACK_OK" || echo "GSTACK_MISSING"
```

If GSTACK_MISSING: STOP. Do not proceed. Tell the user:

> gstack is required for all AI-assisted work in this repo.
> Install it:
> ```bash
> git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
> cd ~/.claude/skills/gstack && ./setup --team
> ```
> Then restart your AI coding tool.

Do not skip skills, ignore gstack errors, or work around missing gstack.

Using gstack skills: After install, skills like /qa, /ship, /review, /investigate,
and /browse are available. Use /browse for all web browsing.
Use ~/.claude/skills/gstack/... for gstack file paths (the global path).
