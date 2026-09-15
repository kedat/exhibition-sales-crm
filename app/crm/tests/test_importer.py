import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from crm.models import Activity, Company, Contact, FairEdition, ImportRun, Opportunity
from crm.services.importer import (
    ArchiveValidationError,
    EXPECTED_HEADERS,
    import_archive,
    load_archive,
    normalize_legacy_status,
    parse_decimal_comma,
)


class LegacyArchiveTestMixin:
    rows = {
        "companies_and_contacts.csv": [
            {
                "legacy_row_id": "AN0000001",
                "company_code": "CO000001",
                "company_name": "Aster Cosmetics S.r.l.",
                "province_code": "BA",
                "region": "Apulia",
                "sales_rep": "Casey Martin",
                "contact_code": "CO000001-P01",
                "contact_first_name": "Andrea",
                "contact_last_name": "Greco",
                "email": "andrea@example.test",
                "phone": "+39 02 90000101",
                "fax": "",
                "legacy_print_layout": "FORM-2|ROW-1|ARCHIVE-A",
            },
            {
                "legacy_row_id": "AN0000002",
                "company_code": "CO000001",
                "company_name": "Aster Cosmetics S.r.l.",
                "province_code": "BA",
                "region": "Apulia",
                "sales_rep": "Casey Martin",
                "contact_code": "CO000001-P02",
                "contact_first_name": "Sam",
                "contact_last_name": "Rossi",
                "email": "",
                "phone": "",
                "fax": "",
                "legacy_print_layout": "MUST-NOT-BE-IMPORTED",
            },
        ],
        "fair_editions.csv": [
            {
                "fair_edition_code": "BEAUTY-2027",
                "fair_name": "Beauty Trade Forum",
                "city": "Bologna",
                "venue": "East Exhibition Centre",
                "starts_on": "24/06/2027",
                "ends_on": "27/06/2027",
                "max_stand_height_m": "4,50",
            }
        ],
        "opportunities.csv": [
            {
                "opportunity_code": "OP000001",
                "company_code": "CO000001",
                "contact_code": "",
                "description": "Product launch stand",
                "amount_eur": "12500,00",
                "legacy_status": " open ",
                "opened_on": "15/01/2026",
                "expected_close_on": "",
                "historical_campaign_code": "",
                "fair_edition_code": "BEAUTY-2027",
                "stand_area_sqm": "",
                "client_budget_eur": "13000,50",
                "requested_height_m": "4,00",
                "brief_notes": "Waiting for plot drawing",
            }
        ],
        "activity_log.csv": [
            {
                "entry_id": "AC0000001",
                "company_code": "CO000001",
                "opportunity_code": "",
                "activity_type": "note",
                "occurred_at": "01/09/2026 09:00",
                "details": "Company-level note",
                "follow_up_on": "03/09/2026",
                "completion_marker": "",
                "legacy_author": "a.morgan",
            }
        ],
    }

    def write_archive(self, directory: Path) -> None:
        files = {}
        for file_name, rows in self.rows.items():
            path = directory / file_name
            with path.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(
                    destination,
                    fieldnames=EXPECTED_HEADERS[file_name],
                    delimiter=";",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)
            files[file_name] = {
                "data_rows": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        manifest = {
            "dataset_version": "test-1.0.0",
            "format": {"encoding": "UTF-8", "delimiter": ";", "line_endings": "LF"},
            "entities": {
                "companies": 1,
                "contacts": 2,
                "opportunities": 1,
                "activity_log_entries": 1,
                "fair_editions": 1,
            },
            "files": files,
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )


class ImportParsingTests(TestCase):
    def test_normalizes_status_and_decimal_comma(self):
        self.assertEqual(normalize_legacy_status(" Proposal "), "proposal")
        self.assertEqual(parse_decimal_comma("12500,50"), 12500.50)
        self.assertIsNone(parse_decimal_comma(""))

    def test_rejects_unknown_status(self):
        with self.assertRaisesMessage(ArchiveValidationError, "Unsupported legacy status"):
            normalize_legacy_status("technically approved")


class LegacyArchiveImportTests(LegacyArchiveTestMixin, TestCase):
    def test_imports_transformations_relationships_and_skips_second_run(self):
        with TemporaryDirectory() as temporary_directory:
            archive_dir = Path(temporary_directory)
            self.write_archive(archive_dir)

            first_result = import_archive(archive_dir)
            second_result = import_archive(archive_dir)

        self.assertFalse(first_result.skipped)
        self.assertTrue(second_result.skipped)
        self.assertEqual(first_result.import_run_id, second_result.import_run_id)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 2)
        self.assertEqual(FairEdition.objects.count(), 1)
        self.assertEqual(Opportunity.objects.count(), 1)
        self.assertEqual(Activity.objects.count(), 1)

        opportunity = Opportunity.objects.get(opportunity_code="OP000001")
        self.assertEqual(opportunity.sales_status, Opportunity.SalesStatus.OPEN)
        self.assertEqual(str(opportunity.amount_eur), "12500.00")
        self.assertEqual(str(opportunity.client_budget_eur), "13000.50")
        self.assertIsNone(opportunity.primary_contact)
        self.assertIsNone(opportunity.stand_area_sqm)
        self.assertIsNone(opportunity.expected_close_on)

        contact = Contact.objects.get(contact_code="CO000001-P02")
        self.assertIsNone(contact.email)
        self.assertIsNone(contact.phone)
        self.assertFalse(hasattr(contact, "legacy_print_layout"))

        activity = Activity.objects.get(legacy_entry_id="AC0000001")
        self.assertIsNone(activity.opportunity)
        occurred_in_rome = timezone.localtime(
            activity.occurred_at, ZoneInfo("Europe/Rome")
        )
        self.assertEqual(occurred_in_rome.strftime("%d/%m/%Y %H:%M"), "01/09/2026 09:00")

        run = ImportRun.objects.get(pk=first_result.import_run_id)
        self.assertEqual(run.status, ImportRun.Status.COMPLETED)
        self.assertEqual(run.record_counts["source_rows"], 5)
        self.assertIsNotNone(run.completed_at)

    def test_checksum_failure_writes_nothing(self):
        with TemporaryDirectory() as temporary_directory:
            archive_dir = Path(temporary_directory)
            self.write_archive(archive_dir)
            with (archive_dir / "opportunities.csv").open(
                "a", encoding="utf-8"
            ) as source:
                source.write("tampered\n")

            with self.assertRaisesMessage(ArchiveValidationError, "Checksum mismatch"):
                load_archive(archive_dir)

        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(ImportRun.objects.count(), 0)

    def test_database_failure_rolls_back_all_entities_and_records_failure(self):
        with TemporaryDirectory() as temporary_directory:
            archive_dir = Path(temporary_directory)
            self.write_archive(archive_dir)

            with patch.object(
                Contact.objects, "bulk_create", side_effect=RuntimeError("forced failure")
            ):
                with self.assertRaisesMessage(RuntimeError, "forced failure"):
                    import_archive(archive_dir)

        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Contact.objects.count(), 0)
        failed_run = ImportRun.objects.get()
        self.assertEqual(failed_run.status, ImportRun.Status.FAILED)
        self.assertEqual(failed_run.error_message, "forced failure")
