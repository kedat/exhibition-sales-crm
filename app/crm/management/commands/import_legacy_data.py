from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from crm.services.importer import ArchiveValidationError, import_archive


class Command(BaseCommand):
    help = "Validate and transactionally import the supplied legacy sales archive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=Path("/app/data"),
            help="Directory containing manifest.json and the legacy CSV files.",
        )

    def handle(self, *args, **options):
        try:
            result = import_archive(options["data_dir"])
        except ArchiveValidationError as exc:
            raise CommandError(str(exc)) from exc

        if result.skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Legacy archive already imported (run {result.import_run_id}); skipping."
                )
            )
            return

        counts = result.record_counts
        self.stdout.write(
            self.style.SUCCESS(
                "Imported legacy archive: "
                f"{counts['companies']} companies, "
                f"{counts['contacts']} contacts, "
                f"{counts['fair_editions']} fair editions, "
                f"{counts['opportunities']} opportunities and "
                f"{counts['activity_log_entries']} activities "
                f"(run {result.import_run_id})."
            )
        )
