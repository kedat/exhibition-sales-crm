from __future__ import annotations

from crm.models import HandoffRun


COMPARISON_FIELDS = (
    ("primary_contact.name", "Primary contact"),
    ("opportunity.client_budget_eur", "Client budget"),
    ("opportunity.stand_area_sqm", "Allocated stand area"),
    ("opportunity.requested_height_m", "Requested height"),
    ("opportunity.brief_notes", "Brief notes"),
    ("fair_edition.code", "Fair edition"),
    ("fair_edition.max_stand_height_m", "Fair maximum height"),
)


def _snapshot_value(snapshot: dict, path: str):
    value = snapshot
    for part in path.split("."):
        if value is None:
            return None
        value = value.get(part)
    return value


def _display_value(value) -> str:
    if value in (None, ""):
        return "Missing"
    return str(value)


def previous_handoff_run(handoff_run: HandoffRun) -> HandoffRun | None:
    return (
        HandoffRun.objects.filter(
            opportunity_id=handoff_run.opportunity_id,
            pk__lt=handoff_run.pk,
        )
        .order_by("-pk")
        .first()
    )


def compare_handoff_runs(
    current: HandoffRun,
    previous: HandoffRun | None = None,
) -> dict | None:
    previous = previous or previous_handoff_run(current)
    if previous is None:
        return None

    changes = []
    for path, label in COMPARISON_FIELDS:
        before = _snapshot_value(previous.input_snapshot, path)
        after = _snapshot_value(current.input_snapshot, path)
        if before != after:
            changes.append(
                {
                    "field": path,
                    "label": label,
                    "before": _display_value(before),
                    "after": _display_value(after),
                }
            )

    previous_reasons = set(previous.reason_codes)
    current_reasons = set(current.reason_codes)
    return {
        "previous_run": previous,
        "changes": changes,
        "decision_changed": (
            previous.coordinator_decision != current.coordinator_decision
        ),
        "resolved_reason_codes": sorted(previous_reasons - current_reasons),
        "new_reason_codes": sorted(current_reasons - previous_reasons),
    }
