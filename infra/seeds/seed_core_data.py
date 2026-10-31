"""Idempotently seed Civic Pulse core data.

Run from the repository root or from ``server/``::

    python infra/seeds/seed_core_data.py

Seeds:
* the five municipal departments used for grievance routing
* three demo accounts (citizen, officer, admin)
* one sample encrypted Citizen Vault for the demo citizen

Re-running the script is safe: departments are reconciled, while existing
users and vaults are left untouched.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make ``app`` importable regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_DIR = _REPO_ROOT / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import encrypt_pii_dict, hash_password  # noqa: E402
from app.domains.identity.models import (  # noqa: E402
    CitizenVault,
    Department,
    User,
)
from app.domains.identity.schemas import (  # noqa: E402
    PiiSecretPayload,
    PublicProfilePayload,
)

DEMO_PASSWORD = "CivicPulse@123"
CITIZEN_EMAIL = "citizen@civicpulse.gov.in"

DEPARTMENTS: list[dict] = [
    {
        "code": "PWD_ROADS",
        "name": "Public Works Department (Roads & Bridges)",
        "categories_handled": ["ROADS", "POTHOLES", "BRIDGES", "FOOTPATHS"],
        "sla_hours_critical": 4,
        "sla_hours_high": 24,
        "sla_hours_medium": 72,
        "sla_hours_low": 168,
        "contact_email": "pwd@civicpulse.gov.in",
    },
    {
        "code": "MUNICIPAL_WATER_BOARD",
        "name": "Municipal Water Board",
        "categories_handled": [
            "WATER_SUPPLY",
            "WATER_LEAKAGE",
            "SEWAGE",
            "DRAINAGE",
        ],
        "sla_hours_critical": 4,
        "sla_hours_high": 24,
        "sla_hours_medium": 72,
        "sla_hours_low": 168,
        "contact_email": "water@civicpulse.gov.in",
    },
    {
        "code": "ENV_POLLUTION_CONTROL",
        "name": "Environment & Pollution Control Board",
        "categories_handled": [
            "AIR_POLLUTION",
            "WATER_POLLUTION",
            "ILLEGAL_DUMPING",
            "NOISE_POLLUTION",
        ],
        "sla_hours_critical": 4,
        "sla_hours_high": 24,
        "sla_hours_medium": 72,
        "sla_hours_low": 168,
        "contact_email": "environment@civicpulse.gov.in",
    },
    {
        "code": "ELECTRICAL_GRID",
        "name": "State Electrical Grid",
        "categories_handled": [
            "POWER_OUTAGE",
            "TRANSFORMER",
            "STREETLIGHTS",
            "ILLEGAL_WIRING",
        ],
        "sla_hours_critical": 4,
        "sla_hours_high": 24,
        "sla_hours_medium": 72,
        "sla_hours_low": 168,
        "contact_email": "power@civicpulse.gov.in",
    },
    {
        "code": "SANITATION_WASTE",
        "name": "Sanitation & Waste Management",
        "categories_handled": [
            "GARBAGE",
            "SANITATION",
            "PUBLIC_TOILETS",
            "WASTE_BURNING",
        ],
        "sla_hours_critical": 4,
        "sla_hours_high": 24,
        "sla_hours_medium": 72,
        "sla_hours_low": 168,
        "contact_email": "sanitation@civicpulse.gov.in",
    },
]

USERS: list[dict] = [
    {
        "email": CITIZEN_EMAIL,
        "full_name": "Demo Citizen",
        "role": "CITIZEN",
        "preferred_language": "hi-IN",
        "department_code": None,
    },
    {
        "email": "officer@civicpulse.gov.in",
        "full_name": "Demo Officer",
        "role": "OFFICER",
        "preferred_language": "en-IN",
        "department_code": "PWD_ROADS",
    },
    {
        "email": "admin@civicpulse.gov.in",
        "full_name": "Demo Administrator",
        "role": "ADMIN",
        "preferred_language": "en-IN",
        "department_code": None,
    },
]


async def seed_core_data(session: AsyncSession) -> dict[str, int]:
    """Seed the database through *session* and return per-entity counts."""
    counts = {
        "departments_created": 0,
        "departments_updated": 0,
        "users_created": 0,
        "users_skipped": 0,
        "vaults_created": 0,
        "vaults_skipped": 0,
    }

    # ------------------------------------------------------------------ #
    # Departments — reconcile configuration on every run.
    # ------------------------------------------------------------------ #
    for department_data in DEPARTMENTS:
        existing = (
            await session.execute(
                select(Department).where(Department.code == department_data["code"])
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(Department(**department_data))
            counts["departments_created"] += 1
        else:
            for field, value in department_data.items():
                setattr(existing, field, value)
            counts["departments_updated"] += 1

    await session.flush()

    departments = {
        department.code: department
        for department in (await session.execute(select(Department))).scalars().all()
    }

    # ------------------------------------------------------------------ #
    # Demo users — insert missing accounts only.
    # ------------------------------------------------------------------ #
    for user_data in USERS:
        email = str(user_data["email"]).strip().lower()
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if existing is not None:
            counts["users_skipped"] += 1
            continue

        department = departments.get(user_data["department_code"])
        session.add(
            User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                full_name=user_data["full_name"],
                role=user_data["role"],
                preferred_language=user_data["preferred_language"],
                department_id=department.id if department is not None else None,
                is_active=True,
            )
        )
        counts["users_created"] += 1

    await session.flush()

    # ------------------------------------------------------------------ #
    # Sample encrypted vault for the demo citizen.
    # ------------------------------------------------------------------ #
    citizen = (
        await session.execute(select(User).where(User.email == CITIZEN_EMAIL))
    ).scalar_one_or_none()

    if citizen is None:
        counts["vaults_skipped"] += 1
    else:
        vault = (
            await session.execute(select(CitizenVault).where(CitizenVault.user_id == citizen.id))
        ).scalar_one_or_none()

        if vault is not None:
            counts["vaults_skipped"] += 1
        else:
            pii = PiiSecretPayload(
                national_id="MP-DEMO-1234-5678",
                dob="1990-01-01",
                bank_iban="IN00DEMO000000000000",
                phone_number="+91-9000000000",
                portal_pin="1234",
            )
            public_profile = PublicProfilePayload(
                state="Madhya Pradesh",
                annual_income=240000.0,
                occupation="Small Business Owner",
                category="OBC",
                is_msme=True,
                education_level="Graduate",
            )
            session.add(
                CitizenVault(
                    user_id=citizen.id,
                    encrypted_pii_blob=encrypt_pii_dict(pii.model_dump()),
                    public_profile=public_profile.model_dump(),
                    document_urls=[],
                )
            )
            counts["vaults_created"] += 1

    await session.commit()
    return counts


async def main() -> None:
    """Open a session, seed, and print a summary."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                counts = await seed_core_data(session)
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()

    print("Civic Pulse core seed complete.")
    print(f"  Departments created : {counts['departments_created']}")
    print(f"  Departments updated : {counts['departments_updated']}")
    print(f"  Users created       : {counts['users_created']}")
    print(f"  Users skipped       : {counts['users_skipped']}")
    print(f"  Vaults created      : {counts['vaults_created']}")
    print(f"  Vaults skipped      : {counts['vaults_skipped']}")
    print(f"  Demo password       : {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
