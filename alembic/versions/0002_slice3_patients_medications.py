"""slice3: patient_profiles constraints, indexes for patients/medications

Revision ID: 0002_slice3
Revises: 0001_baseline
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_slice3"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    op.create_check_constraint(
        "ck_patient_profiles_sex",
        "patient_profiles",
        "sex IS NULL OR sex IN ('MALE','FEMALE','OTHER')",
    )
    op.create_check_constraint(
        "ck_patient_profiles_consent",
        "patient_profiles",
        "privacy_consent_status IS NULL OR privacy_consent_status IN ('PENDING','GRANTED','REVOKED')",
    )
    op.create_check_constraint(
        "ck_patient_profiles_name_not_blank",
        "patient_profiles",
        "length(btrim(name)) > 0",
    )
    op.create_check_constraint(
        "ck_patient_profiles_dob_sane",
        "patient_profiles",
        "dob IS NULL OR (dob > DATE '1900-01-01' AND dob <= CURRENT_DATE)",
    )
    op.create_check_constraint(
        "ck_patient_profiles_tz_not_blank",
        "patient_profiles",
        "length(btrim(timezone)) > 0",
    )

    op.execute(
        "CREATE INDEX idx_patient_profiles_name_trgm ON patient_profiles "
        "USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_users_phone_trgm ON users USING gin (phone gin_trgm_ops)"
    )

    # ── medications ──
    op.create_check_constraint(
        "ck_medications_name_not_blank",
        "medications",
        "length(btrim(name)) > 0",
    )
    op.create_check_constraint(
        "ck_medications_source_not_blank",
        "medications",
        "length(btrim(source_name)) > 0",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_medications_source_record ON medications "
        "(source_name, source_record_key) WHERE source_record_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_medications_active_name ON medications (name, id) "
        "WHERE is_active"
    )
    op.execute(
        "CREATE INDEX idx_medications_name_trgm ON medications USING gin (name gin_trgm_ops)"
    )

    # ── users: close role/status enum gap (6 rows in dev DB, direct ADD is instant) ──
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('PATIENT','DOCTOR','ADMIN','CAREGIVER')",
    )
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('ACTIVE','INACTIVE','BLOCKED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")

    op.execute("DROP INDEX IF EXISTS idx_medications_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_medications_active_name")
    op.execute("DROP INDEX IF EXISTS uq_medications_source_record")
    op.drop_constraint("ck_medications_source_not_blank", "medications", type_="check")
    op.drop_constraint("ck_medications_name_not_blank", "medications", type_="check")

    op.execute("DROP INDEX IF EXISTS idx_users_phone_trgm")
    op.execute("DROP INDEX IF EXISTS idx_patient_profiles_name_trgm")

    op.drop_constraint("ck_patient_profiles_tz_not_blank", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_dob_sane", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_name_not_blank", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_consent", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_sex", "patient_profiles", type_="check")
