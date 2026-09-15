# Exhibition sales CRM

A focused CRM for exhibition-stand sales, built from the supplied legacy archive.
It keeps exhibitors, reusable contacts, fair-edition enquiries and activity in
the correct scope, then uses a deterministic multi-role assistant to decide
whether an enquiry is safe to hand to the technical team.

The assistant is intentionally not a chat interface or an external language
model. It is a local, testable stand-in that demonstrates role separation,
critique, policy gating, evidence, immutable runs and human-approved actions.

## Quick start

Requirements: Docker Engine and Docker Compose only.

```bash
./dev.sh
```

On first use this builds the application, creates the PostgreSQL schema and
imports the complete archive. When the log reports that Gunicorn is listening,
open [http://localhost:3000](http://localhost:3000).

In another terminal, verify the running application:

```bash
./verify.sh
```

Lifecycle commands:

```bash
# Stop while retaining imported data and user changes
docker compose down

# Remove only this project's persistent resources and data
./reset.sh
```

No environment variables, API keys, host runtimes or configuration files are
required.

## What is implemented

- Search by exhibitor name/code and contact name/code/email, with bounded,
  paginated queries.
- Company pages with reusable contacts, edition-specific opportunities and
  company-level activity.
- Opportunity pages scoped to one fair edition and its own activity timeline.
- Opportunity editing, conversation logging and pending follow-up scheduling.
- Overdue, due-today and upcoming follow-up queues.
- Complete, validated and idempotent import into PostgreSQL.
- A deterministic technical-handoff assistant with persisted run history.
- Comparison between reruns after a salesperson changes the brief.
- Evidence for every technical check.
- Human review before an assistant recommendation becomes a CRM task.

Implementation progress and verification evidence are recorded in
[PROGRESS.md](PROGRESS.md).

## Handoff assistant

### Orchestration

```text
CRM + fair snapshot
        |
        v
Preparer -- structured brief and proposed next step
        |
        v
Checker  -- independent checks, evidence and blocking issues
        |
        v
Coordinator -- CONTINUE or STOP under the selected policy
        |
        v
Immutable HandoffRun
        |
        +--> salesperson edits the source brief and reruns
        |
        +--> salesperson reviews and approves a suggested CRM task
```

The roles have deliberately different contracts:

| Role | Observes | Produces | Cannot do |
|---|---|---|---|
| Preparer | CRM/fair snapshot | Structured brief, missing-field list and proposal | Approve technical work |
| Checker | Snapshot and Preparer proposal | Independent checks, source evidence and blockers | Change CRM data or make the final decision |
| Coordinator | Both role outputs and policy | Decision, stable reason codes, explanation and next action | Contact a customer or create work automatically |
| Salesperson | Decision and recommendation | Corrected brief or approved follow-up | Change historical run snapshots |

Each run stores the values it used, both role outputs, the policy version, final
decision, reason codes, explanation and next action. Old runs therefore remain
explainable even after the live opportunity or fair information changes.

### Selected handoff policy

Sales may prepare an early proposal once the fair and client budget are known.
Technical work may continue only when the allocated area and requested height
are also known, and the height is within the fair edition's maximum.

This reconciles the competing requests:

- Sales gets an early, prepared proposal instead of waiting to assemble a
  perfect brief manually.
- Technical retains an independent safety gate before design work starts.
- The Coordinator converts both positions into one consistent and auditable
  outcome.
- A conflict is never hidden by missing information; all detected blockers are
  reported together.

The outcome is `CONTINUE` only when all gates pass. Otherwise it is `STOP` with
one or more stable reason codes, such as `MISSING_STAND_AREA` or
`HEIGHT_EXCEEDS_FAIR_LIMIT`.

### Try an incomplete enquiry and the feedback loop

Open [OP011026](http://localhost:3000/opportunities/OP011026/). Its client budget,
fair and requested height are known, but its allocated area is missing.

1. Select **Prepare technical handoff**.
2. Observe `STOP / MISSING_STAND_AREA` and the Checker's source evidence.
3. Select **Review and create follow-up**. The recommendation is prefilled, but
   no task exists until you review the text/date and confirm it.
4. Edit the opportunity and set allocated area to `24.00` m².
5. Run the assistant again.
6. Observe `STOP → CONTINUE`, the field-level change and the resolved reason.
7. Open the earlier run from history; its missing-area snapshot is unchanged.

### Try a conflicting and a complete enquiry

- [OP000005](http://localhost:3000/opportunities/OP000005/) requests `6.00` m
  against a `5.00` m fair maximum. The Preparer can propose early review, but the
  Checker rejects it and the Coordinator returns
  `STOP / HEIGHT_EXCEEDS_FAIR_LIMIT`.
- [OP000230](http://localhost:3000/opportunities/OP000230/) is complete and within
  its fair limit, so it returns `CONTINUE / READY_FOR_TECHNICAL_HANDOFF`.

All examples come from the supplied archive and are restored by `./reset.sh`.

## Stack and pinned versions

| Component | Version / choice |
|---|---|
| Python runtime | `3.13.7` (`python:3.13.7-slim-bookworm`) |
| Django | `5.2.6` |
| PostgreSQL | `17.6` (`postgres:17.6-alpine3.22`) |
| psycopg | `3.2.10` binary distribution |
| Gunicorn | `23.0.0` |
| WhiteNoise | `6.9.0` |
| uv | `0.8.17` |
| UI | Server-rendered Django templates and local CSS; no CDN |

Dependencies are locked in `app/uv.lock` and installed with
`uv sync --frozen`. Images and runtimes are precisely tagged, and no architecture
is hard-coded; the selected images support the required Linux architectures.

## Data model and import decisions

The importer reads the manifest and all four semicolon-delimited UTF-8 CSVs. A
clean import creates:

| Entity | Records |
|---|---:|
| Companies | 10,000 |
| Contacts | 20,000 |
| Fair editions | 16 |
| Opportunities | 15,000 |
| Activities | 40,000 |

Important decisions:

- Stable legacy codes are retained as unique business identifiers.
- Repeated company columns in the contact export are deduplicated by company
  code and checked for inconsistent repeated values.
- Contacts belong to companies and are reused by opportunities rather than
  copied into every fair enquiry.
- Fair editions are distinct records, so last year's conversations and terms do
  not leak into this year's opportunity.
- Empty values become database `NULL`; they are not treated as zero or approval.
- Monetary, area and height values use decimals. Decimal commas and `DD/MM/YYYY`
  source dates are parsed explicitly.
- Activity timestamps are interpreted in `Europe/Rome`.
- Legacy sales status casing and surrounding whitespace are normalized.
- A requested height above the fair maximum is preserved as source truth for the
  Checker instead of being rejected or silently corrected during import.
- `amount_eur` and `client_budget_eur` remain separate because the archive gives
  them different commercial meanings.
- Optional contact and activity-opportunity relationships remain optional.
- Only `legacy_print_layout` is excluded because the archive identifies it as
  obsolete presentation metadata.

Before any business records are written, the importer validates the manifest,
file presence, exact headers, SHA-256 checksums, row counts, source formats and
foreign references. Business writes are transactional. A completed import is
identified by dataset version and checksums, so later starts preserve changes and
skip a duplicate import.

## Search and expected growth

Everyday search is bounded to six terms, 100 input characters and 20 results per
page. PostgreSQL trigram expression indexes support names and email, while unique
code indexes support prefix lookup. Follow-up lists and histories are paginated,
so the application does not render the whole archive at once. These choices keep
the read path practical as the archive approaches the stated 100,000 contacts.

## AI-assisted development approach

AI assistance was used to:

- explore an unfamiliar CRM domain and translate the archive into workflows;
- identify ambiguities and competing stakeholder needs;
- propose implementation alternatives and bounded phase plans;
- generate implementation candidates;
- perform adversarial review and identify edge cases;
- review assignment compliance and test coverage.

Human responsibility remained with:

- choosing the product scope and what not to build;
- defining the handoff policy and conflict precedence;
- accepting, changing or rejecting generated implementation proposals;
- validating business assumptions against the supplied files;
- verifying behavior through tests, clean imports and restart checks;
- retaining responsibility for the final submitted result.

Generated code was treated as a proposal requiring evidence, not as proof of
correctness. The behavioral evaluations, database constraints, immutable traces
and reproducible Compose lifecycle are the verification boundary.

See [docs/DECISIONS.md](docs/DECISIONS.md) for the main product and engineering
trade-offs.

## Tests

Build the image, then run the full suite without requiring Python on the host:

```bash
docker compose build app
docker compose run --rm --entrypoint /app/.venv/bin/python app manage.py test
```

The current suite contains 34 tests covering models, full import behavior, read
and write workflows, orchestration, immutable history, evidence, deterministic
output, adversarial scenarios, rerun comparison and human-approved actions.

Run only the assistant behavioral evaluations with:

```bash
docker compose run --rm --entrypoint /app/.venv/bin/python app \
  manage.py test crm.tests.test_handoff.HandoffAgentEvaluationTests
```

## Deliberate scope and unfinished work

The following are intentionally outside this first version:

- Authentication, permissions and billing: the assignment assumes one archive
  user.
- General company/contact administration: the MVP focuses on the requested sales
  workflow.
- Chat UI, external models, model downloads and agent frameworks: unnecessary or
  prohibited for this deterministic local stand-in.
- Automatic email/customer contact and automatic technical approval: assistant
  actions remain under human control.
- Floor plans, 3D models, quotations and bills of materials: explicitly outside
  the sales-tool scope.
- Relevance-ranked search and advanced activity filters: deterministic indexed
  search and pagination cover the MVP path.
- Streaming/staging-table import and a concurrent-import lock: the validated
  in-memory import is suitable for the supplied archive and the single Compose
  entrypoint. These would be revisited for materially larger files or multiple
  import workers.
- Marking follow-up tasks complete is a useful next workflow improvement.

Optional future experiments include policy simulation and a visual evaluation
dashboard. They were not added because they do not improve the required sales
workflow as much as evidence, rerun comparison and human approval do.

## Review notes

**Time spent:** `TODO before submission — replace with your actual hours and minutes.`

- [docs/DEMO.md](docs/DEMO.md) contains a 5–7 minute presentation path and talk
  track.
- [docs/DECISIONS.md](docs/DECISIONS.md) records the main accepted and rejected
  design alternatives.
- [COMPLIANCE.md](COMPLIANCE.md) maps each assignment requirement to implementation
  and verification evidence.
- [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) contains the final clean-clone,
  repository and email checks.
