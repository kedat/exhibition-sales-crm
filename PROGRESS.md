# Implementation progress

Last updated: 15 September 2026

This document tracks the implementation against the staged delivery plan. It is
intended to help reviewers distinguish completed work, deliberate scope choices,
and genuinely unfinished work without having to infer progress from the UI or Git
history alone.

## Current position

The functional MVP described in Phases 1–6 is implemented. The remaining work is
operational hardening, final documentation, demo preparation, and submission.

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 1 | Containerized application skeleton | Complete | `f2cc5f6` |
| 2 | PostgreSQL schema and migrations | Complete | `5fe7327` |
| 3 | Transactional legacy archive import | Complete | `9acdb62` |
| 4 | Read-side CRM workflow | Complete | `66619c6` |
| 5 | Opportunity updates and follow-ups | Complete | `8e95520` |
| 6 | Deterministic handoff orchestration | Complete, not yet committed | Current working tree |

Current verification checkpoint:

```text
27 automated tests pass
Django system check passes
No missing migrations
All three CRM migrations apply successfully
./verify.sh passes unchanged
Protected assignment and data files are unchanged
Application is reachable at http://localhost:3000
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
- Comparing field-level changes between two historical runs is a useful optional
  improvement after the required phases.
- The assistant recommends a next action but does not execute it automatically;
  sales retains control of customer communication and technical handoff.

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

## Possible agentic extensions after the required work

These should remain behind Phases 7 and 8 in priority order:

1. **Run comparison** — show exactly which snapshot fields changed between a
   `STOP` run and the later `CONTINUE` run.
2. **Remediation planner** — translate reason codes into a structured checklist
   that sales can approve, such as collecting a plot drawing or revising height.
3. **Human-approved tool action** — allow the coordinator's recommendation to
   prefill a follow-up task, but require the salesperson to confirm before saving.
4. **Policy simulation** — compare a Sales-first policy and the selected
   Technical-safe policy against the same snapshot without changing stored CRM
   data.
5. **Evaluation dashboard** — run a fixed scenario suite and display outcome,
   reason-code, determinism, and regression results as an agent evaluation rather
   than only unit-test output.
6. **Evidence links** — attach every Checker finding to the exact snapshot field
   that supports it, making the reasoning trace even easier to inspect.

The first and third options would add the most visible agentic value to a demo
without violating the no-external-model constraint or expanding into floor-plan,
quotation, or technical-approval work.

## Remaining project phases

### Phase 7 — Tests and operational hardening

- Run the final clean reset/import/start/restart workflow.
- Expand edge-case coverage where valuable.
- Recheck shell executable bits, protected files, credentials, pinned versions,
  and absence of external runtime calls.
- Complete the end-to-end manual workflow on the final review commit.

### Phase 8 — README, demo, and submission

- Consolidate architecture, import decisions, trade-offs, handoff policy,
  examples, unfinished work, and actual time spent into `README.md`.
- Prepare the 5–7 minute demo path and fallback conflict example.
- Commit and push the final tested state.
- Verify anonymous public repository access.
- Submit the exact required email with the full tested commit hash.
