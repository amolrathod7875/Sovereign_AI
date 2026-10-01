from dataclasses import dataclass, field
from typing import List

from app.config import settings


@dataclass
class Principal:
    """M1 development principal abstraction.

    Future Phase A authentication will replace ONLY the resolver that produces
    this object. All history APIs obtain identity through get_current_principal()
    or an equivalent dependency — never from hard-coded user IDs.
    """

    user_id: str
    organization_id: str
    roles: List[str] = field(default_factory=list)
    authenticated: bool = False
    source: str = "local_development"


def get_current_principal() -> Principal:
    """Return the current request principal.

    M1 local development: returns a deterministic dev principal sourced from
    app.config.settings. Real authentication is NOT implemented yet.
    """
    return Principal(
        user_id=settings.SOVEREIGN_DEV_USER_ID,
        organization_id=settings.SOVEREIGN_DEV_ORGANIZATION_ID,
        roles=["owner"],
        authenticated=False,
        source="local_development",
    )
