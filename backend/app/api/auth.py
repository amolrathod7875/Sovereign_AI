"""A1A authentication API endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.identity.principal import Principal, get_current_principal_dep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class AuthMeResponse(BaseModel):
    user_id: str
    organization_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    roles: list[str] = []
    authenticated: bool = False
    source: str = "local_development"


@router.get("/me", response_model=AuthMeResponse)
async def auth_me(
    principal: Principal = Depends(get_current_principal_dep),
):
    return AuthMeResponse(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        roles=principal.roles,
        authenticated=principal.authenticated,
        source=principal.source,
    )
