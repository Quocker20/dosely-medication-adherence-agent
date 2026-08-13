"""slice3: patient_profiles constraints, indexes for patients/medications

Revision ID: 0002_slice3
Revises: 0001_baseline
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_slice3"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # NOT VALID skips the full-table scan, so ADD CONSTRAINT only takes a brief
    # AccessExclusiveLock instead of holding it for the scan. VALIDATE CONSTRAINT
    # then does the scan under ShareUpdateExclusiveLock, which blocks neither
    # reads nor writes.
    op.execute(
        "ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_sex "
        "CHECK (sex IS NULL OR sex IN ('MALE','FEMALE','OTHER')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_consent "
        "CHECK (privacy_consent_status IS NULL OR privacy_consent_status IN "
        "('PENDING','GRANTED','REVOKED')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_name_not_blank "
        "CHECK (length(btrim(name)) > 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_dob_sane "
        "CHECK (dob IS NULL OR (dob > DATE '1900-01-01' AND dob <= CURRENT_DATE)) NOT VALID"
    )
    op.execute(
        "ALTER TABLE patient_profiles ADD CONSTRAINT ck_patient_profiles_tz_not_blank "
        "CHECK (length(btrim(timezone)) > 0) NOT VALID"
    )

    # ── medications ──
    op.execute(
        "ALTER TABLE medications ADD CONSTRAINT ck_medications_name_not_blank "
        "CHECK (length(btrim(name)) > 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE medications ADD CONSTRAINT ck_medications_source_not_blank "
        "CHECK (length(btrim(source_name)) > 0) NOT VALID"
    )

    # ── users: close role/status enum gap (6 rows in dev DB, direct ADD is instant) ──
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role "
        "CHECK (role IN ('PATIENT','DOCTOR','ADMIN','CAREGIVER')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_status "
        "CHECK (status IN ('ACTIVE','INACTIVE','BLOCKED')) NOT VALID"
    )

    op.execute("ALTER TABLE patient_profiles VALIDATE CONSTRAINT ck_patient_profiles_sex")
    op.execute("ALTER TABLE patient_profiles VALIDATE CONSTRAINT ck_patient_profiles_consent")
    op.execute("ALTER TABLE patient_profiles VALIDATE CONSTRAINT ck_patient_profiles_name_not_blank")
    op.execute("ALTER TABLE patient_profiles VALIDATE CONSTRAINT ck_patient_profiles_dob_sane")
    op.execute("ALTER TABLE patient_profiles VALIDATE CONSTRAINT ck_patient_profiles_tz_not_blank")
    op.execute("ALTER TABLE medications VALIDATE CONSTRAINT ck_medications_name_not_blank")
    op.execute("ALTER TABLE medications VALIDATE CONSTRAINT ck_medications_source_not_blank")
    op.execute("ALTER TABLE users VALIDATE CONSTRAINT ck_users_role")
    op.execute("ALTER TABLE users VALIDATE CONSTRAINT ck_users_status")

    # CONCURRENTLY takes ShareLock instead of the plain-CREATE-INDEX default of
    # ShareLock-blocking-writes-for-the-whole-build; it cannot run inside a
    # transaction, hence the autocommit_block.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_patient_profiles_name_trgm ON patient_profiles "
            "USING gin (name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_users_phone_trgm ON users USING gin (phone gin_trgm_ops)"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_medications_source_record ON medications "
            "(source_name, source_record_key) WHERE source_record_key IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_medications_active_name ON medications (name, id) "
            "WHERE is_active"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_medications_name_trgm ON medications USING gin (name gin_trgm_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_medications_name_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_medications_active_name")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_medications_source_record")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_users_phone_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_patient_profiles_name_trgm")

    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")

    op.drop_constraint("ck_medications_source_not_blank", "medications", type_="check")
    op.drop_constraint("ck_medications_name_not_blank", "medications", type_="check")

    op.drop_constraint("ck_patient_profiles_tz_not_blank", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_dob_sane", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_name_not_blank", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_consent", "patient_profiles", type_="check")
    op.drop_constraint("ck_patient_profiles_sex", "patient_profiles", type_="check")
