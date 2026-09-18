from django.urls import path

from admission.api import views


app_name = "admission_api"

urlpatterns = [
    path("csrf/", views.csrf, name="csrf"),
    path("health/", views.health, name="health"),
    path("profiles/validate/", views.validate_profile, name="validate-profile"),
    path("profiles/", views.upsert_profile, name="upsert-profile"),
    path("profiles/<str:profile_key>/", views.get_profile, name="get-profile"),
    path("profiles/<str:profile_key>/diagnostic/", views.get_diagnostic, name="get-diagnostic"),
    path("profiles/<str:profile_key>/journey/", views.get_journey, name="get-journey"),
]
