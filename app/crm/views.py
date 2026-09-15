from datetime import timedelta

from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Prefetch, Subquery
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from crm.forms import ConversationForm, FollowUpForm, OpportunityUpdateForm
from crm.models import Activity, Company, Contact, HandoffRun, Opportunity
from crm.services.handoff import ASSISTANT_LABEL, run_handoff
from crm.services.handoff_comparison import compare_handoff_runs


FOLLOW_UP_PREVIEW_LIMIT = 8
SEARCH_PAGE_SIZE = 20
SEARCH_MAX_LENGTH = 100


def _company_ids_matching(term):
    """Return a union of narrow, index-backed company/contact searches."""
    branches = [
        Company.objects.alias(search_value=Lower("name"))
        .filter(search_value__contains=term)
        .order_by()
        .values_list("pk", flat=True),
        Company.objects.filter(company_code__startswith=term.upper())
        .order_by()
        .values_list("pk", flat=True),
        Contact.objects.alias(search_value=Lower("first_name"))
        .filter(search_value__contains=term)
        .order_by()
        .values_list("company_id", flat=True),
        Contact.objects.alias(search_value=Lower("last_name"))
        .filter(search_value__contains=term)
        .order_by()
        .values_list("company_id", flat=True),
        Contact.objects.alias(search_value=Lower("email"))
        .filter(search_value__contains=term)
        .order_by()
        .values_list("company_id", flat=True),
        Contact.objects.filter(contact_code__startswith=term.upper())
        .order_by()
        .values_list("company_id", flat=True),
    ]
    return branches[0].union(*branches[1:])


def home(request):
    today = timezone.localdate()
    follow_ups = Activity.objects.filter(
        follow_up_on__isnull=False
    ).select_related("company", "opportunity", "opportunity__primary_contact")

    overdue = follow_ups.filter(follow_up_on__lt=today).order_by(
        "follow_up_on", "occurred_at"
    )
    due_today = follow_ups.filter(follow_up_on=today).order_by("occurred_at")
    upcoming = follow_ups.filter(follow_up_on__gt=today).order_by(
        "follow_up_on", "occurred_at"
    )

    overdue_page = Paginator(overdue, FOLLOW_UP_PREVIEW_LIMIT).get_page(
        request.GET.get("overdue_page")
    )
    due_today_page = Paginator(due_today, FOLLOW_UP_PREVIEW_LIMIT).get_page(
        request.GET.get("today_page")
    )
    upcoming_page = Paginator(upcoming, FOLLOW_UP_PREVIEW_LIMIT).get_page(
        request.GET.get("upcoming_page")
    )

    return render(
        request,
        "crm/home.html",
        {
            "today": today,
            "overdue": overdue_page,
            "overdue_count": overdue_page.paginator.count,
            "due_today": due_today_page,
            "due_today_count": due_today_page.paginator.count,
            "upcoming": upcoming_page,
            "upcoming_count": upcoming_page.paginator.count,
        },
    )


def search(request):
    query = request.GET.get("q", "").strip()[:SEARCH_MAX_LENGTH]
    page_obj = None

    if query:
        normalized_query = query.lower()
        search_terms = normalized_query.split()[:6]
        companies = Company.objects.all()
        for term in search_terms:
            companies = companies.filter(
                pk__in=Subquery(_company_ids_matching(term))
            )

        companies = (
            companies
            .annotate(
                contact_count=Count("contacts", distinct=True),
                opportunity_count=Count("opportunities", distinct=True),
            )
            .prefetch_related("contacts")
            .order_by("name", "company_code")
        )
        page_obj = Paginator(companies, SEARCH_PAGE_SIZE).get_page(
            request.GET.get("page")
        )

    return render(
        request,
        "crm/search.html",
        {"query": query, "page_obj": page_obj},
    )


def company_detail(request, company_code):
    opportunities = Opportunity.objects.select_related(
        "fair_edition", "primary_contact"
    ).order_by("-fair_edition__starts_on", "opportunity_code")
    company = get_object_or_404(
        Company.objects.prefetch_related(
            "contacts",
            Prefetch("opportunities", queryset=opportunities),
        ),
        company_code=company_code,
    )
    company_activities = company.activities.filter(
        opportunity__isnull=True
    ).order_by("-occurred_at")

    return render(
        request,
        "crm/company_detail.html",
        {"company": company, "company_activities": company_activities},
    )


def opportunity_detail(request, opportunity_code):
    opportunity = get_object_or_404(
        Opportunity.objects.select_related(
            "company", "primary_contact", "fair_edition"
        ),
        opportunity_code=opportunity_code,
    )
    activities = opportunity.activities.select_related(
        "company", "source_handoff_run"
    ).order_by("-occurred_at")
    handoff_history = list(
        opportunity.handoff_runs.select_related("approved_follow_up").all()
    )
    latest_handoff = handoff_history[0] if handoff_history else None

    return render(
        request,
        "crm/opportunity_detail.html",
        {
            "opportunity": opportunity,
            "activities": activities,
            "saved_action": request.GET.get("saved"),
            "assistant_label": ASSISTANT_LABEL,
            "latest_handoff": latest_handoff,
            "latest_comparison": (
                compare_handoff_runs(latest_handoff) if latest_handoff else None
            ),
            "handoff_history": handoff_history,
        },
    )


def opportunity_edit(request, opportunity_code):
    opportunity = get_object_or_404(
        Opportunity.objects.select_related("company", "fair_edition"),
        opportunity_code=opportunity_code,
    )
    form = OpportunityUpdateForm(
        request.POST or None,
        instance=opportunity,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(
            f"{opportunity.get_absolute_url()}?saved=opportunity"
        )

    return render(
        request,
        "crm/form_page.html",
        {
            "opportunity": opportunity,
            "form": form,
            "eyebrow": "Opportunity",
            "heading": "Edit commercial brief",
            "description": (
                "Update the sales information used by the technical handoff."
            ),
            "submit_label": "Save opportunity",
        },
    )


def conversation_create(request, opportunity_code):
    opportunity = get_object_or_404(
        Opportunity.objects.select_related("company"),
        opportunity_code=opportunity_code,
    )
    initial = {"occurred_at": timezone.localtime().replace(second=0, microsecond=0)}
    form = ConversationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        Activity.objects.create(
            company=opportunity.company,
            opportunity=opportunity,
            activity_type=form.cleaned_data["activity_type"],
            occurred_at=form.cleaned_data["occurred_at"],
            details=form.cleaned_data["details"],
            follow_up_on=form.cleaned_data["follow_up_on"],
            completion_marker=Activity.CompletionMarker.COMPLETED,
        )
        return redirect(
            f"{opportunity.get_absolute_url()}?saved=conversation"
        )

    return render(
        request,
        "crm/form_page.html",
        {
            "opportunity": opportunity,
            "form": form,
            "eyebrow": "Customer contact",
            "heading": "Record conversation",
            "description": (
                "Log a completed call, email or meeting on this opportunity."
            ),
            "submit_label": "Record conversation",
        },
    )


def follow_up_create(request, opportunity_code):
    opportunity = get_object_or_404(
        Opportunity.objects.select_related("company"),
        opportunity_code=opportunity_code,
    )
    form = FollowUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Activity.objects.create(
            company=opportunity.company,
            opportunity=opportunity,
            activity_type=Activity.ActivityType.TASK,
            occurred_at=timezone.now(),
            details=form.cleaned_data["details"],
            follow_up_on=form.cleaned_data["follow_up_on"],
            completion_marker=Activity.CompletionMarker.PENDING,
        )
        return redirect(
            f"{opportunity.get_absolute_url()}?saved=follow-up"
        )

    return render(
        request,
        "crm/form_page.html",
        {
            "opportunity": opportunity,
            "form": form,
            "eyebrow": "Next action",
            "heading": "Schedule follow-up",
            "description": (
                "Create a pending task for this company and opportunity."
            ),
            "submit_label": "Schedule follow-up",
        },
    )


@require_POST
def handoff_create(request, opportunity_code):
    opportunity = get_object_or_404(
        Opportunity.objects.select_related(
            "company", "primary_contact", "fair_edition"
        ),
        opportunity_code=opportunity_code,
    )
    run_handoff(opportunity)
    return redirect(
        f"{opportunity.get_absolute_url()}?saved=handoff#technical-handoff"
    )


def handoff_run_detail(request, opportunity_code, run_id):
    handoff_run = get_object_or_404(
        HandoffRun.objects.select_related(
            "opportunity",
            "opportunity__company",
            "opportunity__fair_edition",
            "approved_follow_up",
        ),
        pk=run_id,
        opportunity__opportunity_code=opportunity_code,
    )
    return render(
        request,
        "crm/handoff_run_detail.html",
        {
            "opportunity": handoff_run.opportunity,
            "handoff_run": handoff_run,
            "comparison": compare_handoff_runs(handoff_run),
            "assistant_label": ASSISTANT_LABEL,
        },
    )


def handoff_follow_up_create(request, opportunity_code, run_id):
    handoff_run = get_object_or_404(
        HandoffRun.objects.select_related(
            "opportunity", "opportunity__company", "opportunity__fair_edition"
        ),
        pk=run_id,
        opportunity__opportunity_code=opportunity_code,
    )
    opportunity = handoff_run.opportunity
    existing_follow_up = Activity.objects.filter(
        source_handoff_run=handoff_run
    ).first()
    initial = {
        "details": handoff_run.next_action,
        "follow_up_on": timezone.localdate() + timedelta(days=1),
    }
    form = FollowUpForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        if existing_follow_up is not None:
            form.add_error(
                None,
                "This recommendation has already been approved as a follow-up.",
            )
        else:
            Activity.objects.create(
                company=opportunity.company,
                opportunity=opportunity,
                source_handoff_run=handoff_run,
                activity_type=Activity.ActivityType.TASK,
                occurred_at=timezone.now(),
                details=form.cleaned_data["details"],
                follow_up_on=form.cleaned_data["follow_up_on"],
                completion_marker=Activity.CompletionMarker.PENDING,
                author=opportunity.company.sales_rep,
            )
            return redirect(
                f"{opportunity.get_absolute_url()}?saved=assistant-follow-up"
                "#technical-handoff"
            )

    return render(
        request,
        "crm/handoff_follow_up.html",
        {
            "opportunity": opportunity,
            "handoff_run": handoff_run,
            "existing_follow_up": existing_follow_up,
            "form": form,
            "assistant_label": ASSISTANT_LABEL,
        },
    )


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()

    return JsonResponse({"status": "ok", "database": "connected"})
