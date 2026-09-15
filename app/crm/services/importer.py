from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from crm.models import (
    Activity,
    Company,
    Contact,
    FairEdition,
    ImportRun,
    Opportunity,
)


ROME = ZoneInfo("Europe/Rome")
DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"
BATCH_SIZE = 2_000

EXPECTED_HEADERS = {
    "companies_and_contacts.csv": [
        "legacy_row_id",
        "company_code",
        "company_name",
        "province_code",
        "region",
        "sales_rep",
        "contact_code",
        "contact_first_name",
        "contact_last_name",
        "email",
        "phone",
        "fax",
        "legacy_print_layout",
    ],
    "opportunities.csv": [
        "opportunity_code",
        "company_code",
        "contact_code",
        "description",
        "amount_eur",
        "legacy_status",
        "opened_on",
        "expected_close_on",
        "historical_campaign_code",
        "fair_edition_code",
        "stand_area_sqm",
        "client_budget_eur",
        "requested_height_m",
        "brief_notes",
    ],
    "activity_log.csv": [
        "entry_id",
        "company_code",
        "opportunity_code",
        "activity_type",
        "occurred_at",
        "details",
        "follow_up_on",
        "completion_marker",
        "legacy_author",
    ],
    "fair_editions.csv": [
        "fair_edition_code",
        "fair_name",
        "city",
        "venue",
        "starts_on",
        "ends_on",
        "max_stand_height_m",
    ],
}


class ArchiveValidationError(ValueError):
    """Raised when the supplied legacy archive does not match its contract."""


@dataclass(frozen=True, slots=True)
class ImportResult:
    skipped: bool
    import_run_id: int
    record_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    company_code: str
    name: str
    province_code: str | None
    region: str | None
    sales_rep: str | None


@dataclass(frozen=True, slots=True)
class ContactRecord:
    legacy_row_id: str
    contact_code: str
    company_code: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    fax: str | None


@dataclass(frozen=True, slots=True)
class FairEditionRecord:
    fair_edition_code: str
    fair_name: str
    city: str
    venue: str
    starts_on: date
    ends_on: date
    max_stand_height_m: Decimal


@dataclass(frozen=True, slots=True)
class OpportunityRecord:
    opportunity_code: str
    company_code: str
    contact_code: str | None
    fair_edition_code: str
    description: str | None
    amount_eur: Decimal | None
    client_budget_eur: Decimal | None
    sales_status: str
    opened_on: date
    expected_close_on: date | None
    historical_campaign_code: str | None
    stand_area_sqm: Decimal | None
    requested_height_m: Decimal | None
    brief_notes: str | None


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    legacy_entry_id: str
    company_code: str
    opportunity_code: str | None
    activity_type: str
    occurred_at: datetime
    details: str
    follow_up_on: date | None
    completion_marker: str | None
    author: str | None


@dataclass(frozen=True, slots=True)
class ArchiveData:
    dataset_version: str
    checksums: dict[str, str]
    source_row_counts: dict[str, int]
    companies: tuple[CompanyRecord, ...]
    contacts: tuple[ContactRecord, ...]
    fair_editions: tuple[FairEditionRecord, ...]
    opportunities: tuple[OpportunityRecord, ...]
    activities: tuple[ActivityRecord, ...]

    @property
    def entity_counts(self) -> dict[str, int]:
        return {
            "companies": len(self.companies),
            "contacts": len(self.contacts),
            "fair_editions": len(self.fair_editions),
            "opportunities": len(self.opportunities),
            "activity_log_entries": len(self.activities),
        }


def _optional(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _required(value: str, *, file_name: str, row_number: int, field: str) -> str:
    normalized = _optional(value)
    if normalized is None:
        raise ArchiveValidationError(
            f"{file_name} row {row_number}: {field} is required"
        )
    return normalized


def _parse_date(
    value: str,
    *,
    file_name: str,
    row_number: int,
    field: str,
    required: bool = False,
) -> date | None:
    normalized = _optional(value)
    if normalized is None:
        if required:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: {field} is required"
            )
        return None
    try:
        return datetime.strptime(normalized, DATE_FORMAT).date()
    except ValueError as exc:
        raise ArchiveValidationError(
            f"{file_name} row {row_number}: invalid {field} date {normalized!r}"
        ) from exc


def _parse_datetime(
    value: str, *, file_name: str, row_number: int, field: str
) -> datetime:
    normalized = _required(
        value,
        file_name=file_name,
        row_number=row_number,
        field=field,
    )
    try:
        parsed = datetime.strptime(normalized, DATETIME_FORMAT)
    except ValueError as exc:
        raise ArchiveValidationError(
            f"{file_name} row {row_number}: invalid {field} datetime {normalized!r}"
        ) from exc
    return timezone.make_aware(parsed, ROME)


def parse_decimal_comma(
    value: str,
    *,
    file_name: str = "value",
    row_number: int = 0,
    field: str = "decimal",
    required: bool = False,
) -> Decimal | None:
    normalized = _optional(value)
    if normalized is None:
        if required:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: {field} is required"
            )
        return None
    try:
        return Decimal(normalized.replace(",", "."))
    except InvalidOperation as exc:
        raise ArchiveValidationError(
            f"{file_name} row {row_number}: invalid {field} decimal {normalized!r}"
        ) from exc


def normalize_legacy_status(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {choice.value for choice in Opportunity.SalesStatus}
    if normalized not in allowed:
        raise ArchiveValidationError(f"Unsupported legacy status {value!r}")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(data_dir: Path) -> dict:
    path = data_dir / "manifest.json"
    if not path.is_file():
        raise ArchiveValidationError(f"Missing source file: {path.name}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveValidationError("manifest.json is not valid UTF-8 JSON") from exc

    source_format = manifest.get("format", {})
    if source_format.get("encoding") != "UTF-8" or source_format.get("delimiter") != ";":
        raise ArchiveValidationError("Unsupported archive encoding or delimiter")
    if not _optional(str(manifest.get("dataset_version", ""))):
        raise ArchiveValidationError("manifest.json has no dataset_version")
    return manifest


def _read_csv_files(
    data_dir: Path, manifest: dict
) -> tuple[dict[str, list[dict[str, str]]], dict[str, str], dict[str, int]]:
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict):
        raise ArchiveValidationError("manifest.json has no valid files section")

    rows_by_file: dict[str, list[dict[str, str]]] = {}
    checksums: dict[str, str] = {}
    row_counts: dict[str, int] = {}

    for file_name, expected_headers in EXPECTED_HEADERS.items():
        metadata = manifest_files.get(file_name)
        if not isinstance(metadata, dict):
            raise ArchiveValidationError(f"manifest.json is missing {file_name}")

        path = data_dir / file_name
        if not path.is_file():
            raise ArchiveValidationError(f"Missing source file: {file_name}")

        actual_checksum = _sha256(path)
        expected_checksum = str(metadata.get("sha256", "")).lower()
        if actual_checksum != expected_checksum:
            raise ArchiveValidationError(
                f"Checksum mismatch for {file_name}: expected {expected_checksum}, "
                f"got {actual_checksum}"
            )

        try:
            with path.open("r", encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source, delimiter=";")
                if reader.fieldnames != expected_headers:
                    raise ArchiveValidationError(
                        f"Unexpected headers in {file_name}: expected {expected_headers}, "
                        f"got {reader.fieldnames}"
                    )
                rows = list(reader)
        except UnicodeDecodeError as exc:
            raise ArchiveValidationError(f"{file_name} is not valid UTF-8") from exc

        expected_count = metadata.get("data_rows")
        if not isinstance(expected_count, int) or len(rows) != expected_count:
            raise ArchiveValidationError(
                f"Record count mismatch for {file_name}: expected {expected_count}, "
                f"got {len(rows)}"
            )
        rows_by_file[file_name] = rows
        checksums[file_name] = actual_checksum
        row_counts[file_name] = len(rows)

    return rows_by_file, checksums, row_counts


def _parse_companies_and_contacts(
    rows: list[dict[str, str]],
) -> tuple[tuple[CompanyRecord, ...], tuple[ContactRecord, ...]]:
    file_name = "companies_and_contacts.csv"
    companies: dict[str, CompanyRecord] = {}
    contacts: list[ContactRecord] = []
    contact_codes: set[str] = set()
    legacy_row_ids: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        company_code = _required(
            row["company_code"],
            file_name=file_name,
            row_number=row_number,
            field="company_code",
        )
        company = CompanyRecord(
            company_code=company_code,
            name=_required(
                row["company_name"],
                file_name=file_name,
                row_number=row_number,
                field="company_name",
            ),
            province_code=_optional(row["province_code"]),
            region=_optional(row["region"]),
            sales_rep=_optional(row["sales_rep"]),
        )
        existing_company = companies.get(company_code)
        if existing_company is not None and existing_company != company:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: inconsistent repeated company "
                f"{company_code}"
            )
        companies[company_code] = company

        legacy_row_id = _required(
            row["legacy_row_id"],
            file_name=file_name,
            row_number=row_number,
            field="legacy_row_id",
        )
        contact_code = _required(
            row["contact_code"],
            file_name=file_name,
            row_number=row_number,
            field="contact_code",
        )
        if legacy_row_id in legacy_row_ids:
            raise ArchiveValidationError(f"Duplicate legacy_row_id {legacy_row_id}")
        if contact_code in contact_codes:
            raise ArchiveValidationError(f"Duplicate contact_code {contact_code}")
        legacy_row_ids.add(legacy_row_id)
        contact_codes.add(contact_code)
        contacts.append(
            ContactRecord(
                legacy_row_id=legacy_row_id,
                contact_code=contact_code,
                company_code=company_code,
                first_name=_optional(row["contact_first_name"]),
                last_name=_optional(row["contact_last_name"]),
                email=_optional(row["email"]),
                phone=_optional(row["phone"]),
                fax=_optional(row["fax"]),
            )
        )

    return tuple(companies.values()), tuple(contacts)


def _parse_fair_editions(
    rows: list[dict[str, str]],
) -> tuple[FairEditionRecord, ...]:
    file_name = "fair_editions.csv"
    records: list[FairEditionRecord] = []
    codes: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        code = _required(
            row["fair_edition_code"],
            file_name=file_name,
            row_number=row_number,
            field="fair_edition_code",
        )
        if code in codes:
            raise ArchiveValidationError(f"Duplicate fair_edition_code {code}")
        codes.add(code)
        starts_on = _parse_date(
            row["starts_on"],
            file_name=file_name,
            row_number=row_number,
            field="starts_on",
            required=True,
        )
        ends_on = _parse_date(
            row["ends_on"],
            file_name=file_name,
            row_number=row_number,
            field="ends_on",
            required=True,
        )
        height = parse_decimal_comma(
            row["max_stand_height_m"],
            file_name=file_name,
            row_number=row_number,
            field="max_stand_height_m",
            required=True,
        )
        assert starts_on is not None and ends_on is not None and height is not None
        if ends_on < starts_on:
            raise ArchiveValidationError(f"{file_name} row {row_number}: fair ends before it starts")
        if height <= 0:
            raise ArchiveValidationError(f"{file_name} row {row_number}: height must be positive")
        records.append(
            FairEditionRecord(
                fair_edition_code=code,
                fair_name=_required(
                    row["fair_name"],
                    file_name=file_name,
                    row_number=row_number,
                    field="fair_name",
                ),
                city=_required(
                    row["city"],
                    file_name=file_name,
                    row_number=row_number,
                    field="city",
                ),
                venue=_required(
                    row["venue"],
                    file_name=file_name,
                    row_number=row_number,
                    field="venue",
                ),
                starts_on=starts_on,
                ends_on=ends_on,
                max_stand_height_m=height,
            )
        )
    return tuple(records)


def _parse_opportunities(
    rows: list[dict[str, str]],
    companies: dict[str, CompanyRecord],
    contacts: dict[str, ContactRecord],
    fair_editions: dict[str, FairEditionRecord],
) -> tuple[OpportunityRecord, ...]:
    file_name = "opportunities.csv"
    records: list[OpportunityRecord] = []
    codes: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        code = _required(
            row["opportunity_code"],
            file_name=file_name,
            row_number=row_number,
            field="opportunity_code",
        )
        company_code = _required(
            row["company_code"],
            file_name=file_name,
            row_number=row_number,
            field="company_code",
        )
        contact_code = _optional(row["contact_code"])
        fair_code = _required(
            row["fair_edition_code"],
            file_name=file_name,
            row_number=row_number,
            field="fair_edition_code",
        )
        if code in codes:
            raise ArchiveValidationError(f"Duplicate opportunity_code {code}")
        if company_code not in companies:
            raise ArchiveValidationError(f"{code} references unknown company {company_code}")
        if fair_code not in fair_editions:
            raise ArchiveValidationError(f"{code} references unknown fair edition {fair_code}")
        if contact_code is not None:
            contact = contacts.get(contact_code)
            if contact is None:
                raise ArchiveValidationError(f"{code} references unknown contact {contact_code}")
            if contact.company_code != company_code:
                raise ArchiveValidationError(
                    f"{code} contact {contact_code} belongs to another company"
                )
        codes.add(code)

        opened_on = _parse_date(
            row["opened_on"],
            file_name=file_name,
            row_number=row_number,
            field="opened_on",
            required=True,
        )
        expected_close_on = _parse_date(
            row["expected_close_on"],
            file_name=file_name,
            row_number=row_number,
            field="expected_close_on",
        )
        assert opened_on is not None
        if expected_close_on is not None and expected_close_on < opened_on:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: expected close precedes open date"
            )

        amount = parse_decimal_comma(
            row["amount_eur"], file_name=file_name, row_number=row_number, field="amount_eur"
        )
        budget = parse_decimal_comma(
            row["client_budget_eur"],
            file_name=file_name,
            row_number=row_number,
            field="client_budget_eur",
        )
        area = parse_decimal_comma(
            row["stand_area_sqm"],
            file_name=file_name,
            row_number=row_number,
            field="stand_area_sqm",
        )
        height = parse_decimal_comma(
            row["requested_height_m"],
            file_name=file_name,
            row_number=row_number,
            field="requested_height_m",
        )
        if amount is not None and amount < 0:
            raise ArchiveValidationError(f"{file_name} row {row_number}: amount must not be negative")
        if budget is not None and budget < 0:
            raise ArchiveValidationError(f"{file_name} row {row_number}: budget must not be negative")
        if area is not None and area <= 0:
            raise ArchiveValidationError(f"{file_name} row {row_number}: area must be positive")
        if height is not None and height <= 0:
            raise ArchiveValidationError(f"{file_name} row {row_number}: height must be positive")

        try:
            sales_status = normalize_legacy_status(row["legacy_status"])
        except ArchiveValidationError as exc:
            raise ArchiveValidationError(f"{file_name} row {row_number}: {exc}") from exc

        records.append(
            OpportunityRecord(
                opportunity_code=code,
                company_code=company_code,
                contact_code=contact_code,
                fair_edition_code=fair_code,
                description=_optional(row["description"]),
                amount_eur=amount,
                client_budget_eur=budget,
                sales_status=sales_status,
                opened_on=opened_on,
                expected_close_on=expected_close_on,
                historical_campaign_code=_optional(row["historical_campaign_code"]),
                stand_area_sqm=area,
                requested_height_m=height,
                brief_notes=_optional(row["brief_notes"]),
            )
        )
    return tuple(records)


def _parse_activities(
    rows: list[dict[str, str]],
    companies: dict[str, CompanyRecord],
    opportunities: dict[str, OpportunityRecord],
) -> tuple[ActivityRecord, ...]:
    file_name = "activity_log.csv"
    records: list[ActivityRecord] = []
    entry_ids: set[str] = set()
    allowed_types = {choice.value for choice in Activity.ActivityType}
    allowed_markers = {choice.value for choice in Activity.CompletionMarker}

    for row_number, row in enumerate(rows, start=2):
        entry_id = _required(
            row["entry_id"],
            file_name=file_name,
            row_number=row_number,
            field="entry_id",
        )
        company_code = _required(
            row["company_code"],
            file_name=file_name,
            row_number=row_number,
            field="company_code",
        )
        opportunity_code = _optional(row["opportunity_code"])
        activity_type = _required(
            row["activity_type"],
            file_name=file_name,
            row_number=row_number,
            field="activity_type",
        ).lower()
        marker = _optional(row["completion_marker"])

        if entry_id in entry_ids:
            raise ArchiveValidationError(f"Duplicate entry_id {entry_id}")
        if company_code not in companies:
            raise ArchiveValidationError(f"{entry_id} references unknown company {company_code}")
        if opportunity_code is not None:
            opportunity = opportunities.get(opportunity_code)
            if opportunity is None:
                raise ArchiveValidationError(
                    f"{entry_id} references unknown opportunity {opportunity_code}"
                )
            if opportunity.company_code != company_code:
                raise ArchiveValidationError(
                    f"{entry_id} opportunity {opportunity_code} belongs to another company"
                )
        if activity_type not in allowed_types:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: unsupported activity type {activity_type!r}"
            )
        if marker is not None and marker not in allowed_markers:
            raise ArchiveValidationError(
                f"{file_name} row {row_number}: unsupported completion marker {marker!r}"
            )
        entry_ids.add(entry_id)
        records.append(
            ActivityRecord(
                legacy_entry_id=entry_id,
                company_code=company_code,
                opportunity_code=opportunity_code,
                activity_type=activity_type,
                occurred_at=_parse_datetime(
                    row["occurred_at"],
                    file_name=file_name,
                    row_number=row_number,
                    field="occurred_at",
                ),
                details=_required(
                    row["details"],
                    file_name=file_name,
                    row_number=row_number,
                    field="details",
                ),
                follow_up_on=_parse_date(
                    row["follow_up_on"],
                    file_name=file_name,
                    row_number=row_number,
                    field="follow_up_on",
                ),
                completion_marker=marker,
                author=_optional(row["legacy_author"]),
            )
        )
    return tuple(records)


def load_archive(data_dir: Path | str) -> ArchiveData:
    data_dir = Path(data_dir)
    manifest = _read_manifest(data_dir)
    rows, checksums, source_row_counts = _read_csv_files(data_dir, manifest)

    companies, contacts = _parse_companies_and_contacts(
        rows["companies_and_contacts.csv"]
    )
    fair_editions = _parse_fair_editions(rows["fair_editions.csv"])
    company_map = {record.company_code: record for record in companies}
    contact_map = {record.contact_code: record for record in contacts}
    fair_map = {record.fair_edition_code: record for record in fair_editions}
    opportunities = _parse_opportunities(
        rows["opportunities.csv"], company_map, contact_map, fair_map
    )
    opportunity_map = {record.opportunity_code: record for record in opportunities}
    activities = _parse_activities(
        rows["activity_log.csv"], company_map, opportunity_map
    )

    archive = ArchiveData(
        dataset_version=str(manifest["dataset_version"]),
        checksums=checksums,
        source_row_counts=source_row_counts,
        companies=companies,
        contacts=contacts,
        fair_editions=fair_editions,
        opportunities=opportunities,
        activities=activities,
    )
    expected_entities = manifest.get("entities")
    if expected_entities != archive.entity_counts:
        raise ArchiveValidationError(
            f"Entity count mismatch: expected {expected_entities}, got {archive.entity_counts}"
        )
    return archive


def _persist_archive(archive: ArchiveData) -> None:
    Company.objects.bulk_create(
        [
            Company(
                company_code=item.company_code,
                name=item.name,
                province_code=item.province_code,
                region=item.region,
                sales_rep=item.sales_rep,
            )
            for item in archive.companies
        ],
        batch_size=BATCH_SIZE,
    )
    company_ids = dict(Company.objects.values_list("company_code", "id"))

    Contact.objects.bulk_create(
        [
            Contact(
                legacy_row_id=item.legacy_row_id,
                contact_code=item.contact_code,
                company_id=company_ids[item.company_code],
                first_name=item.first_name,
                last_name=item.last_name,
                email=item.email,
                phone=item.phone,
                fax=item.fax,
            )
            for item in archive.contacts
        ],
        batch_size=BATCH_SIZE,
    )
    contact_ids = dict(Contact.objects.values_list("contact_code", "id"))

    FairEdition.objects.bulk_create(
        [
            FairEdition(
                fair_edition_code=item.fair_edition_code,
                fair_name=item.fair_name,
                city=item.city,
                venue=item.venue,
                starts_on=item.starts_on,
                ends_on=item.ends_on,
                max_stand_height_m=item.max_stand_height_m,
            )
            for item in archive.fair_editions
        ],
        batch_size=BATCH_SIZE,
    )
    fair_ids = dict(FairEdition.objects.values_list("fair_edition_code", "id"))

    Opportunity.objects.bulk_create(
        [
            Opportunity(
                opportunity_code=item.opportunity_code,
                company_id=company_ids[item.company_code],
                primary_contact_id=(
                    contact_ids[item.contact_code] if item.contact_code else None
                ),
                fair_edition_id=fair_ids[item.fair_edition_code],
                description=item.description,
                amount_eur=item.amount_eur,
                client_budget_eur=item.client_budget_eur,
                sales_status=item.sales_status,
                opened_on=item.opened_on,
                expected_close_on=item.expected_close_on,
                historical_campaign_code=item.historical_campaign_code,
                stand_area_sqm=item.stand_area_sqm,
                requested_height_m=item.requested_height_m,
                brief_notes=item.brief_notes,
            )
            for item in archive.opportunities
        ],
        batch_size=BATCH_SIZE,
    )
    opportunity_ids = dict(
        Opportunity.objects.values_list("opportunity_code", "id")
    )

    Activity.objects.bulk_create(
        [
            Activity(
                legacy_entry_id=item.legacy_entry_id,
                company_id=company_ids[item.company_code],
                opportunity_id=(
                    opportunity_ids[item.opportunity_code]
                    if item.opportunity_code
                    else None
                ),
                activity_type=item.activity_type,
                occurred_at=item.occurred_at,
                details=item.details,
                follow_up_on=item.follow_up_on,
                completion_marker=item.completion_marker,
                author=item.author,
            )
            for item in archive.activities
        ],
        batch_size=BATCH_SIZE,
    )


def import_archive(data_dir: Path | str) -> ImportResult:
    archive = load_archive(data_dir)
    record_counts = {
        **archive.entity_counts,
        "source_rows": sum(archive.source_row_counts.values()),
    }
    completed_run = ImportRun.objects.filter(
        dataset_version=archive.dataset_version,
        source_checksums=archive.checksums,
        status=ImportRun.Status.COMPLETED,
    ).first()
    if completed_run is not None:
        return ImportResult(
            skipped=True,
            import_run_id=completed_run.pk,
            record_counts=completed_run.record_counts,
        )

    run = ImportRun.objects.create(
        dataset_version=archive.dataset_version,
        source_checksums=archive.checksums,
        record_counts=record_counts,
        status=ImportRun.Status.RUNNING,
    )
    try:
        with transaction.atomic():
            _persist_archive(archive)
            run.status = ImportRun.Status.COMPLETED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at"])
    except Exception as exc:
        ImportRun.objects.filter(pk=run.pk).update(
            status=ImportRun.Status.FAILED,
            completed_at=timezone.now(),
            error_message=str(exc),
        )
        raise

    return ImportResult(
        skipped=False,
        import_run_id=run.pk,
        record_counts=record_counts,
    )
