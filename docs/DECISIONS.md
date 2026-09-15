# Product and engineering decisions

This log captures the decisions most relevant to reviewing the solution. It is
not a record of every implementation detail.

## 1. Build a focused sales workflow, not a general-purpose CRM

**Context:** The archive is large, but the assignment asks account managers to
find the right exhibitor/enquiry, update a brief, record contact and act on
follow-ups.

**Decision:** Implement those end-to-end paths and omit broad company/contact
administration.

**Reason:** Workflow completeness and correct edition boundaries provide more
value than a larger set of generic CRUD screens. Authentication and permissions
are also excluded because the scenario explicitly assumes one user.

## 2. Separate companies, contacts, opportunities and fair editions

**Context:** Contacts repeat company fields in the export, and one exhibitor may
return for multiple fairs or editions.

**Decision:** Normalize the entities and attach activity either to a company or
one opportunity.

**Reason:** Contacts remain reusable, while an opportunity's conversations,
budget and brief cannot accidentally be presented as belonging to another
edition. Stable legacy codes preserve traceability to the source archive.

**Rejected:** Flattening the archive into one table or showing all company
activity on every opportunity. Both would recreate the historical-context error
described in the brief.

## 3. Preserve conflicts instead of validating them away

**Context:** A customer can request a height above the fair limit.

**Decision:** Store the positive requested height unchanged and let the Checker
compare it with the edition maximum.

**Reason:** The request is source truth, not an approval. Rejecting it at form or
import time would erase the conflict the handoff workflow must surface.

## 4. Use a Sales-early, Technical-safe handoff policy

**Context:** Sales wants Technical involved when fair and budget are known;
Technical wants area and height checked first.

**Decision:** The Preparer may propose an early review after the commercial gate,
but the Coordinator may continue only after the independent technical gate
passes.

**Reason:** This preserves Sales' speed at the proposal stage without allowing
unsafe or incomplete work to enter technical design. All blockers are returned
together so one conflict is not hidden behind another missing value.

## 5. Use explicit role contracts

**Decision:** The Preparer produces a structured brief and proposal; the Checker
independently evaluates technical completeness and constraints; the Coordinator
alone applies the policy and decides `CONTINUE` or `STOP`.

**Reason:** Role boundaries make critique observable and testable. In the height
conflict scenario, the Preparer proposes early review and the Checker overturns
it; the roles are not three labels for the same decision function.

## 6. Use a deterministic local stand-in

**Context:** The assignment prohibits API keys, external model calls and model
downloads and explicitly permits ordinary functions in one process.

**Decision:** Implement versioned deterministic Python role functions and label
them clearly in the UI and snapshots.

**Reason:** It obeys the runtime constraint, works offline, makes equal inputs
produce equal outputs, and permits exact behavioral evaluation. A real model or
agent framework would add non-determinism, dependencies and presentation value
without improving the required decision.

## 7. Persist values and outputs as immutable runs

**Decision:** Store a value snapshot, assistant/policy versions, both role
outputs, Coordinator fields and reason codes for every execution.

**Reason:** Saving only foreign keys would make a historical decision appear to
use today's edited values. Snapshots keep each run independently explainable and
enable before/after comparison on rerun.

## 8. Ground checks in evidence

**Decision:** Each Checker result records the source record, field and value used.
Height comparison cites both the opportunity request and fair maximum.

**Reason:** Reviewers and salespeople can inspect why a check passed or failed
without trusting prose alone. Evidence remains part of the historical role
output.

## 9. Require human approval for side effects

**Decision:** The Coordinator proposes a next action. A salesperson must open a
prefilled form, review/edit it and confirm before a pending CRM task is created.
The task links back to one source run, and duplicate approval is prevented.

**Reason:** This demonstrates a controlled agent-to-tool boundary. The assistant
does not contact customers, send email or start technical work autonomously.

**Rejected:** Automatic email and automatic task creation. Both remove useful
human judgment and automatic email is explicitly unnecessary.

## 10. Validate and import the complete archive transactionally

**Decision:** Validate manifest metadata, headers, checksums, row counts, source
formats and references before transactional business writes. Identify completed
imports by dataset version plus checksums.

**Reason:** A replacement archive either imports completely or fails visibly;
later application starts do not duplicate data and retain user changes.

**Rejected:** Editing CSVs, generating replacement records, using a hard-coded
sample, or relying only on row-level best-effort import.

## 11. Use indexed, bounded server-rendered reads

**Decision:** Use PostgreSQL trigram expression indexes for searchable text,
unique code indexes for prefix lookup, strict query/result bounds and server-side
pagination.

**Reason:** This keeps common searches practical toward 100,000 contacts without
introducing a separate search service or client-side state that the MVP does not
need.
