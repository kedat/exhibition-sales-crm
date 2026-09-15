# Assignment compliance matrix

Last checked: 16 September 2026

This document maps the supplied assignment to implementation and verification
evidence. It is a navigation aid for review, not a replacement for
`ASSIGNMENT.md`. Protected assignment and archive files were not modified.

Status meanings:

- **PASS** — implemented and verified.
- **OUT OF SCOPE** — explicitly unnecessary or excluded by the assignment.

## Sales workflow

| Requirement | Status | Implementation and evidence |
|---|---|---|
| Find an exhibitor or contact | PASS | Indexed company/contact search by names, codes and email; bounded and paginated. Covered by `test_searches_company_and_contact_fields` and `test_search_results_are_paginated_and_bounded`. |
| See relevant opportunities and fair editions | PASS | Company detail groups reusable contacts and edition-specific opportunities. Covered by `test_company_detail_distinguishes_editions_and_company_activity`. |
| Reuse contacts across fair enquiries | PASS | `Contact` belongs to `Company`; opportunities reference an optional primary contact instead of copying it. |
| Keep edition conversations and follow-ups separate | PASS | Activities link to one opportunity and its fair edition; company-level activity remains separate. Covered by `test_opportunity_timeline_is_scoped_to_selected_opportunity`. |
| Update an opportunity | PASS | Sales can edit contact, status, expected close, budget, area, requested height and brief notes. |
| Record customer conversation | PASS | Call, email and meeting records are persisted on the selected opportunity timeline. |
| Schedule and rediscover follow-ups | PASS | Pending tasks appear in paginated overdue, today and upcoming queues with company, contact and context. |
| Save user changes in PostgreSQL | PASS | All business state uses PostgreSQL; stop/start persistence and import-skip behavior were verified. |
| Plan for 100,000 contacts | PASS | PostgreSQL trigram/name/email indexes, code indexes, bounded search input and server-side pagination; rationale is in `README.md`. |

## Handoff assistant

| Requirement | Status | Implementation and evidence |
|---|---|---|
| Add an opportunity action | PASS | `Prepare technical handoff` is available from opportunity detail. |
| Gather CRM and fair information | PASS | Each run snapshots company, contact, opportunity, commercial brief and fair-edition constraints. |
| Propose a next step, then check it | PASS | Preparer emits a structured proposal; Checker consumes and independently evaluates that proposal before coordination. |
| Missing information affects outcome | PASS | Missing budget, area or requested height produces `STOP` with stable reason codes. |
| Conflicting requests affect outcome | PASS | Requested height above fair maximum produces `STOP / HEIGHT_EXCEEDS_FAIR_LIMIT`. |
| Separate Preparer, Checker and Coordinator roles | PASS | Each role has a distinct input/output contract; only Coordinator makes the final `CONTINUE`/`STOP` decision. |
| Deterministic local stand-in | PASS | Versioned ordinary Python functions; clearly labelled `Deterministic local stand-in` and `No model or API` in the UI/snapshot. |
| No keys, external calls or model downloads | PASS | No external model dependency or runtime call is present; source/dependency scan performed. |
| Save every run and information used | PASS | `HandoffRun` stores an immutable value snapshot and policy/assistant version. |
| Save role outputs and decision reason | PASS | Preparer and Checker JSON outputs plus Coordinator decision, reason codes, explanation and next action are persisted. |
| Revisit and rerun after editing | PASS | Run history/detail preserves old snapshots; rerunning creates a new record and shows field/reason/decision differences. |

Additional safety and evaluation evidence:

- Checker results cite source record, field and immutable value.
- A conflicting Checker result can overrule the Preparer's early-review proposal.
- Coordinator recommendations create no side effect until a salesperson reviews
  and confirms a prefilled CRM task.
- An approved task links back to exactly one source run; duplicate approval is
  blocked.
- `HandoffAgentEvaluationTests` covers primary outcomes, deterministic reruns,
  simultaneous blockers, boundary height, evidence, immutable history,
  comparison and human approval.

## Archive import

| Requirement | Status | Implementation and evidence |
|---|---|---|
| Import the whole supplied dataset | PASS | Clean import produces 10,000 companies, 20,000 contacts, 16 fair editions, 15,000 opportunities and 40,000 activities. |
| Preserve useful commercial information and relationships | PASS | Normalized relational models retain stable codes, ownership, editions, monetary values, sizes, notes and activities. |
| Do not modify or reduce source files | PASS | `data/` has no diff; all normalization is in `crm/services/importer.py`. |
| Work when reviewers replace `data/` | PASS | Importer reads the supplied manifest/archive at runtime; no generated records or hard-coded subset. Clean reset/import verified. |
| Document exclusions and interpretations | PASS | README records null, decimal, date/time, status, amount/budget and height decisions; only obsolete `legacy_print_layout` is excluded. |
| Fail safely on invalid archive | PASS | Manifest format, files, headers, checksums, counts, formats and references are validated before transactional business writes. |
| Avoid duplicate import | PASS | Completed imports are identified by dataset version and checksums; restart reports that the archive is already imported. |

## Runtime and portability

| Requirement | Status | Implementation and evidence |
|---|---|---|
| PostgreSQL and full app through `compose.yml` | PASS | Local application image plus PostgreSQL service; no external runtime service. |
| `./dev.sh` builds, starts, migrates and imports | PASS | App entrypoint performs migrations, idempotent import, static collection and Gunicorn startup on port 3000. |
| `docker compose down` keeps data | PASS | Named PostgreSQL volume remains unless reset is requested. |
| `./reset.sh` removes only project resources | PASS | Uses the current Compose project with `down --volumes --remove-orphans`; no global cleanup command. |
| `./verify.sh` works unchanged | PASS | Compose validation and HTTP reachability pass against `http://localhost:3000`. |
| Pinned images, runtimes and packages | PASS | Python `3.13.7`, PostgreSQL `17.6-alpine3.22`, uv `0.8.17` and exact Python dependencies. |
| Lockfile and frozen install | PASS | Committed `app/uv.lock`; Docker build uses `uv sync --frozen`. |
| Approved image sources | PASS | Docker Official Python/PostgreSQL images and assignment-approved `ghcr.io/astral-sh/uv`; application built from submitted source. |
| Required Linux architectures | PASS | No architecture is hard-coded; selected upstream images support the required targets. |
| Working local configuration | PASS | Compose supplies local-only database/application settings; no file or environment setup is required. |

## Protected inputs

The final audit found no changes to:

- `ASSIGNMENT.md`
- `verify.sh`
- `data/`
- `docs/environment.md`
- `docs/image-policy.md`

The source CSVs, manifest, lockfile and required shell scripts are tracked. Root
scripts have executable Git mode and LF line endings.

## Explicitly excluded scope

| Item | Status | Reason |
|---|---|---|
| Login, permissions and billing | OUT OF SCOPE | Assignment assumes one user. |
| Floor plans, 3D models, quotations, bills of materials and technical approvals | OUT OF SCOPE | Explicitly excluded from this sales tool. |
| Chat interface and agent framework | OUT OF SCOPE | Explicitly unnecessary; ordinary functions are permitted. |
| API keys, external model calls and model downloads | OUT OF SCOPE | Explicitly prohibited. |
| Automatic email/customer contact | OUT OF SCOPE | Explicitly unnecessary; human approval boundary retained. |
| Public deployment and video | OUT OF SCOPE | Not requested. |

## Verification checkpoint

```text
34 automated tests pass
Django system check passes
No model changes are missing from migrations
Compose configuration is valid
./verify.sh passes unchanged
Application is reachable at http://localhost:3000
Clean import contains 85,016 business records
Restart retains data and skips duplicate import
Anonymous repository request returns HTTP 200
```

## Final submission controls

Repository implementation compliance and external submission are separate. The
candidate must still record actual time spent in the README, commit and push the
final state, verify that exact commit anonymously, and send the required email.
Those actions cannot be proven by a document inside the commit itself.

The operational checklist and exact email template are in
`SUBMISSION_CHECKLIST.md`; the presentation path is in `docs/DEMO.md`.
