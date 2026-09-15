# Demo guide

This is a 5–7 minute path for presenting the product in English. It demonstrates
the business workflow first and uses implementation details only as evidence.

## Before the interview

From a clean state:

```bash
./reset.sh
./dev.sh
```

Keep `./dev.sh` running. In another terminal:

```bash
./verify.sh
```

Open these tabs:

- [Incomplete enquiry — OP011026](http://localhost:3000/opportunities/OP011026/)
- [Height conflict — OP000005](http://localhost:3000/opportunities/OP000005/)
- [Complete enquiry — OP000230](http://localhost:3000/opportunities/OP000230/)
- [Progress evidence](../PROGRESS.md)

Do not rehearse by editing these records after the final reset unless you reset
again before the real presentation.

## 0:00–0:40 — Frame the problem

Suggested talk track:

> I focused on the point where commercial speed and technical safety conflict.
> The CRM keeps each fair edition separate, makes promised follow-ups actionable,
> and adds a controlled decision workflow rather than a generic AI chat box.

Briefly show search and the opportunity's company, contact, fair edition and
timeline. Avoid touring every screen.

## 0:40–2:10 — Incomplete enquiry and role separation

Open `OP011026` and point out:

- client budget `€37,800.00` is known;
- requested height `3.50 m` is within the fair's `4.50 m` maximum;
- allocated area is unknown;
- the primary contact is Andrea Greco.

Select **Prepare technical handoff**.

Suggested talk track:

> The Preparer represents the commercial need for early involvement. It can
> propose a review because fair and budget are known. The Checker has a different
> contract: it finds the missing area and grounds that finding in the stored
> opportunity field. The Coordinator applies the policy and stops technical work.

Show `MISSING_STAND_AREA`, the next action and the source evidence. Mention that
the snapshot and every role output have been saved.

## 2:10–3:00 — Human-approved action

Select **Review and create follow-up**.

Show that the assistant recommendation and a proposed date are prefilled. Change
the wording if useful, then select **Approve and schedule**.

Suggested talk track:

> The assistant can propose a tool action, but page load has no side effect. The
> salesperson reviews it first. The resulting task links back to this exact run,
> and one run cannot create duplicate approved tasks.

Point to the approved state and linked activity in the opportunity timeline.

## 3:00–4:20 — Correct, rerun and compare

Edit the opportunity, set allocated area to `24.00` m² and save. Run the handoff
again.

Show:

- `STOP → CONTINUE`;
- `Allocated stand area: Missing → 24.00`;
- resolved `MISSING_STAND_AREA`;
- new `READY_FOR_TECHNICAL_HANDOFF`.

Open the earlier run from history and show that its snapshot still says the area
was unknown.

Suggested talk track:

> This is the feedback loop: observe, reason, stop, let a human correct the source
> state, and reevaluate. Historical reasoning does not change when live CRM data
> changes.

## 4:20–5:20 — Adversarial conflict

Open `OP000005` and run the assistant. Show requested height `6.00 m` and fair
maximum `5.00 m`.

Suggested talk track:

> This is the case that proves the roles are not decorative. The Preparer still
> proposes early review because commercial data is complete. The independent
> Checker rejects that proposal, cites both source values, and the Coordinator
> returns STOP with a concrete remediation.

If time is short, this is the best fallback scenario after `OP011026`.

## 5:20–6:10 — Engineering evidence

Show `PROGRESS.md` or the test command rather than reading code line by line.

```bash
docker compose run --rm --entrypoint /app/.venv/bin/python app \
  manage.py test crm.tests.test_handoff.HandoffAgentEvaluationTests
```

Mention:

- deterministic outputs for equal snapshots;
- boundary and simultaneous-blocker cases;
- immutable reruns and evidence checks;
- full clean import and restart/idempotency verification;
- no model, API or external runtime dependency.

## 6:10–6:40 — Close

Suggested close:

> AI makes producing features inexpensive, so I optimized for decision quality,
> traceability and safe human control. The result is deliberately small, but the
> critical handoff decision is reproducible, auditable and connected to the sales
> workflow.

## Likely questions

### Why call this agentic if there is no language model?

The assignment requires a deterministic local stand-in. The agentic properties
are observable role contracts, proposal and critique, policy-based coordination,
state snapshots, persisted traces, human-approved action and rerun feedback. A
language model is neither required for those properties nor permitted here.

### Why not pass the enquiry as soon as fair and budget are known?

That is allowed at the Preparer proposal stage, satisfying Sales' request for
speed. The final gate also requires area and safe height because starting
undeliverable technical work is the failure the technical coordinator reported.

### Why use JSON for role outputs?

Core CRM entities remain relational and constrained. Role outputs and value
snapshots are versioned documents whose schema may evolve and whose historical
contents must remain intact. Stable final decision and reason fields are also
stored directly for querying.

### What would you build next?

Marking follow-ups complete is the nearest workflow improvement. For the
assistant, policy simulation or a visual evaluation report could be useful after
real stakeholder feedback, but neither should displace core sales tasks.

### How did AI help build this?

AI accelerated domain exploration, alternative generation, implementation and
adversarial review. Product scope, policy, acceptance/rejection of proposals and
verification remained human responsibilities. Tests and reproducible runtime
behavior—not generated confidence—are the acceptance boundary.
