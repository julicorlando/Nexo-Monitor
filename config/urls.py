from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from monitor import views
urlpatterns = [path("devices/<int:device_id>/history/", views.history), path("collectors/<int:collector_id>/import/", views.import_inventory), path("", views.dashboard), path("admin/", admin.site.urls), path("login/", auth.LoginView.as_view(template_name="login.html")), path("logout/", auth.LogoutView.as_view()), path("health/", views.health), path("api/collector/config/", views.collector_config), path("api/collector/results/", views.ingest)]
