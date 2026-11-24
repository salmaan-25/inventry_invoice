"""Other income URL patterns — Phase 9."""

from django.urls import path

from apps.other_income.views import (
    IncomeCategoryListCreateView,
    OtherIncomeListCreateView,
    OtherIncomeDetailView,
    OtherIncomeExportView,
)

urlpatterns = [
    path(
        "income-categories/",
        IncomeCategoryListCreateView.as_view(),
        name="income-category-list-create",
    ),
    path(
        "other-income/",
        OtherIncomeListCreateView.as_view(),
        name="other-income-list-create",
    ),
    path(
        "other-income/<int:pk>/",
        OtherIncomeDetailView.as_view(),
        name="other-income-detail",
    ),
    path(
        "other-income/export/",
        OtherIncomeExportView.as_view(),
        name="other-income-export",
    ),
]