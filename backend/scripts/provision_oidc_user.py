"""Provision an OIDC user for Sovereign AI.

Maps an OIDC issuer+subject to a Sovereign User and organization membership.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.storage.postgres import async_session, User, Organization, OrganizationMembership

logger = logging.getLogger(__name__)


def _canonical_subject_key(issuer: str, subject: str) -> str:
    return f"{issuer}|{subject}"


async def _get_session() -> AsyncSession:
    session = async_session()
    if session is None:
        raise RuntimeError("Database unavailable")
    return session


async def provision(
    issuer: str,
    subject: str,
    organization_id: str,
    email: str | None = None,
    display_name: str | None = None,
    role: str = "member",
) -> None:
    canonical_key = _canonical_subject_key(issuer, subject)

    session = await _get_session()
    try:
        org = await session.get(Organization, organization_id)
        if not org:
            raise ValueError(f"Organization not found: {organization_id}")

        existing_user = None
        stmt = select(User).where(User.external_subject == canonical_key)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            if existing_user.email and email and existing_user.email != email:
                raise ValueError(
                    f"Subject already bound to user {existing_user.id} with email {existing_user.email}"
                )
            user = existing_user
            if display_name:
                user.display_name = display_name
            if email:
                user.email = email
        else:
            email_stmt = select(User).where(User.email == email)
            if email:
                email_result = await session.execute(email_stmt)
                if email_result.scalar_one_or_none():
                    raise ValueError(f"Email already in use: {email}")

            user = User(
                display_name=display_name or subject,
                email=email,
                external_subject=canonical_key,
            )
            session.add(user)
            await session.flush()

        membership_stmt = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user.id,
            )
        )
        membership_result = await session.execute(membership_stmt)
        existing_membership = membership_result.scalar_one_or_none()

        if existing_membership:
            if existing_membership.status != "active":
                existing_membership.status = "active"
            existing_membership.role = role
        else:
            membership = OrganizationMembership(
                organization_id=organization_id,
                user_id=user.id,
                role=role,
                status="active",
            )
            session.add(membership)

        await session.commit()
        print(f"Provisioned OIDC user: {user.id}")
        print(f"  external_subject: {canonical_key}")
        print(f"  organization_id: {organization_id}")
        print(f"  role: {role}")
    finally:
        await session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision an OIDC user")
    parser.add_argument("--issuer", required=True, help="OIDC issuer URL")
    parser.add_argument("--subject", required=True, help="OIDC subject (sub)")
    parser.add_argument("--organization-id", required=True, help="Organization ID")
    parser.add_argument("--email", default=None, help="User email")
    parser.add_argument("--display-name", default=None, help="Display name")
    parser.add_argument("--role", default="member", help="Membership role")
    args = parser.parse_args()

    asyncio.run(provision(
        issuer=args.issuer,
        subject=args.subject,
        organization_id=args.organization_id,
        email=args.email,
        display_name=args.display_name,
        role=args.role,
    ))


if __name__ == "__main__":
    main()
