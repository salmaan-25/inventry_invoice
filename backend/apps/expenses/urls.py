"""Expense URL patterns — Phase 8."""

from django.urls import path

from apps.expenses.views import (
    ExpenseCategoryListCreateView,
    ExpenseListCreateView,
    ExpenseDetailView,
    ExpenseExportView,
)

urlpatterns = [
    path(
        "expense-categories/",
        ExpenseCategoryListCreateView.as_view(),
        name="expense-category-list-create",
    ),
    path(
        "expenses/",
        ExpenseListCreateView.as_view(),
        name="expense-list-create",
    ),
    path(
        "expenses/<int:pk>/",
        ExpenseDetailView.as_view(),
        name="expense-detail",
    ),
    path(
        "expenses/export/",
        ExpenseExportView.as_view(),
        name="expense-export",
    ),
]