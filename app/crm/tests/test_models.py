from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from crm.models import Activity, Company, Contact, FairEdition, HandoffRun, Opportunity


class CrmModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            company_code="CO-PRIMARY",
            name="Primary Exhibitor",
        )
        cls.other_company = Company.objects.create(
            company_code="CO-OTHER",
            name="Other Exhibitor",
        )
        cls.contact = Contact.objects.create(
            legacy_row_id="ROW-PRIMARY",
            contact_code="CONTACT-PRIMARY",
            company=cls.company,
            first_name="Andrea",
            last_name="Greco",
        )
        cls.other_contact = Contact.objects.create(
            legacy_row_id="ROW-OTHER",
            contact_code="CONTACT-OTHER",
            company=cls.other_company,
            first_name="Sam",
            last_name="Rossi",
        )
        cls.fair = FairEdition.objects.create(
            fair_edition_code="FAIR-2026",
            fair_name="Example Fair",
            city="Milan",
            venue="Example Hall",
            starts_on=date(2026, 10, 20),
            ends_on=date(2026, 10, 23),
            max_stand_height_m=Decimal("5.00"),
        )

    def make_opportunity(self, **overrides):
        values = {
            "opportunity_code": "OP-VALID",
            "company": self.company,
            "primary_contact": self.contact,
            "fair_edition": self.fair,
            "description": "Example stand",
            "amount_eur": Decimal("10000.00"),
            "client_budget_eur": Decimal("12000.00"),
            "sales_status": Opportunity.SalesStatus.OPEN,
            "opened_on": date(2026, 9, 1),
            "stand_area_sqm": Decimal("40.00"),
            "requested_height_m": Decimal("4.00"),
        }
        values.update(overrides)
        return Opportunity(**values)

    def test_optional_opportunity_contact_and_activity_opportunity_are_supported(self):
        opportunity = self.make_opportunity(
            opportunity_code="OP-NO-CONTACT",
            primary_contact=None,
        )
        opportunity.full_clean()
        opportunity.save()

        activity = Activity.objects.create(
            company=self.company,
            opportunity=None,
            activity_type=Activity.ActivityType.NOTE,
            occurred_at=timezone.now(),
            details="Company-level note",
        )

        self.assertIsNone(opportunity.primary_contact)
        self.assertIsNone(activity.opportunity)

    def test_primary_contact_must_belong_to_opportunity_company(self):
        opportunity = self.make_opportunity(primary_contact=self.other_contact)

        with self.assertRaisesMessage(
            ValidationError,
            "Primary contact must belong to the company.",
        ):
            opportunity.full_clean()

    def test_activity_opportunity_must_belong_to_activity_company(self):
        opportunity = self.make_opportunity()
        opportunity.save()
        activity = Activity(
            company=self.other_company,
            opportunity=opportunity,
            activity_type=Activity.ActivityType.CALL,
            occurred_at=timezone.now(),
            details="Mismatched company",
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Opportunity must belong to the company.",
        ):
            activity.full_clean()

    def test_height_above_fair_limit_is_preserved_for_handoff_checking(self):
        opportunity = self.make_opportunity(
            requested_height_m=Decimal("6.00"),
        )

        opportunity.full_clean()
        opportunity.save()

        self.assertEqual(opportunity.requested_height_m, Decimal("6.00"))
        self.assertEqual(opportunity.fair_edition.max_stand_height_m, Decimal("5.00"))

    def test_database_rejects_nonpositive_stand_area(self):
        opportunity = self.make_opportunity(stand_area_sqm=Decimal("0.00"))

        with self.assertRaises(IntegrityError), transaction.atomic():
            opportunity.save()

    def test_handoff_run_keeps_structured_role_outputs(self):
        opportunity = self.make_opportunity()
        opportunity.save()
        run = HandoffRun.objects.create(
            opportunity=opportunity,
            input_snapshot={"stand_area_sqm": "40.00"},
            preparer_output={"proposal": "technical_review"},
            checker_output={"verdict": "pass", "issues": []},
            coordinator_decision=HandoffRun.Decision.CONTINUE,
            decision_reason="All required information is present.",
            next_action="Send the brief to Technical.",
        )

        run.refresh_from_db()

        self.assertEqual(run.input_snapshot["stand_area_sqm"], "40.00")
        self.assertEqual(run.checker_output["verdict"], "pass")
