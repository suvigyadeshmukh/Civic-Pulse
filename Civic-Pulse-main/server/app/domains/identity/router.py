"""Identity & authentication HTTP routes.

Mounted by ``app.main`` at ``/api/v1``. Every success response uses the shared
:class:`ApiEnvelope`; errors use the shared exception envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUserContext, get_current_user, get_db
from app.core.pagination import ApiEnvelope
from app.domains.identity.schemas import (
    AuthResponseDto,
    CitizenVaultResponseDto,
    CitizenVaultUpsertRequest,
    DepartmentDto,
    LoginRequest,
    RegisterRequest,
    UserDto,
)
from app.domains.identity.service import IdentityService

router = APIRouter()
_service = IdentityService()


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiEnvelope[AuthResponseDto],
    summary="Register a new account",
)
async def register_user(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[AuthResponseDto]:
    return ApiEnvelope(data=await _service.register_user(db, payload))


@router.post(
    "/auth/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiEnvelope[AuthResponseDto],
    summary="Authenticate with email and password",
)
async def login_user(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[AuthResponseDto]:
    return ApiEnvelope(data=await _service.authenticate_user(db, payload))


@router.get(
    "/auth/me",
    status_code=status.HTTP_200_OK,
    response_model=ApiEnvelope[UserDto],
    summary="Return the authenticated user's profile",
)
async def get_me(
    current_user: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[UserDto]:
    return ApiEnvelope(data=await _service.get_user_by_id(db, current_user.id))


@router.put(
    "/profile/vault",
    status_code=status.HTTP_200_OK,
    response_model=ApiEnvelope[CitizenVaultResponseDto],
    summary="Create or replace the encrypted Citizen Vault",
)
async def upsert_vault(
    payload: CitizenVaultUpsertRequest,
    current_user: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[CitizenVaultResponseDto]:
    return ApiEnvelope(data=await _service.upsert_citizen_vault(db, current_user.id, payload))


@router.get(
    "/profile/vault",
    status_code=status.HTTP_200_OK,
    response_model=ApiEnvelope[CitizenVaultResponseDto],
    summary="Return the decrypted Citizen Vault",
)
async def get_vault(
    current_user: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[CitizenVaultResponseDto]:
    return ApiEnvelope(data=await _service.get_decrypted_vault(db, current_user.id))


@router.get(
    "/departments",
    status_code=status.HTTP_200_OK,
    response_model=ApiEnvelope[list[DepartmentDto]],
    summary="List municipal departments",
)
async def list_departments(
    db: AsyncSession = Depends(get_db),
) -> ApiEnvelope[list[DepartmentDto]]:
    return ApiEnvelope(data=await _service.list_departments(db))
