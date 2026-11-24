"""
Health endpoint — GET /api/health/

Public. Returns HTTP 200 when the application is up and the database is
reachable. Returns HTTP 503 when the database check fails so that a load
balancer or container orchestrator can detect an unhealthy instance.
"""

import logging

from django.db import connection, DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """
    Liveness and database readiness check.

    No authentication required.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # skip session / CSRF overhead

    def get(self, request, *args, **kwargs):
        db_ok = True
        db_error = None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError as exc:
            db_ok = False
            db_error = str(exc)
            logger.error("Health check: database unreachable: %s", exc)

        status_text = "ok" if db_ok else "error"
        body = {
            "status": status_text,
            "database": "ok" if db_ok else "error",
        }
        if db_error:
            body["detail"] = db_error

        http_status = 200 if db_ok else 503
        return Response(body, status=http_status)
