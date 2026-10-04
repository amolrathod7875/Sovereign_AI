"""Resolve an OIDC-validated identity into an authenticated Principal.

Maps issuer+subject -> users.external_subject -> active OrganizationMembership -> Principal.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.identity.principal import Principal
from app.storage.postgres import (
    User,
    OrganizationMembership,
)

logger = logging.getLogger(__name__)


def _canonical_subject_key(issuer: str, subject: str) -> str:
    return f"{issuer}|{subject}"


class PrincipalResolutionError(Exception):
    pass


class PrincipalResolver:
    def __init__(self, session, issuer: str, subject: str) -> None:
        self.session = session
        self.issuer = issuer
        self.subject = subject
        self.canonical_key = _canonical_subject_key(issuer, subject)
        self.requested_org_id: Optional[str] = None

    async def resolve(self) -> Principal:
        user = await self._find_user()
        if user is None:
            raise PrincipalResolutionError("Unknown user")
        if not user.active:
            raise PrincipalResolutionError("Inactive user")

        memberships = await self._find_active_memberships(user.id)
        if not memberships:
            raise PrincipalResolutionError("No active organization memberships")

        org_id = self._select_organization(memberships)
        membership = next(m for m in memberships if m.organization_id == org_id)
        roles = [membership.role]

        return Principal(
            user_id=user.id,
            organization_id=org_id,
            roles=roles,
            authenticated=True,
            source="oidc",
        )

    async def _find_user(self):
        stmt = select(User).where(User.external_subject == self.canonical_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_active_memberships(self, user_id: str):
        stmt = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _select_organization(self, memberships: list) -> str:
        org_ids = list({m.organization_id for m in memberships})

        if self.requested_org_id:
            if self.requested_org_id not in org_ids:
                raise PrincipalResolutionError("Organization not found in user memberships")
            return self.requested_org_id

        if len(org_ids) == 1:
            return org_ids[0]

        header_name = settings.AUTH_ORGANIZATION_HEADER.strip()
        raise PrincipalResolutionError(
            f"Multiple active memberships found; specify organization via {header_name}"
        )
