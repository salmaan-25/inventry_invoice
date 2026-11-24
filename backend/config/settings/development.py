"""
Development settings — extends base.py.

Do NOT use in production. Set DJANGO_SETTINGS_MODULE=config.settings.development.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

# In development the OpenAPI schema and docs are public (no login needed).
# Production overrides these to require authentication or disables the docs page.
SPECTACULAR_SETTINGS["SERVE_PUBLIC"] = True  # noqa: F405

# Allow all hosts in development for convenience. Add proper ALLOWED_HOSTS
# in .env for a shared dev server.
ALLOWED_HOSTS = ["*"]  # noqa: F405

# Show all SQL in the shell when DEBUG=True — optional, helpful.
# Uncomment to activate:
# LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
#     "handlers": ["console"],
#     "level": "DEBUG",
#     "propagate": False,
# }
