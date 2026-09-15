from django.contrib.postgres.indexes import GinIndex, OpClass
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse


class Company(models.Model):
    company_code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    province_code = models.CharField(max_length=2, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    sales_rep = models.CharField(max_length=120, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "company_code"]
        verbose_name_plural = "companies"
        indexes = [
            GinIndex(
                OpClass(Lower("name"), name="gin_trgm_ops"),
                name="company_name_trgm",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Contact(models.Model):
    legacy_row_id = models.CharField(max_length=32, unique=True)
    contact_code = models.CharField(max_length=40, unique=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    first_name = models.CharField(max_length=120, null=True, blank=True)
    last_name = models.CharField(max_length=120, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=80, null=True, blank=True)
    fax = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name", "contact_code"]
        indexes = [
            GinIndex(
                OpClass(Lower("first_name"), name="gin_trgm_ops"),
                name="contact_first_trgm",
            ),
            GinIndex(
                OpClass(Lower("last_name"), name="gin_trgm_ops"),
                name="contact_last_trgm",
            ),
            GinIndex(
                OpClass(Lower("email"), name="gin_trgm_ops"),
                name="contact_email_trgm",
            ),
        ]

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def __str__(self) -> str:
        return self.full_name or self.contact_code


class FairEdition(models.Model):
    fair_edition_code = models.CharField(max_length=32, unique=True)
    fair_name = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    venue = models.CharField(max_length=255)
    starts_on = models.DateField()
    ends_on = models.DateField()
    max_stand_height_m = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["-starts_on", "fair_name"]
        indexes = [
            models.Index(fields=["starts_on", "ends_on"], name="fair_dates_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F("starts_on")),
                name="fair_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(max_stand_height_m__gt=0),
                name="fair_height_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.fair_name} ({self.starts_on.year})"


class Opportunity(models.Model):
    class SalesStatus(models.TextChoices):
        OPEN = "open", "Open"
        QUALIFIED = "qualified", "Qualified"
        PROPOSAL = "proposal", "Proposal"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    opportunity_code = models.CharField(max_length=32, unique=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="opportunities",
    )
    primary_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        related_name="primary_opportunities",
        null=True,
        blank=True,
    )
    fair_edition = models.ForeignKey(
        FairEdition,
        on_delete=models.PROTECT,
        related_name="opportunities",
    )
    description = models.TextField(null=True, blank=True)
    amount_eur = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    client_budget_eur = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    sales_status = models.CharField(max_length=32, choices=SalesStatus.choices)
    opened_on = models.DateField()
    expected_close_on = models.DateField(null=True, blank=True)
    historical_campaign_code = models.CharField(max_length=100, null=True, blank=True)
    stand_area_sqm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    requested_height_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    brief_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opened_on", "opportunity_code"]
        indexes = [
            models.Index(
                fields=["company", "fair_edition"],
                name="opp_company_fair_idx",
            ),
            models.Index(fields=["sales_status"], name="opp_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_eur__isnull=True)
                | models.Q(amount_eur__gte=0),
                name="opp_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(client_budget_eur__isnull=True)
                | models.Q(client_budget_eur__gte=0),
                name="opp_budget_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(stand_area_sqm__isnull=True)
                | models.Q(stand_area_sqm__gt=0),
                name="opp_area_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(requested_height_m__isnull=True)
                | models.Q(requested_height_m__gt=0),
                name="opp_height_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(expected_close_on__isnull=True)
                | models.Q(expected_close_on__gte=models.F("opened_on")),
                name="opp_close_after_open",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.primary_contact_id is None:
            return

        contact_company_id = self.primary_contact.company_id
        if contact_company_id != self.company_id:
            raise ValidationError(
                {"primary_contact": "Primary contact must belong to the company."}
            )

    def __str__(self) -> str:
        return f"{self.opportunity_code} — {self.description or 'Untitled opportunity'}"

    def get_absolute_url(self) -> str:
        return reverse("crm:opportunity-detail", args=[self.opportunity_code])


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        CALL = "call", "Call"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        NOTE = "note", "Note"
        TASK = "task", "Task"

    class CompletionMarker(models.TextChoices):
        COMPLETED = "Y", "Completed interaction"
        PENDING = "N", "Pending task"

    legacy_entry_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="activities",
        null=True,
        blank=True,
    )
    activity_type = models.CharField(max_length=16, choices=ActivityType.choices)
    occurred_at = models.DateTimeField()
    details = models.TextField()
    follow_up_on = models.DateField(null=True, blank=True)
    completion_marker = models.CharField(
        max_length=1,
        choices=CompletionMarker.choices,
        null=True,
        blank=True,
    )
    author = models.CharField(max_length=120, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["opportunity", "-occurred_at"],
                name="activity_opp_time_idx",
            ),
            models.Index(
                fields=["company", "-occurred_at"],
                name="activity_company_time_idx",
            ),
            models.Index(
                fields=["follow_up_on"],
                name="activity_follow_up_idx",
                condition=models.Q(follow_up_on__isnull=False),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.opportunity_id is None:
            return

        opportunity_company_id = self.opportunity.company_id
        if opportunity_company_id != self.company_id:
            raise ValidationError(
                {"opportunity": "Opportunity must belong to the company."}
            )

    def __str__(self) -> str:
        return f"{self.get_activity_type_display()} — {self.occurred_at:%Y-%m-%d}"


class HandoffRun(models.Model):
    class Decision(models.TextChoices):
        CONTINUE = "continue", "Continue"
        STOP = "stop", "Stop"

    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="handoff_runs",
    )
    input_snapshot = models.JSONField()
    preparer_output = models.JSONField()
    checker_output = models.JSONField()
    coordinator_decision = models.CharField(max_length=16, choices=Decision.choices)
    decision_reason = models.TextField()
    next_action = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["opportunity", "-created_at"],
                name="handoff_opp_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.opportunity.opportunity_code} — {self.get_coordinator_decision_display()}"


class ImportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    dataset_version = models.CharField(max_length=64)
    source_checksums = models.JSONField(default=dict)
    record_counts = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["status"], name="import_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Dataset {self.dataset_version} — {self.get_status_display()}"
