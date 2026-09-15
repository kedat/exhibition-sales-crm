from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import Activity, Company, Contact, FairEdition, Opportunity


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
    }
)
class CrmReadWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            company_code="CO-DEMO",
            name="Oruma Ceramics Cooperative",
            region="Lombardy",
            province_code="MI",
            sales_rep="Casey Martin",
        )
        cls.other_company = Company.objects.create(
            company_code="CO-OTHER",
            name="Another Exhibitor",
        )
        cls.contact = Contact.objects.create(
            legacy_row_id="ROW-DEMO",
            contact_code="CO-DEMO-P01",
            company=cls.company,
            first_name="Andrea",
            last_name="Greco",
            email="andrea.greco@example.test",
        )
        cls.fair_2026 = FairEdition.objects.create(
            fair_edition_code="FOOD-2026",
            fair_name="Food Service Expo",
            city="Milan",
            venue="North Exhibition Centre",
            starts_on=date(2026, 10, 10),
            ends_on=date(2026, 10, 13),
            max_stand_height_m=Decimal("4.50"),
        )
        cls.fair_2027 = FairEdition.objects.create(
            fair_edition_code="FOOD-2027",
            fair_name="Food Service Expo",
            city="Milan",
            venue="North Exhibition Centre",
            starts_on=date(2027, 10, 10),
            ends_on=date(2027, 10, 13),
            max_stand_height_m=Decimal("4.50"),
        )
        cls.opportunity = Opportunity.objects.create(
            opportunity_code="OP-DEMO",
            company=cls.company,
            primary_contact=cls.contact,
            fair_edition=cls.fair_2026,
            description="Demo stand",
            amount_eur=Decimal("25000.00"),
            client_budget_eur=Decimal("30000.00"),
            sales_status=Opportunity.SalesStatus.QUALIFIED,
            opened_on=date(2026, 8, 1),
            expected_close_on=date(2026, 9, 30),
            requested_height_m=Decimal("3.50"),
            brief_notes="Waiting for the allocated area.",
        )
        cls.other_opportunity = Opportunity.objects.create(
            opportunity_code="OP-NEXT",
            company=cls.company,
            primary_contact=cls.contact,
            fair_edition=cls.fair_2027,
            description="Next edition stand",
            sales_status=Opportunity.SalesStatus.OPEN,
            opened_on=date(2026, 9, 1),
        )

        today = timezone.localdate()
        occurred_at = timezone.make_aware(datetime.combine(today, time(9, 0)))
        cls.company_activity = Activity.objects.create(
            legacy_entry_id="AC-COMPANY",
            company=cls.company,
            activity_type=Activity.ActivityType.EMAIL,
            occurred_at=occurred_at,
            details="Company-level follow-up details",
            follow_up_on=today,
            completion_marker=Activity.CompletionMarker.COMPLETED,
        )
        cls.opportunity_activity = Activity.objects.create(
            legacy_entry_id="AC-DEMO",
            company=cls.company,
            opportunity=cls.opportunity,
            activity_type=Activity.ActivityType.CALL,
            occurred_at=occurred_at,
            details="Only the demo opportunity should show this call",
            follow_up_on=today - timedelta(days=1),
            completion_marker=Activity.CompletionMarker.COMPLETED,
        )
        Activity.objects.create(
            legacy_entry_id="AC-NEXT",
            company=cls.company,
            opportunity=cls.other_opportunity,
            activity_type=Activity.ActivityType.MEETING,
            occurred_at=occurred_at,
            details="Only the next opportunity should show this meeting",
            follow_up_on=today + timedelta(days=1),
            completion_marker=Activity.CompletionMarker.COMPLETED,
        )
        Activity.objects.create(
            legacy_entry_id="AC-NOTE",
            company=cls.company,
            activity_type=Activity.ActivityType.NOTE,
            occurred_at=occurred_at,
            details="Internal note follow-up",
            follow_up_on=today,
        )
        Activity.objects.create(
            legacy_entry_id="AC-TASK",
            company=cls.company,
            opportunity=cls.opportunity,
            activity_type=Activity.ActivityType.TASK,
            occurred_at=occurred_at,
            details="Pending task follow-up",
            follow_up_on=today,
            completion_marker=Activity.CompletionMarker.PENDING,
        )

    def test_dashboard_groups_every_activity_type_and_company_level_follow_up(self):
        response = self.client.get(reverse("crm:home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overdue_count"], 1)
        self.assertEqual(response.context["due_today_count"], 3)
        self.assertEqual(response.context["upcoming_count"], 1)
        all_visible = [
            *response.context["overdue"],
            *response.context["due_today"],
            *response.context["upcoming"],
        ]
        self.assertEqual(
            {activity.activity_type for activity in all_visible},
            {"call", "email", "meeting", "note", "task"},
        )
        self.assertContains(response, "Company-level follow-up")

    def test_searches_company_and_contact_fields(self):
        queries = [
            "Oruma Ceramics",
            "CO-DEMO",
            "Andrea Greco",
            "CO-DEMO-P01",
            "andrea.greco@example.test",
        ]

        for query in queries:
            with self.subTest(query=query):
                response = self.client.get(reverse("crm:search"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Oruma Ceramics Cooperative")
                self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_search_results_are_paginated_and_bounded(self):
        Company.objects.bulk_create(
            [
                Company(company_code=f"CO-EXPO-{number:02}", name=f"Expo Company {number}")
                for number in range(21)
            ]
        )

        response = self.client.get(reverse("crm:search"), {"q": "Expo"})

        page = response.context["page_obj"]
        self.assertEqual(len(page.object_list), 20)
        self.assertTrue(page.has_next())
        self.assertEqual(page.paginator.count, 21)

    def test_company_detail_distinguishes_editions_and_company_activity(self):
        response = self.client.get(
            reverse("crm:company-detail", args=[self.company.company_code])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FOOD-2026")
        self.assertContains(response, "FOOD-2027")
        self.assertContains(response, "Company-level follow-up details")
        self.assertNotContains(response, "Only the demo opportunity should show this call")

    def test_opportunity_timeline_is_scoped_to_selected_opportunity(self):
        response = self.client.get(
            reverse("crm:opportunity-detail", args=[self.opportunity.opportunity_code])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only the demo opportunity should show this call")
        self.assertContains(response, "Pending task follow-up")
        self.assertNotContains(response, "Company-level follow-up details")
        self.assertNotContains(response, "Only the next opportunity should show this meeting")
        self.assertContains(response, "FOOD-2026")
        self.assertContains(response, "4.50 m")
