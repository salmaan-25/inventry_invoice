"""
Production settings — extends base.py.

Set DJANGO_SETTINGS_MODULE=config.settings.production and supply all required
environment variables via the deployment platform's secret manager or .env file
(never commit the actual .env to version control).
"""

from .base import *  # noqa: F401, F403

DEBUG = False  # noqa: F405

SECRET_KEY = os.environ["SECRET_KEY"]

# Production security headers.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Session and CSRF cookies must be sent over HTTPS only in production.
SESSION_COOKIE_SECURE = True  # noqa: F405
CSRF_COOKIE_SECURE = True     # noqa: F405

# HSTS — enable once HTTPS is confirmed.
# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# API docs are disabled in production. Remove this override to re-enable
# with authentication once the deployment is stable.
SPECTACULAR_SETTINGS["SERVE_PUBLIC"] = False  # noqa: F405
