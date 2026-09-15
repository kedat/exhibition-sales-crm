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

    def test_each_follow_up_bucket_can_be_paginated(self):
        follow_up_on = timezone.localdate() + timedelta(days=2)
        Activity.objects.bulk_create(
            [
                Activity(
                    company=self.company,
                    activity_type=Activity.ActivityType.TASK,
                    occurred_at=timezone.now(),
                    details=f"Additional upcoming task {number}",
                    follow_up_on=follow_up_on,
                    completion_marker=Activity.CompletionMarker.PENDING,
                )
                for number in range(9)
            ]
        )

        response = self.client.get(reverse("crm:home"), {"upcoming_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["upcoming"].number, 2)
        self.assertEqual(response.context["upcoming"].paginator.count, 10)
        self.assertEqual(len(response.context["upcoming"].object_list), 2)

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


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
    }
)
class OpportunityWriteWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            company_code="CO-WRITE",
            name="Write Workflow Exhibitor",
        )
        cls.other_company = Company.objects.create(
            company_code="CO-OUTSIDE",
            name="Outside Exhibitor",
        )
        cls.contact = Contact.objects.create(
            legacy_row_id="ROW-WRITE",
            contact_code="CONTACT-WRITE",
            company=cls.company,
            first_name="Andrea",
            last_name="Greco",
        )
        cls.outside_contact = Contact.objects.create(
            legacy_row_id="ROW-OUTSIDE",
            contact_code="CONTACT-OUTSIDE",
            company=cls.other_company,
            first_name="Other",
            last_name="Contact",
        )
        cls.fair = FairEdition.objects.create(
            fair_edition_code="WRITE-2027",
            fair_name="Write Fair",
            city="Milan",
            venue="Test Venue",
            starts_on=date(2027, 6, 1),
            ends_on=date(2027, 6, 3),
            max_stand_height_m=Decimal("5.00"),
        )
        cls.opportunity = Opportunity.objects.create(
            opportunity_code="OP-WRITE",
            company=cls.company,
            fair_edition=cls.fair,
            description="Write workflow stand",
            amount_eur=Decimal("15000.00"),
            sales_status=Opportunity.SalesStatus.OPEN,
            opened_on=date(2026, 9, 1),
        )

    def opportunity_payload(self, **overrides):
        payload = {
            "primary_contact": self.contact.pk,
            "sales_status": Opportunity.SalesStatus.PROPOSAL,
            "expected_close_on": "2026-10-01",
            "client_budget_eur": "20000.00",
            "stand_area_sqm": "60.00",
            "requested_height_m": "4.50",
            "brief_notes": "Reception, store and two meeting tables.",
        }
        payload.update(overrides)
        return payload

    def test_updates_all_editable_fields_and_persists_after_reload(self):
        response = self.client.post(
            reverse("crm:opportunity-edit", args=[self.opportunity.opportunity_code]),
            self.opportunity_payload(),
        )

        self.assertRedirects(
            response,
            f"{self.opportunity.get_absolute_url()}?saved=opportunity",
        )
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.primary_contact, self.contact)
        self.assertEqual(self.opportunity.sales_status, Opportunity.SalesStatus.PROPOSAL)
        self.assertEqual(self.opportunity.expected_close_on, date(2026, 10, 1))
        self.assertEqual(self.opportunity.client_budget_eur, Decimal("20000.00"))
        self.assertEqual(self.opportunity.stand_area_sqm, Decimal("60.00"))
        self.assertEqual(self.opportunity.requested_height_m, Decimal("4.50"))
        self.assertEqual(
            self.opportunity.brief_notes,
            "Reception, store and two meeting tables.",
        )

        detail_response = self.client.get(self.opportunity.get_absolute_url())
        self.assertContains(detail_response, "€20000.00")
        self.assertContains(detail_response, "60.00 m²")

    def test_requested_height_above_fair_limit_is_saved(self):
        response = self.client.post(
            reverse("crm:opportunity-edit", args=[self.opportunity.opportunity_code]),
            self.opportunity_payload(requested_height_m="6.00"),
        )

        self.assertEqual(response.status_code, 302)
        self.opportunity.refresh_from_db()
        self.assertEqual(self.opportunity.requested_height_m, Decimal("6.00"))
        self.assertEqual(self.opportunity.fair_edition.max_stand_height_m, Decimal("5.00"))

    def test_rejects_nonpositive_values_and_contact_from_another_company(self):
        response = self.client.post(
            reverse("crm:opportunity-edit", args=[self.opportunity.opportunity_code]),
            self.opportunity_payload(
                primary_contact=self.outside_contact.pk,
                client_budget_eur="0",
                stand_area_sqm="-1",
                requested_height_m="0",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertContains(response, "Enter a value greater than zero", count=3)
        self.opportunity.refresh_from_db()
        self.assertIsNone(self.opportunity.primary_contact)
        self.assertIsNone(self.opportunity.client_budget_eur)

    def test_records_conversation_on_current_opportunity(self):
        follow_up_on = timezone.localdate() + timedelta(days=2)
        response = self.client.post(
            reverse(
                "crm:conversation-create",
                args=[self.opportunity.opportunity_code],
            ),
            {
                "activity_type": Activity.ActivityType.CALL,
                "occurred_at": "2026-09-15T14:30",
                "details": "Andrea will confirm the allocated plot.",
                "follow_up_on": follow_up_on.isoformat(),
            },
        )

        self.assertRedirects(
            response,
            f"{self.opportunity.get_absolute_url()}?saved=conversation",
        )
        activity = Activity.objects.get(details="Andrea will confirm the allocated plot.")
        self.assertEqual(activity.company, self.company)
        self.assertEqual(activity.opportunity, self.opportunity)
        self.assertEqual(activity.activity_type, Activity.ActivityType.CALL)
        self.assertEqual(activity.completion_marker, Activity.CompletionMarker.COMPLETED)
        self.assertEqual(activity.follow_up_on, follow_up_on)
        self.assertTrue(timezone.is_aware(activity.occurred_at))

        self.assertContains(
            self.client.get(self.opportunity.get_absolute_url()),
            "Andrea will confirm the allocated plot.",
        )
        self.assertContains(
            self.client.get(reverse("crm:home")),
            "Andrea will confirm the allocated plot.",
        )

    def test_schedules_pending_task_and_exposes_it_on_dashboard(self):
        follow_up_on = timezone.localdate() + timedelta(days=1)
        response = self.client.post(
            reverse("crm:follow-up-create", args=[self.opportunity.opportunity_code]),
            {
                "details": "Ask Andrea for the plot drawing.",
                "follow_up_on": follow_up_on.isoformat(),
            },
        )

        self.assertRedirects(
            response,
            f"{self.opportunity.get_absolute_url()}?saved=follow-up",
        )
        activity = Activity.objects.get(details="Ask Andrea for the plot drawing.")
        self.assertEqual(activity.company, self.company)
        self.assertEqual(activity.opportunity, self.opportunity)
        self.assertEqual(activity.activity_type, Activity.ActivityType.TASK)
        self.assertEqual(activity.completion_marker, Activity.CompletionMarker.PENDING)
        self.assertEqual(activity.follow_up_on, follow_up_on)
        self.assertContains(
            self.client.get(reverse("crm:home")),
            "Ask Andrea for the plot drawing.",
        )
