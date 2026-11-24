"""
accounts.throttles — Phase 1.

Login rate throttling: 5 attempts per minute per IP address.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttles login attempts.

    Rate: 5 per minute per IP address.
    Applied specifically to LoginView.
    """

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
