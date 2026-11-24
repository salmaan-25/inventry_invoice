"""
Root URL configuration.

Public routes:
  GET  /api/health/   — liveness + database check (no auth)
  GET  /api/schema/   — OpenAPI schema download (public in dev)
  GET  /api/docs/     — Swagger UI (public in dev)

All other /api/* routes are registered by their app's urls.py.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django admin (kept for internal/superuser use and for managed models
    # such as Units and ExpenseCategories).
    path("admin/", admin.site.urls),

    # Health check — the only public application endpoint in Phase 0.
    path("api/", include("apps.common.urls")),

    # OpenAPI schema and Swagger UI.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # Phase 1: authentication and staff
    path("api/", include("apps.accounts.urls")),

    # Phase 2: business settings
    path("api/", include("apps.company.urls")),

    # Phase 3: customers
    path("api/", include("apps.customers.urls")),

    # Phase 4: products and inventory
    path("api/", include("apps.products.urls")),
    path("api/", include("apps.inventory.urls")),

    # Phase 5: invoices
    path("api/", include("apps.invoices.urls")),

    # Phase 6: payments and outstanding balances
    path("api/", include("apps.payments.urls")),

    # Phase 7: delivery challans
    path("api/", include("apps.delivery.urls")),

    # Phase 8: expenses and Excel export
    path("api/", include("apps.expenses.urls")),

    # Phase 9: other income and Excel export
    path("api/", include("apps.other_income.urls")),

    # Phase 10: dashboard
    path("api/", include("apps.dashboard.urls")),
]

# Serve uploaded media (company logo) from the development server. In
# production the web server or the configured storage backend serves media
# (decision D17).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
