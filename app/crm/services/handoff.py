from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from crm.models import HandoffRun, Opportunity


ASSISTANT_LABEL = "Deterministic local stand-in"
POLICY_ID = "checked-technical-handoff-v1"

FIELD_LABELS = {
    "fair_edition": "Fair edition",
    "client_budget_eur": "Client budget",
    "stand_area_sqm": "Allocated stand area",
    "requested_height_m": "Requested height",
    "primary_contact": "Primary contact",
    "brief_notes": "Brief notes",
}


def _evidence(source: str, field: str, value) -> dict:
    return {"source": source, "field": field, "value": value}


def _decimal_value(value: Decimal | None) -> str | None:
    return f"{value:.2f}" if value is not None else None


def _date_value(value) -> str | None:
    return value.isoformat() if value is not None else None


def build_snapshot(opportunity: Opportunity) -> dict:
    contact = opportunity.primary_contact
    fair = opportunity.fair_edition
    return {
        "assistant": {
            "label": ASSISTANT_LABEL,
            "implementation": "ordinary deterministic Python functions",
            "external_model_calls": False,
            "version": "1.0",
        },
        "policy": {
            "id": POLICY_ID,
            "decision_rule": (
                "Continue only when fair, client budget, allocated area and "
                "requested height are known and the requested height is within "
                "the fair maximum."
            ),
            "commercial_gate": ["fair_edition", "client_budget_eur"],
            "technical_gate": ["stand_area_sqm", "requested_height_m"],
        },
        "company": {
            "code": opportunity.company.company_code,
            "name": opportunity.company.name,
            "province_code": opportunity.company.province_code,
            "region": opportunity.company.region,
            "sales_rep": opportunity.company.sales_rep,
        },
        "primary_contact": (
            {
                "code": contact.contact_code,
                "name": contact.full_name,
                "email": contact.email,
                "phone": contact.phone,
            }
            if contact is not None
            else None
        ),
        "opportunity": {
            "code": opportunity.opportunity_code,
            "description": opportunity.description,
            "sales_status": opportunity.sales_status,
            "opened_on": _date_value(opportunity.opened_on),
            "expected_close_on": _date_value(opportunity.expected_close_on),
            "amount_eur": _decimal_value(opportunity.amount_eur),
            "client_budget_eur": _decimal_value(opportunity.client_budget_eur),
            "stand_area_sqm": _decimal_value(opportunity.stand_area_sqm),
            "requested_height_m": _decimal_value(opportunity.requested_height_m),
            "brief_notes": opportunity.brief_notes,
        },
        "fair_edition": {
            "code": fair.fair_edition_code,
            "name": fair.fair_name,
            "city": fair.city,
            "venue": fair.venue,
            "starts_on": _date_value(fair.starts_on),
            "ends_on": _date_value(fair.ends_on),
            "max_stand_height_m": _decimal_value(fair.max_stand_height_m),
        },
    }


def prepare_brief(snapshot: dict) -> dict:
    opportunity = snapshot["opportunity"]
    fair = snapshot["fair_edition"]
    contact = snapshot["primary_contact"]
    field_values = {
        "fair_edition": fair,
        "client_budget_eur": opportunity["client_budget_eur"],
        "stand_area_sqm": opportunity["stand_area_sqm"],
        "requested_height_m": opportunity["requested_height_m"],
        "primary_contact": contact,
        "brief_notes": opportunity["brief_notes"],
    }
    known_fields = [
        {"field": field, "label": FIELD_LABELS[field]}
        for field, value in field_values.items()
        if value not in (None, "")
    ]
    missing_fields = [
        {"field": field, "label": FIELD_LABELS[field]}
        for field, value in field_values.items()
        if value in (None, "")
    ]

    commercial_missing = [
        field
        for field in ("fair_edition", "client_budget_eur")
        if field_values[field] in (None, "")
    ]
    if commercial_missing:
        proposal_code = "COLLECT_COMMERCIAL_INFORMATION"
        proposal = "Collect the missing commercial information before involving Technical."
        missing_labels = [FIELD_LABELS[field].lower() for field in commercial_missing]
        next_action = f"Confirm the missing {', '.join(missing_labels)} with the client."
    else:
        proposal_code = "EARLY_TECHNICAL_REVIEW"
        proposal = (
            "Fair and client budget are known; prepare the enquiry for an early "
            "technical review, subject to the independent safety check."
        )
        next_action = "Ask the Checker to verify technical completeness and constraints."

    return {
        "role": "Preparer",
        "responsibility": "Commercial completeness and brief preparation",
        "summary": (
            f"Prepared a brief for {snapshot['company']['name']} and "
            f"{fair['name']} ({fair['code']})."
        ),
        "brief": {
            "company": snapshot["company"]["name"],
            "contact": contact["name"] if contact else None,
            "opportunity": opportunity["code"],
            "description": opportunity["description"],
            "fair_edition": fair["code"],
            "client_budget_eur": opportunity["client_budget_eur"],
            "stand_area_sqm": opportunity["stand_area_sqm"],
            "requested_height_m": opportunity["requested_height_m"],
            "brief_notes": opportunity["brief_notes"],
        },
        "known_fields": known_fields,
        "missing_fields": missing_fields,
        "commercial_missing_fields": commercial_missing,
        "proposal_code": proposal_code,
        "proposal": proposal,
        "next_action": next_action,
    }


def check_brief(snapshot: dict, preparer_output: dict) -> dict:
    opportunity = snapshot["opportunity"]
    fair = snapshot["fair_edition"]
    area = opportunity["stand_area_sqm"]
    requested_height = opportunity["requested_height_m"]
    maximum_height = fair["max_stand_height_m"]
    opportunity_source = f"Opportunity {opportunity['code']}"
    fair_source = f"Fair edition {fair['code']}"
    checks = []
    blocking_issues = []

    area_evidence = [_evidence(opportunity_source, "stand_area_sqm", area)]
    if area is None:
        checks.append(
            {
                "code": "STAND_AREA_PRESENT",
                "label": "Allocated stand area",
                "status": "FAIL",
                "detail": "The allocated stand area is missing.",
                "evidence": area_evidence,
            }
        )
        blocking_issues.append(
            {
                "code": "MISSING_STAND_AREA",
                "field": "stand_area_sqm",
                "message": "Allocated stand area is required before technical work begins.",
                "evidence": area_evidence,
            }
        )
    else:
        checks.append(
            {
                "code": "STAND_AREA_PRESENT",
                "label": "Allocated stand area",
                "status": "PASS",
                "detail": f"Allocated area: {area} square metres.",
                "evidence": area_evidence,
            }
        )

    height_evidence = [
        _evidence(opportunity_source, "requested_height_m", requested_height)
    ]
    if requested_height is None:
        checks.append(
            {
                "code": "REQUESTED_HEIGHT_PRESENT",
                "label": "Requested height",
                "status": "FAIL",
                "detail": "The requested height is missing.",
                "evidence": height_evidence,
            }
        )
        blocking_issues.append(
            {
                "code": "MISSING_REQUESTED_HEIGHT",
                "field": "requested_height_m",
                "message": "Requested height is required before technical work begins.",
                "evidence": height_evidence,
            }
        )
    else:
        checks.append(
            {
                "code": "REQUESTED_HEIGHT_PRESENT",
                "label": "Requested height",
                "status": "PASS",
                "detail": f"Requested height: {requested_height} m.",
                "evidence": height_evidence,
            }
        )

    fair_evidence = [_evidence(fair_source, "max_stand_height_m", maximum_height)]
    if maximum_height is None:
        checks.append(
            {
                "code": "FAIR_HEIGHT_AVAILABLE",
                "label": "Fair maximum height",
                "status": "FAIL",
                "detail": "The fair maximum height is unavailable.",
                "evidence": fair_evidence,
            }
        )
        blocking_issues.append(
            {
                "code": "MISSING_FAIR_HEIGHT_LIMIT",
                "field": "max_stand_height_m",
                "message": "The requested height cannot be checked without a fair limit.",
                "evidence": fair_evidence,
            }
        )
    else:
        checks.append(
            {
                "code": "FAIR_HEIGHT_AVAILABLE",
                "label": "Fair maximum height",
                "status": "PASS",
                "detail": f"Fair maximum height: {maximum_height} m.",
                "evidence": fair_evidence,
            }
        )
        if requested_height is not None:
            within_limit = Decimal(requested_height) <= Decimal(maximum_height)
            comparison_evidence = [*height_evidence, *fair_evidence]
            checks.append(
                {
                    "code": "HEIGHT_WITHIN_FAIR_LIMIT",
                    "label": "Height constraint",
                    "status": "PASS" if within_limit else "FAIL",
                    "detail": (
                        f"Requested {requested_height} m; fair maximum {maximum_height} m."
                    ),
                    "evidence": comparison_evidence,
                }
            )
            if not within_limit:
                blocking_issues.append(
                    {
                        "code": "HEIGHT_EXCEEDS_FAIR_LIMIT",
                        "field": "requested_height_m",
                        "message": (
                            f"Requested height {requested_height} m exceeds the fair "
                            f"maximum of {maximum_height} m."
                        ),
                        "evidence": comparison_evidence,
                    }
                )

    proposal_is_collection = (
        preparer_output["proposal_code"] == "COLLECT_COMMERCIAL_INFORMATION"
    )
    proposal_safe = proposal_is_collection or not blocking_issues
    if proposal_safe and not blocking_issues:
        summary = "All technical checks passed; the proposed handoff is safe."
    elif proposal_safe:
        summary = (
            "Collecting commercial information is safe, but the technical handoff "
            "is not ready."
        )
    else:
        summary = "The proposed early technical review is unsafe until the issues are resolved."

    return {
        "role": "Checker",
        "responsibility": "Technical completeness and constraint safety",
        "summary": summary,
        "checks": checks,
        "blocking_issues": blocking_issues,
        "proposal_checked": preparer_output["proposal_code"],
        "proposal_safe": proposal_safe,
    }


def coordinate(snapshot: dict, preparer_output: dict, checker_output: dict) -> dict:
    fair = snapshot["fair_edition"]
    commercial_issues = []
    if "fair_edition" in preparer_output["commercial_missing_fields"]:
        commercial_issues.append(
            {
                "code": "MISSING_FAIR_EDITION",
                "message": "Fair edition is required for a technical handoff.",
            }
        )
    if "client_budget_eur" in preparer_output["commercial_missing_fields"]:
        commercial_issues.append(
            {
                "code": "MISSING_CLIENT_BUDGET",
                "message": "Client budget is required for a technical handoff.",
            }
        )
    issues = [*commercial_issues, *checker_output["blocking_issues"]]

    if not issues:
        return {
            "decision": HandoffRun.Decision.CONTINUE,
            "reason_codes": ["READY_FOR_TECHNICAL_HANDOFF"],
            "reason": (
                "Commercial and technical information is complete, and the requested "
                "height is within the fair limit."
            ),
            "next_action": "Send the checked brief to Technical for design review.",
        }

    reason_codes = [issue["code"] for issue in issues]
    missing_commercial = {
        "MISSING_FAIR_EDITION",
        "MISSING_CLIENT_BUDGET",
    }.intersection(reason_codes)
    missing_technical = {
        "MISSING_STAND_AREA",
        "MISSING_REQUESTED_HEIGHT",
        "MISSING_FAIR_HEIGHT_LIMIT",
    }.intersection(reason_codes)
    actions = []
    client_name = (
        snapshot["primary_contact"]["name"]
        if snapshot["primary_contact"] and snapshot["primary_contact"]["name"]
        else "the client"
    )
    if missing_commercial:
        fields = []
        if "MISSING_FAIR_EDITION" in reason_codes:
            fields.append("fair edition")
        if "MISSING_CLIENT_BUDGET" in reason_codes:
            fields.append("client budget")
        actions.append(f"confirm the missing {', '.join(fields)}")
    if missing_technical:
        fields = []
        if "MISSING_STAND_AREA" in reason_codes:
            fields.append("allocated area")
        if "MISSING_REQUESTED_HEIGHT" in reason_codes:
            fields.append("requested height")
        if "MISSING_FAIR_HEIGHT_LIMIT" in reason_codes:
            fields.append("fair height limit")
        actions.append(f"provide the missing {', '.join(fields)}")
    if "HEIGHT_EXCEEDS_FAIR_LIMIT" in reason_codes:
        actions.append(f"revise the height to {fair['max_stand_height_m']} m or below")

    return {
        "decision": HandoffRun.Decision.STOP,
        "reason_codes": reason_codes,
        "reason": " ".join(issue["message"] for issue in issues),
        "next_action": f"Ask {client_name} to {'; then '.join(actions)}.",
    }


@transaction.atomic
def run_handoff(opportunity: Opportunity) -> HandoffRun:
    current_opportunity = Opportunity.objects.select_related(
        "company", "primary_contact", "fair_edition"
    ).get(pk=opportunity.pk)
    snapshot = build_snapshot(current_opportunity)
    preparer_output = prepare_brief(snapshot)
    checker_output = check_brief(snapshot, preparer_output)
    coordinator_output = coordinate(snapshot, preparer_output, checker_output)
    return HandoffRun.objects.create(
        opportunity=current_opportunity,
        input_snapshot=snapshot,
        preparer_output=preparer_output,
        checker_output=checker_output,
        coordinator_decision=coordinator_output["decision"],
        reason_codes=coordinator_output["reason_codes"],
        decision_reason=coordinator_output["reason"],
        next_action=coordinator_output["next_action"],
    )
