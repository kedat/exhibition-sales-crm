from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Prefetch, Subquery
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from crm.models import Activity, Company, Contact, Opportunity


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

    return render(
        request,
        "crm/home.html",
        {
            "today": today,
            "overdue": overdue[:FOLLOW_UP_PREVIEW_LIMIT],
            "overdue_count": overdue.count(),
            "due_today": due_today[:FOLLOW_UP_PREVIEW_LIMIT],
            "due_today_count": due_today.count(),
            "upcoming": upcoming[:FOLLOW_UP_PREVIEW_LIMIT],
            "upcoming_count": upcoming.count(),
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
    activities = opportunity.activities.select_related("company").order_by(
        "-occurred_at"
    )

    return render(
        request,
        "crm/opportunity_detail.html",
        {"opportunity": opportunity, "activities": activities},
    )


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()

    return JsonResponse({"status": "ok", "database": "connected"})
