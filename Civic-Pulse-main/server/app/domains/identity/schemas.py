"""Identity domain Pydantic schemas (request / response contracts)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

UserRole = Literal["CITIZEN", "BUSINESS_OWNER", "OFFICER", "ADMIN"]


class RegisterRequest(BaseModel):
    """Payload for creating a new Civic Pulse account."""

    email: str
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole = "CITIZEN"
    preferred_language: str = "hi-IN"
    department_code: str | None = None


class LoginRequest(BaseModel):
    """Email / password credentials."""

    email: str
    password: str


class UserDto(BaseModel):
    """Public, non-sensitive representation of an account."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    preferred_language: str
    department_id: UUID | None = None


class AuthResponseDto(BaseModel):
    """JWT plus the authenticated user's profile."""

    access_token: str
    token_type: str = "bearer"
    user: UserDto


class PiiSecretPayload(BaseModel):
    """Sensitive fields that are only ever stored inside the encrypted blob."""

    national_id: str = ""
    dob: str = ""
    bank_iban: str = ""
    phone_number: str = ""
    portal_pin: str = ""


class PublicProfilePayload(BaseModel):
    """Non-sensitive demographic data used for eligibility matching."""

    state: str = "Madhya Pradesh"
    annual_income: float = 0.0
    occupation: str = ""
    category: str = "GENERAL"
    is_msme: bool = False
    education_level: str = ""


class CitizenVaultUpsertRequest(BaseModel):
    """Create / replace a citizen vault."""

    pii_secret: PiiSecretPayload
    public_profile: PublicProfilePayload
    document_urls: list[str] = Field(default_factory=list)


class CitizenVaultResponseDto(BaseModel):
    """Decrypted vault representation returned to the owning citizen."""

    vault_id: UUID
    user_id: UUID
    pii_secret: PiiSecretPayload
    public_profile: PublicProfilePayload
    document_urls: list[str]
    updated_at: datetime


class DepartmentDto(BaseModel):
    """Department configuration exposed to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    categories_handled: list[str]
    sla_hours_critical: int
    sla_hours_high: int
    sla_hours_medium: int
    sla_hours_low: int
    contact_email: str
