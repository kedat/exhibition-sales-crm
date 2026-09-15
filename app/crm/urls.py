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
    path("health/", views.health, name="health"),
]
