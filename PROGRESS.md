# Implementation progress

Last updated: 16 September 2026

This document tracks the implementation against the staged delivery plan. It is
intended to help reviewers distinguish completed work, deliberate scope choices,
and genuinely unfinished work without having to infer progress from the UI or Git
history alone.

## Current position

The functional MVP, agentic quality/safety layer and reviewer documentation
described in Phases 1–8 are implemented. Only candidate-owned submission steps
remain: record actual time spent, commit/push this phase, verify public access and
send the required email.

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 1 | Containerized application skeleton | Complete | `f2cc5f6` |
| 2 | PostgreSQL schema and migrations | Complete | `5fe7327` |
| 3 | Transactional legacy archive import | Complete | `9acdb62` |
| 4 | Read-side CRM workflow | Complete | `66619c6` |
| 5 | Opportunity updates and follow-ups | Complete | `8e95520` |
| 6 | Deterministic handoff orchestration | Complete | `3b2046e` |
| 7 | Agentic quality, safety and operational hardening | Complete | `00da573` |
| 8 | Reviewer experience and submission preparation | Complete | Final submission documentation |

Current verification checkpoint:

```text
34 automated tests pass
Django system check passes
No missing migrations
All four CRM migrations apply successfully
./verify.sh passes unchanged
Protected assignment and data files are unchanged
Application is reachable at http://localhost:3000
Clean reset imports all 85,016 archive records
Later starts retain data and skip duplicate import
```

## Phase 1 — Containerized application skeleton

### Objective

Create the smallest reproducible application that starts entirely through Docker
Compose and is reachable on the required port.

### Delivered

- Django application served by Gunicorn at `http://localhost:3000`.
- PostgreSQL service with a persistent, project-scoped volume.
- Health-gated startup: the application waits for PostgreSQL readiness.
- Application startup runs migrations before starting the web server.
- Exactly pinned Python, package-manager, dependency, PostgreSQL, and utility
  image versions.
- Committed `uv.lock` and frozen dependency installation.
- Linux images support both required CPU architectures without a hard-coded
  platform.
- Local configuration is supplied through Compose; no credentials or setup files
  are required from the reviewer.
- Europe/Rome application timezone.
- Local static styling without external CDNs.
- Supplied `dev.sh`, `reset.sh`, and `verify.sh` workflows are supported.

### Not implemented in this phase

- CRM schema, archive data, or business workflows. These intentionally began in
  later phases.
- Production deployment, authentication, authorization, and billing. These are
  outside the assignment scope.

### Verification

- Clean image build succeeds.
- Database health check succeeds.
- HTTP and database health endpoint succeeds.
- `./verify.sh` succeeds without modification.

## Phase 2 — PostgreSQL schema and migrations

### Objective

Represent the legacy sales archive and retain auditable assistant runs without
flattening company, opportunity, or fair-edition boundaries.

### Delivered

- Models and migrations for:
  - `Company`
  - `Contact`
  - `FairEdition`
  - `Opportunity`
  - `Activity`
  - `HandoffRun`
  - `ImportRun`
- Stable legacy codes are unique.
- Contacts belong to companies and are reused across opportunities.
- Opportunities require a company and a fair edition.
- Primary contacts and activity opportunities preserve source nullability.
- Sales status is separate from the technical handoff decision.
- Decimal fields preserve money, area, and height accurately.
- Requested heights above a fair limit remain storable so the Checker can detect
  the conflict instead of losing the original request.
- Date constraints, positive/non-negative numeric constraints, foreign keys, and
  workflow indexes.
- `pg_trgm` extension and expression indexes for company/contact search.
- JSON snapshots and role outputs for immutable handoff history.

### Remaining or deliberately deferred

- Cross-company contact/opportunity consistency is enforced by model validation,
  forms, and importer validation rather than a PostgreSQL trigger. Foreign-key,
  uniqueness, date, and numeric integrity are enforced in PostgreSQL.
- User/owner tables are omitted because the brief assumes one user.

### Verification

- Migrations apply to an empty PostgreSQL database and safely run again.
- Model tests cover nullable relationships, invalid ownership, numeric
  constraints, height conflicts, and JSON handoff storage.

## Phase 3 — Full transactional CSV importer

### Objective

Import the complete supplied archive on first use and make later starts safe and
idempotent.

### Delivered

- Reads `manifest.json` and validates its format contract.
- Validates the presence, exact headers, SHA-256 checksums, and row counts of all
  four CSV files.
- Parses semicolon-delimited UTF-8 source files.
- Deduplicates repeated companies by `company_code` while validating repeated
  company values for consistency.
- Imports records in foreign-key dependency order.
- Normalizes whitespace/casing variations in legacy sales status.
- Parses decimal commas, `DD/MM/YYYY` dates, and Europe/Rome date-times.
- Converts empty values to database `NULL`.
- Preserves optional primary-contact and activity-opportunity relationships.
- Excludes only the obsolete `legacy_print_layout` column.
- Validates referenced company, contact, opportunity, and fair codes before
  database writes.
- Wraps all business-entity writes in one database transaction.
- Records completed and failed `ImportRun` metadata.
- Identifies a completed import by dataset version and source checksums and skips
  duplicate imports on later starts.
- Runs automatically after migrations in the container entrypoint.

Imported record totals:

| Entity | Imported records |
|---|---:|
| Companies | 10,000 |
| Contacts | 20,000 |
| Fair editions | 16 |
| Opportunities | 15,000 |
| Activities | 40,000 |

### Remaining or deliberately deferred

- The current importer validates and normalizes the supplied archive in memory.
  This is appropriate for the supplied dataset and the stated near-term growth;
  a streaming/staging-table importer would be the next step for substantially
  larger archives.
- Concurrent import locking is not added because Compose starts one application
  entrypoint. Dataset identity and database uniqueness still prevent silent
  duplication.

### Verification

- Full reset/import and restart/skip lifecycle tested.
- Imported counts and relationship integrity checked against PostgreSQL.
- Forced mid-import failure test confirms all business entities roll back.
- Parser, checksum, normalization, null handling, and idempotency tests pass.

## Phase 4 — Read-side CRM workflow

### Objective

Give account managers a bounded, edition-aware way to find customers and act on
follow-ups without mixing unrelated opportunity history.

### Delivered

- Global search from every page.
- Search by:
  - company name and code;
  - contact first/last name and code;
  - contact email.
- Multi-word search, a 100-character query bound, 20 results per page, and
  server-side pagination.
- Search branches use PostgreSQL trigram and code indexes rather than a broad
  reverse-join sequential scan.
- Follow-up dashboard with Overdue, Due today, and Upcoming buckets.
- Includes every activity type with `follow_up_on`, not only tasks.
- Supports both opportunity-level and company-level follow-ups.
- Each follow-up bucket has independent pagination, so all 5,718 imported
  follow-ups remain reachable without rendering thousands of rows.
- Company detail shows company information, reusable contacts, edition-specific
  opportunities, and only company-level activity.
- Opportunity detail shows its company/contact, commercial values, fair edition,
  fair limit, brief notes, and only that opportunity's activity timeline.
- Multiple editions of the same fair remain visibly distinguishable by edition
  code and dates.
- Responsive interface with no external frontend dependencies.

### Remaining or deliberately deferred

- Search results are deterministic and alphabetic rather than relevance-ranked.
- Advanced activity filters and full-text activity-note search are not required
  for the MVP.
- Server-side pagination is intentionally simple; no JavaScript client state is
  required.

### Verification

- Tests cover every search field, multi-word contact search, result bounds,
  pagination, all five activity types, company-level follow-ups, fair editions,
  and opportunity timeline isolation.
- Real archive pages for `OP011026` and `OP000005` return successfully.

## Phase 5 — Write workflow and follow-ups

### Objective

Let sales correct an opportunity, record customer contact, and create a findable
next action without adding unrelated CRM administration screens.

### Delivered

- Opportunity edit form for:
  - primary contact;
  - sales status;
  - expected close date;
  - client budget;
  - allocated stand area;
  - requested height;
  - brief notes.
- Server-side validation requires supplied budget, area, and height values to be
  greater than zero.
- Primary-contact choices are limited to the opportunity's company and validated
  again on the server.
- Expected close date cannot precede the opportunity open date.
- Height above the fair maximum remains valid input for later conflict detection.
- Conversation form records a completed call, email, or meeting against the
  current company and opportunity, with Europe/Rome date-time interpretation and
  an optional follow-up date.
- Standalone follow-up form creates a pending task with company and opportunity
  context.
- New conversations and tasks immediately appear in the correct timeline and
  follow-up dashboard.
- POST/redirect/GET flow, CSRF protection, validation messages, and visible save
  confirmation.
- Changes persist across a Compose stop/start cycle.

### Remaining or deliberately deferred

- Marking a follow-up complete is an optional post-MVP improvement.
- Creating a new company-level task from the UI is not required; imported
  company-level follow-ups are fully supported and displayed.
- General company/contact CRUD is intentionally omitted to keep the workflow
  focused on the assignment.

### Verification

- Tests cover all editable fields, invalid numbers, cross-company contacts,
  height conflicts, conversations, pending tasks, timeline placement, and
  dashboard visibility.
- A temporary real-database opportunity survived a Compose restart with its two
  new activities; the temporary records were removed after verification.

## Phase 6 — Deterministic handoff orchestration

### Objective

Reconcile Sales' request for early technical involvement with Technical's safety
requirements through an explainable, auditable multi-role workflow.

### Chosen policy

Sales may propose an early technical review once the fair and client budget are
known. Technical work may continue only when the allocated area and requested
height are also known and the requested height does not exceed the edition's
maximum.

This deliberately gives Sales an early proposal while preserving Technical's
final safety gate.

### Delivered

- Snapshot service records values, not only foreign-key IDs:
  - company and sales representative;
  - primary contact details;
  - opportunity and commercial fields;
  - area, requested height, and brief notes;
  - fair edition, dates, venue, and maximum height;
  - assistant implementation and policy version.
- Preparer role:
  - creates a structured technical brief;
  - labels known and missing fields;
  - requests missing commercial information; or
  - proposes early technical review when fair and budget are known.
- Checker role:
  - independently checks area and requested height;
  - checks availability of the fair limit;
  - compares requested height with the fair maximum;
  - determines whether the Preparer's proposal is safe;
  - reports structured blocking issues.
- Coordinator role:
  - returns exactly `CONTINUE` or `STOP`;
  - stores stable reason codes;
  - produces a human-readable reason and concrete next action.
- Every run stores the input snapshot, both role outputs, coordinator decision,
  reason codes, reason, next action, and timestamp.
- Database migration converts any older lowercase decisions and adds structured
  reason-code storage.
- Opportunity UI includes:
  - `Prepare technical handoff` / `Run handoff again` action;
  - explicit `Deterministic local stand-in` and `No model or API` labels;
  - latest decision and reason codes;
  - role-by-role output and technical checks;
  - missing/conflicting information;
  - complete run history;
  - an immutable historical snapshot page for each run.
- Editing the opportunity and rerunning creates a new record while preserving the
  previous snapshot.

Primary outcome matrix:

| Scenario | Coordinator decision | Reason code |
|---|---|---|
| Missing client budget | `STOP` | `MISSING_CLIENT_BUDGET` |
| Missing allocated area | `STOP` | `MISSING_STAND_AREA` |
| Missing requested height | `STOP` | `MISSING_REQUESTED_HEIGHT` |
| Requested height exceeds fair maximum | `STOP` | `HEIGHT_EXCEEDS_FAIR_LIMIT` |
| Complete and within limit | `CONTINUE` | `READY_FOR_TECHNICAL_HANDOFF` |

### Remaining or deliberately deferred

- No chat interface, agent framework, automatic email, model download, API key,
  or external model call. These are explicitly unnecessary or prohibited by the
  assignment.
- Field-level run comparison and human-approved follow-up creation were deferred
  at this checkpoint and completed in Phase 7.
- The assistant never contacts a customer or starts technical work automatically;
  sales retains control of external communication and technical handoff.

### Verification

- All five primary outcomes are covered by deterministic tests.
- Tests prove Preparer and Checker have different responsibilities.
- Tests prove snapshots retain their old values after editing and rerunning.
- POST-only execution and history/snapshot UI are covered.
- Real archive checks produced:

```text
OP011026 → STOP / MISSING_STAND_AREA
OP000005 → STOP / HEIGHT_EXCEEDS_FAIR_LIMIT
OP000230 → CONTINUE / READY_FOR_TECHNICAL_HANDOFF
```

- Temporary verification runs were removed after the check.
- Source scan confirms no external model/API client dependency or call.

## Why this is more than CRUD

The CRM screens provide the data and human workflow, but the handoff feature is a
small agentic system because it performs a stateful reasoning cycle with separate
responsibilities:

```text
Observe CRM and fair state
        ↓
Preparer proposes a brief and next step
        ↓
Checker independently critiques completeness and safety
        ↓
Coordinator applies policy and decides CONTINUE or STOP
        ↓
Persist evidence, decision, and next action
        ↓
Human edits the source state and reruns the cycle
```

The implementation is deterministic because the assignment prohibits external
models. Determinism is useful here: the same snapshot always produces the same
decision, the policy is testable, and reviewers can explain every outcome.

The agentic value comes from orchestration, role separation, critique, policy
gating, state observation, and an auditable feedback loop—not from pretending a
language model is present.

## Phase 7 — Agentic quality, safety and operational hardening

### Objective

Make the orchestration visibly responsive to human corrections, ground its
findings in evidence, connect recommendations to controlled CRM actions, and
evaluate behavior rather than merely test CRUD endpoints.

### Delivered

- Run comparison against the immediately preceding run for the same opportunity:
  - decision transition such as `STOP → CONTINUE`;
  - before/after values for decision-relevant snapshot fields;
  - resolved and newly introduced reason codes;
  - an explicit deterministic confirmation when no relevant input changed.
- Evidence-backed Checker output:
  - every check identifies the source record, field, and immutable value used;
  - height conflicts cite both requested height and the fair maximum;
  - missing values remain explicit evidence rather than disappearing from output.
- Human-approved action workflow:
  - coordinator recommendations prefill a follow-up form;
  - the salesperson can edit the action and date before confirming;
  - no task is created on page load;
  - each approved task retains provenance to its source `HandoffRun`;
  - a database one-to-one constraint and UI guard prevent duplicate approval;
  - the opportunity timeline links the task back to its immutable run.
- Agent behavior evaluations cover:
  - deterministic output for the same snapshot;
  - multiple simultaneous blockers;
  - the Checker overruling an unsafe Preparer proposal;
  - height exactly equal to the fair limit;
  - evidence retained with a conflict;
  - changed input and decision comparison;
  - human approval and duplicate-action prevention.
- Clean operational lifecycle completed against the original archive:
  - project-scoped Compose volume reset;
  - empty-schema migration through `0004`;
  - complete archive import;
  - unchanged reviewer verification script;
  - app restart with no migration work and duplicate import skipped.

### Remaining or deliberately deferred

- A policy-simulation UI is not necessary to demonstrate the selected policy and
  would introduce a second policy that stakeholders did not request.
- Agent evaluation remains executable automated tests rather than a production
  dashboard. This keeps reviewer-facing UI focused on the sales workflow.
- The assistant creates only an internal task after approval. It does not send an
  email, contact the client, or approve technical work.

### Verification

```text
34 automated tests pass
Django system check passes
No model changes are missing from migrations
./verify.sh passes unchanged
Clean import: 10,000 companies, 20,000 contacts, 16 fair editions,
              15,000 opportunities and 40,000 activities
Restart: no migrations to apply; legacy archive already imported, skipping
```

## Phase 8 — Reviewer experience and submission preparation

### Objective

Make the product, agent architecture, trade-offs, verification evidence and demo
path understandable without requiring the reviewer to reconstruct intent from
the source code or development conversation.

### Delivered

- Replaced the starter README with reviewer-facing documentation covering:
  - clean startup and lifecycle commands;
  - implemented sales workflows;
  - assistant architecture and explicit role contracts;
  - selected handoff policy and competing stakeholder requests;
  - reproducible incomplete, conflicting and complete archive examples;
  - pinned stack versions;
  - data-model, import and search decisions;
  - AI-assisted development method and human responsibility;
  - test commands, deliberate scope and unfinished work.
- Added `docs/DECISIONS.md` with accepted and rejected product/engineering
  alternatives, including the deterministic stand-in, conflict preservation,
  immutable snapshots, evidence and human approval boundary.
- Added `docs/DEMO.md` with a timed 5–7 minute English presentation:
  - incomplete enquiry and role separation;
  - human-approved action;
  - correction and `STOP → CONTINUE` rerun comparison;
  - adversarial height conflict;
  - engineering evidence and likely interview questions.
- Added `SUBMISSION_CHECKLIST.md` with clean-clone, demo, public repository,
  commit-hash and exact email-format checks.
- Added `COMPLIANCE.md` as a concise requirement-to-evidence matrix, including
  explicit out-of-scope items and pending candidate-owned submission actions.
- Verified the three documented examples directly against the clean PostgreSQL
  import:
  - `OP011026`: allocated area missing;
  - `OP000005`: requested `6.00 m`, fair maximum `5.00 m`;
  - `OP000230`: complete and within its fair limit.

### Remaining candidate-owned steps

- Replace the single README time-spent placeholder with the actual hours and
  minutes. This cannot be inferred reliably from commit timestamps.
- Rehearse once, reset to known data, then commit and push Phase 8.
- Verify that the public repository opens without authentication.
- Copy the full final commit hash and send the required submission email. These
  external submission actions are intentionally not performed by the app.

### Verification

- All Phase 8 claims are traceable to the assignment, source, tests or clean
  PostgreSQL archive.
- Documentation uses archive-backed demo records rather than test fixtures.
- No protected assignment, environment, policy, verification or data file was
  changed.
- Phase 8 changes documentation only; the final Phase 7 runtime checkpoint
  remains 34 passing tests and an unchanged `verify.sh` pass.
