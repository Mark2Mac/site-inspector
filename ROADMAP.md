# Site Inspector — Development Roadmap

## Baseline complete

These workstreams are considered integrated and green in the current baseline:

- Core crawler foundation
- Analysis pipeline
- Duplicate detection hardening + validation layer
- Stability layer (CLI regression tests + golden schema checks)
- Crawl quality guardrails
- SEO auditing
- AI crawler optimization
- Reporting and developer experience
- Packaging and public release prep

## Current focus

### Production Hardening Program

The next phase is not about adding broad new capabilities. It is about making the current tool safer to publish and easier to maintain.

This phase is intentionally split into **4 controlled iterations** so changes stay small, testable, and reversible.

---

## Iteration P1 — Packaging cleanup

Goal: remove packaging debt and align public project metadata with the real state of the tool.

Scope:
- clean `pyproject.toml` metadata
- remove deprecated packaging fields and warnings
- tighten `MANIFEST.in`
- align `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `RELEASING.md`
- harden `.gitignore` so local artifacts never leak into releases

Acceptance:
- `py -m build --sdist --wheel` passes
- `py -m twine check` passes
- packaging warnings are reduced or removed
- metadata tests pass

Status: **in progress with this iteration**

---

## Iteration P2 — Output contracts

Goal: freeze the most important output shapes so future refactors cannot silently break consumers.

Scope:
- contract tests for `run.json`
- contract tests for `diff.json`
- contract tests for `quality_summary.json`
- stronger golden checks on critical nested fields
- schema/version notes in docs

Acceptance:
- contract tests fail on accidental output drift
- top-level and critical nested fields are explicitly covered
- docs describe the intended output contract

---

## Iteration P3 — Reliability and diagnostics

Goal: improve production robustness without changing product scope.

Scope:
- normalize error messages and warning classes
- improve exit-code consistency
- add clearer runtime diagnostics/logging
- make failure causes easier to triage in CLI output and reports

Acceptance:
- failures are easier to classify
- warnings vs hard failures are clearer
- runner and CLI messages are consistent

---

## Iteration P4 — Validation corpus

Goal: validate the tool beyond a single favorite smoke target.

Scope:
- richer local fixture(s)
- more than one live smoke target
- fast vs live validation profile separation
- confidence checks across different site shapes

Acceptance:
- validation no longer depends on one site only
- live smoke checks remain optional but representative
- false confidence from a single target is reduced

---

## Target outcome

A Windows-first CLI tool capable of:
- crawling and analyzing websites
- detecting structural and content issues
- identifying duplicate content clusters
- evaluating AI crawler accessibility
- generating structured audit reports
- building and shipping as a public Python package with a stable release process
