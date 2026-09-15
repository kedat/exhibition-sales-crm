from decimal import Decimal

from django import forms

from crm.models import Activity, Contact, Opportunity


POSITIVE_VALUE_ERROR = "Enter a value greater than zero."


class OpportunityUpdateForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = [
            "primary_contact",
            "sales_status",
            "expected_close_on",
            "client_budget_eur",
            "stand_area_sqm",
            "requested_height_m",
            "brief_notes",
        ]
        labels = {
            "client_budget_eur": "Client budget (EUR)",
            "stand_area_sqm": "Allocated stand area (m²)",
            "requested_height_m": "Requested height (m)",
        }
        widgets = {
            "expected_close_on": forms.DateInput(attrs={"type": "date"}),
            "brief_notes": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.company_id:
            self.fields["primary_contact"].queryset = self.instance.company.contacts.all()
        else:
            self.fields["primary_contact"].queryset = Contact.objects.none()
        self.fields["primary_contact"].required = False
        self.fields["primary_contact"].empty_label = "No primary contact"

    def clean_primary_contact(self):
        contact = self.cleaned_data.get("primary_contact")
        if contact is not None and contact.company_id != self.instance.company_id:
            raise forms.ValidationError(
                "Primary contact must belong to this opportunity's company."
            )
        return contact

    def clean_expected_close_on(self):
        expected_close_on = self.cleaned_data.get("expected_close_on")
        if expected_close_on and expected_close_on < self.instance.opened_on:
            raise forms.ValidationError(
                "Expected close date cannot be before the opportunity opened."
            )
        return expected_close_on

    def _clean_positive_decimal(self, field_name):
        value = self.cleaned_data.get(field_name)
        if value is not None and value <= Decimal("0"):
            raise forms.ValidationError(POSITIVE_VALUE_ERROR)
        return value

    def clean_client_budget_eur(self):
        return self._clean_positive_decimal("client_budget_eur")

    def clean_stand_area_sqm(self):
        return self._clean_positive_decimal("stand_area_sqm")

    def clean_requested_height_m(self):
        # A value above the fair limit is intentionally retained. The handoff
        # checker introduced in Phase 6 owns that business decision.
        return self._clean_positive_decimal("requested_height_m")


class ConversationForm(forms.Form):
    activity_type = forms.ChoiceField(
        choices=[
            (Activity.ActivityType.CALL, "Call"),
            (Activity.ActivityType.EMAIL, "Email"),
            (Activity.ActivityType.MEETING, "Meeting"),
        ],
        label="Conversation type",
    )
    occurred_at = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
        label="Occurred at",
        help_text="Interpreted in Europe/Rome.",
    )
    details = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))
    follow_up_on = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Follow-up date",
    )


class FollowUpForm(forms.Form):
    details = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        label="What needs to happen?",
    )
    follow_up_on = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Follow-up date",
    )
