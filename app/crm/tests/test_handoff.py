from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import Activity, Company, Contact, FairEdition, HandoffRun, Opportunity
from crm.services.handoff import ASSISTANT_LABEL, POLICY_ID, run_handoff
from crm.services.handoff_comparison import compare_handoff_runs


class HandoffFixturesMixin:
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            company_code="CO-HANDOFF",
            name="Handoff Exhibitor",
            sales_rep="Casey Martin",
        )
        cls.contact = Contact.objects.create(
            legacy_row_id="ROW-HANDOFF",
            contact_code="CONTACT-HANDOFF",
            company=cls.company,
            first_name="Andrea",
            last_name="Greco",
            email="andrea@example.test",
        )
        cls.fair = FairEdition.objects.create(
            fair_edition_code="HANDOFF-2027",
            fair_name="Handoff Fair",
            city="Milan",
            venue="Test Venue",
            starts_on=date(2027, 4, 10),
            ends_on=date(2027, 4, 12),
            max_stand_height_m=Decimal("5.00"),
        )

    def make_opportunity(self, code, **overrides):
        values = {
            "opportunity_code": code,
            "company": self.company,
            "primary_contact": self.contact,
            "fair_edition": self.fair,
            "description": "Exhibition stand",
            "amount_eur": Decimal("18000.00"),
            "client_budget_eur": Decimal("20000.00"),
            "sales_status": Opportunity.SalesStatus.QUALIFIED,
            "opened_on": date(2026, 9, 1),
            "stand_area_sqm": Decimal("40.00"),
            "requested_height_m": Decimal("4.00"),
            "brief_notes": "Reception and meeting area.",
        }
        values.update(overrides)
        return Opportunity.objects.create(**values)


class HandoffAgentEvaluationTests(HandoffFixturesMixin, TestCase):
    """Behavioral evaluations for role contracts and coordinator policy."""

    def test_five_primary_handoff_outcomes(self):
        cases = [
            {
                "code": "OP-MISSING-BUDGET",
                "overrides": {"client_budget_eur": None},
                "decision": "STOP",
                "reason_code": "MISSING_CLIENT_BUDGET",
                "proposal": "COLLECT_COMMERCIAL_INFORMATION",
                "proposal_safe": True,
            },
            {
                "code": "OP-MISSING-AREA",
                "overrides": {"stand_area_sqm": None},
                "decision": "STOP",
                "reason_code": "MISSING_STAND_AREA",
                "proposal": "EARLY_TECHNICAL_REVIEW",
                "proposal_safe": False,
            },
            {
                "code": "OP-MISSING-HEIGHT",
                "overrides": {"requested_height_m": None},
                "decision": "STOP",
                "reason_code": "MISSING_REQUESTED_HEIGHT",
                "proposal": "EARLY_TECHNICAL_REVIEW",
                "proposal_safe": False,
            },
            {
                "code": "OP-HEIGHT-CONFLICT",
                "overrides": {"requested_height_m": Decimal("6.00")},
                "decision": "STOP",
                "reason_code": "HEIGHT_EXCEEDS_FAIR_LIMIT",
                "proposal": "EARLY_TECHNICAL_REVIEW",
                "proposal_safe": False,
            },
            {
                "code": "OP-COMPLETE",
                "overrides": {},
                "decision": "CONTINUE",
                "reason_code": "READY_FOR_TECHNICAL_HANDOFF",
                "proposal": "EARLY_TECHNICAL_REVIEW",
                "proposal_safe": True,
            },
        ]

        for case in cases:
            with self.subTest(case=case["code"]):
                opportunity = self.make_opportunity(
                    case["code"], **case["overrides"]
                )
                handoff_run = run_handoff(opportunity)

                self.assertEqual(handoff_run.coordinator_decision, case["decision"])
                self.assertIn(case["reason_code"], handoff_run.reason_codes)
                self.assertEqual(
                    handoff_run.preparer_output["proposal_code"], case["proposal"]
                )
                self.assertEqual(
                    handoff_run.checker_output["proposal_safe"],
                    case["proposal_safe"],
                )
                self.assertEqual(handoff_run.preparer_output["role"], "Preparer")
                self.assertEqual(handoff_run.checker_output["role"], "Checker")

        self.assertEqual(HandoffRun.objects.count(), 5)

    def test_snapshot_contains_values_and_identifies_local_stand_in(self):
        opportunity = self.make_opportunity("OP-SNAPSHOT")

        handoff_run = run_handoff(opportunity)
        snapshot = handoff_run.input_snapshot

        self.assertEqual(snapshot["assistant"]["label"], ASSISTANT_LABEL)
        self.assertFalse(snapshot["assistant"]["external_model_calls"])
        self.assertEqual(snapshot["policy"]["id"], POLICY_ID)
        self.assertEqual(snapshot["company"]["name"], "Handoff Exhibitor")
        self.assertEqual(snapshot["primary_contact"]["name"], "Andrea Greco")
        self.assertEqual(snapshot["opportunity"]["client_budget_eur"], "20000.00")
        self.assertEqual(snapshot["fair_edition"]["max_stand_height_m"], "5.00")

    def test_edit_and_rerun_keeps_previous_snapshot_immutable(self):
        opportunity = self.make_opportunity(
            "OP-RERUN",
            stand_area_sqm=None,
        )
        first_run = run_handoff(opportunity)

        opportunity.stand_area_sqm = Decimal("45.00")
        opportunity.save(update_fields=["stand_area_sqm"])
        second_run = run_handoff(opportunity)
        first_run.refresh_from_db()

        self.assertNotEqual(first_run.pk, second_run.pk)
        self.assertEqual(first_run.coordinator_decision, HandoffRun.Decision.STOP)
        self.assertIsNone(first_run.input_snapshot["opportunity"]["stand_area_sqm"])
        self.assertEqual(second_run.coordinator_decision, HandoffRun.Decision.CONTINUE)
        self.assertEqual(
            second_run.input_snapshot["opportunity"]["stand_area_sqm"], "45.00"
        )

    def test_same_snapshot_is_deterministic(self):
        opportunity = self.make_opportunity("OP-DETERMINISTIC")

        first_run = run_handoff(opportunity)
        second_run = run_handoff(opportunity)

        self.assertEqual(first_run.input_snapshot, second_run.input_snapshot)
        self.assertEqual(first_run.preparer_output, second_run.preparer_output)
        self.assertEqual(first_run.checker_output, second_run.checker_output)
        self.assertEqual(
            first_run.coordinator_decision,
            second_run.coordinator_decision,
        )
        self.assertEqual(first_run.reason_codes, second_run.reason_codes)

    def test_checker_reports_multiple_issues_and_overrules_unsafe_proposal(self):
        opportunity = self.make_opportunity(
            "OP-ADVERSARIAL",
            stand_area_sqm=None,
            requested_height_m=Decimal("6.00"),
        )

        handoff_run = run_handoff(opportunity)

        self.assertEqual(
            handoff_run.preparer_output["proposal_code"],
            "EARLY_TECHNICAL_REVIEW",
        )
        self.assertFalse(handoff_run.checker_output["proposal_safe"])
        self.assertEqual(handoff_run.coordinator_decision, HandoffRun.Decision.STOP)
        self.assertEqual(
            handoff_run.reason_codes,
            ["MISSING_STAND_AREA", "HEIGHT_EXCEEDS_FAIR_LIMIT"],
        )

    def test_height_equal_to_fair_limit_passes(self):
        opportunity = self.make_opportunity(
            "OP-BOUNDARY",
            requested_height_m=Decimal("5.00"),
        )

        handoff_run = run_handoff(opportunity)

        self.assertEqual(
            handoff_run.coordinator_decision,
            HandoffRun.Decision.CONTINUE,
        )
        limit_check = next(
            check
            for check in handoff_run.checker_output["checks"]
            if check["code"] == "HEIGHT_WITHIN_FAIR_LIMIT"
        )
        self.assertEqual(limit_check["status"], "PASS")

    def test_checker_findings_retain_snapshot_evidence(self):
        opportunity = self.make_opportunity(
            "OP-EVIDENCE",
            requested_height_m=Decimal("6.00"),
        )

        handoff_run = run_handoff(opportunity)
        conflict = next(
            issue
            for issue in handoff_run.checker_output["blocking_issues"]
            if issue["code"] == "HEIGHT_EXCEEDS_FAIR_LIMIT"
        )

        self.assertEqual(
            conflict["evidence"],
            [
                {
                    "source": "Opportunity OP-EVIDENCE",
                    "field": "requested_height_m",
                    "value": "6.00",
                },
                {
                    "source": "Fair edition HANDOFF-2027",
                    "field": "max_stand_height_m",
                    "value": "5.00",
                },
            ],
        )

    def test_run_comparison_explains_changed_inputs_and_outcome(self):
        opportunity = self.make_opportunity("OP-COMPARE", stand_area_sqm=None)
        first_run = run_handoff(opportunity)
        opportunity.stand_area_sqm = Decimal("45.00")
        opportunity.save(update_fields=["stand_area_sqm"])
        second_run = run_handoff(opportunity)

        comparison = compare_handoff_runs(second_run)

        self.assertEqual(comparison["previous_run"], first_run)
        self.assertTrue(comparison["decision_changed"])
        self.assertEqual(
            comparison["changes"],
            [
                {
                    "field": "opportunity.stand_area_sqm",
                    "label": "Allocated stand area",
                    "before": "Missing",
                    "after": "45.00",
                }
            ],
        )
        self.assertEqual(
            comparison["resolved_reason_codes"],
            ["MISSING_STAND_AREA"],
        )
        self.assertEqual(
            comparison["new_reason_codes"],
            ["READY_FOR_TECHNICAL_HANDOFF"],
        )


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
    }
)
class HandoffUiTests(HandoffFixturesMixin, TestCase):
    def test_post_runs_assistant_and_displays_auditable_history(self):
        opportunity = self.make_opportunity("OP-UI", stand_area_sqm=None)
        run_url = reverse("crm:handoff-create", args=[opportunity.opportunity_code])

        response = self.client.post(run_url)

        self.assertRedirects(
            response,
            f"{opportunity.get_absolute_url()}?saved=handoff#technical-handoff",
        )
        handoff_run = opportunity.handoff_runs.get()
        detail = self.client.get(opportunity.get_absolute_url())
        self.assertContains(detail, ASSISTANT_LABEL)
        self.assertContains(detail, "No model or API")
        self.assertContains(detail, "STOP")
        self.assertContains(detail, "MISSING_STAND_AREA")
        self.assertContains(detail, "Preparer")
        self.assertContains(detail, "Checker")
        self.assertContains(detail, f"Run #{handoff_run.pk}")

        history = self.client.get(
            reverse(
                "crm:handoff-run-detail",
                args=[opportunity.opportunity_code, handoff_run.pk],
            )
        )
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Immutable snapshot")
        self.assertContains(history, POLICY_ID)
        self.assertContains(history, "Unknown")

    def test_run_endpoint_rejects_get(self):
        opportunity = self.make_opportunity("OP-POST-ONLY")

        response = self.client.get(
            reverse("crm:handoff-create", args=[opportunity.opportunity_code])
        )

        self.assertEqual(response.status_code, 405)

    def test_rerun_displays_input_and_decision_comparison(self):
        opportunity = self.make_opportunity("OP-UI-COMPARE", stand_area_sqm=None)
        first_run = run_handoff(opportunity)
        opportunity.stand_area_sqm = Decimal("45.00")
        opportunity.save(update_fields=["stand_area_sqm"])
        second_run = run_handoff(opportunity)

        response = self.client.get(
            reverse(
                "crm:handoff-run-detail",
                args=[opportunity.opportunity_code, second_run.pk],
            )
        )

        self.assertContains(response, f"Changes since run #{first_run.pk}")
        self.assertContains(response, "Allocated stand area")
        self.assertContains(response, "Missing")
        self.assertContains(response, "45.00")
        self.assertContains(response, "MISSING_STAND_AREA")

    def test_sales_reviews_and_approves_recommended_follow_up_once(self):
        opportunity = self.make_opportunity("OP-UI-ACTION", stand_area_sqm=None)
        handoff_run = run_handoff(opportunity)
        action_url = reverse(
            "crm:handoff-follow-up-create",
            args=[opportunity.opportunity_code, handoff_run.pk],
        )

        review = self.client.get(action_url)

        self.assertContains(review, "human approval")
        self.assertContains(review, "nothing is scheduled until you review")
        self.assertEqual(
            review.context["form"].initial["details"],
            handoff_run.next_action,
        )
        follow_up_on = timezone.localdate() + timedelta(days=2)

        approved = self.client.post(
            action_url,
            {
                "details": "Ask Andrea for the final allocated plot drawing.",
                "follow_up_on": follow_up_on.isoformat(),
            },
        )

        self.assertRedirects(
            approved,
            f"{opportunity.get_absolute_url()}?saved=assistant-follow-up"
            "#technical-handoff",
        )
        activity = Activity.objects.get(source_handoff_run=handoff_run)
        self.assertEqual(activity.opportunity, opportunity)
        self.assertEqual(activity.company, opportunity.company)
        self.assertEqual(activity.activity_type, Activity.ActivityType.TASK)
        self.assertEqual(
            activity.completion_marker,
            Activity.CompletionMarker.PENDING,
        )
        self.assertEqual(activity.follow_up_on, follow_up_on)

        duplicate = self.client.post(
            action_url,
            {
                "details": "Duplicate action",
                "follow_up_on": follow_up_on.isoformat(),
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already approved")
        self.assertEqual(
            Activity.objects.filter(source_handoff_run=handoff_run).count(),
            1,
        )

        detail = self.client.get(opportunity.get_absolute_url())
        self.assertContains(detail, "Approved by sales")
        self.assertContains(detail, f"Approved from handoff run #{handoff_run.pk}")
