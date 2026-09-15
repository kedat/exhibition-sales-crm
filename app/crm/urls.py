from django.urls import path

from . import views


app_name = "crm"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path(
        "companies/<str:company_code>/",
        views.company_detail,
        name="company-detail",
    ),
    path(
        "opportunities/<str:opportunity_code>/",
        views.opportunity_detail,
        name="opportunity-detail",
    ),
    path(
        "opportunities/<str:opportunity_code>/edit/",
        views.opportunity_edit,
        name="opportunity-edit",
    ),
    path(
        "opportunities/<str:opportunity_code>/conversations/new/",
        views.conversation_create,
        name="conversation-create",
    ),
    path(
        "opportunities/<str:opportunity_code>/follow-ups/new/",
        views.follow_up_create,
        name="follow-up-create",
    ),
    path("health/", views.health, name="health"),
]
