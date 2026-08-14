import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from src.core.config import get_settings
from src.core.database import Base

# Import every module that declares ORM models. A class only registers itself
# on Base.metadata when its module is imported, so without these the metadata
# is empty and autogenerate reads that as "no table should exist" — it emits a
# revision that DROPs the entire schema. `alembic upgrade head` was unaffected
# (it replays existing revisions and never consults metadata), which is why
# this stayed hidden. Keep this list in step with src/modules/*/models.py;
# dashboard has no models.py of its own, it only reads other slices' tables.
from src.modules.adherence import models as _adherence_models  # noqa: F401,E402
from src.modules.admin import models as _admin_models  # noqa: F401,E402
from src.modules.agents import models as _agents_models  # noqa: F401,E402
from src.modules.auth import models as _auth_models  # noqa: F401,E402
from src.modules.patients import models as _patients_models  # noqa: F401,E402
from src.modules.prescriptions import models as _prescriptions_models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate to the objects the ORM actually declares.

    This database is provisioned by docs/database_v1_init.sql and then advanced
    by hand-written revisions; the ORM covers only the subset of tables the
    application code reads. Autogenerate compares metadata against the live
    schema and treats anything it cannot find in metadata as deleted, so
    without this filter it proposes DROP TABLE for the eight tables no module
    ever modelled (ocr_jobs, rag_queries, rag_citations, knowledge_documents,
    knowledge_chunks, conversations, messages, notification_deliveries) plus
    DROP INDEX for every index init.sql created that no model repeats.

    `reflected and compare_to is None` is precisely "exists in the database,
    absent from metadata" — the destructive direction. Additions still come
    through, so a genuinely new model or column is still detected.
    """
    if reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
