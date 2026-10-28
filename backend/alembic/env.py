"""Alembic environment for async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from app.core.config import get_settings
from app.core.database.base import Base
from app.core.postgres_provider import resolve_engine_kwargs

# Import models so metadata is populated
from app.modules.tenants import models as _tenants  # noqa: F401
from app.modules.users import models as _users  # noqa: F401
from app.modules.roles import models as _roles  # noqa: F401
from app.modules.reference import models as _reference  # noqa: F401
from app.modules.system_config import models as _system_config  # noqa: F401
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.jobs import models as _jobs  # noqa: F401
from app.modules.customers import models as _customers  # noqa: F401
from app.modules.intermediaries import models as _intermediaries  # noqa: F401
from app.modules.products import models as _products  # noqa: F401
from app.modules.insurer_catalog import models as _insurer_catalog  # noqa: F401
from app.modules.proposals import models as _proposals  # noqa: F401
from app.modules.policies import models as _policies  # noqa: F401
from app.modules.payments import models as _payments  # noqa: F401
from app.modules.wallets import models as _wallets  # noqa: F401
from app.modules.certificates import models as _certificates  # noqa: F401
from app.modules.certificates import access_models as _certificate_accesses  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.reports import models as _reports  # noqa: F401
from app.modules.claims import models as _claims  # noqa: F401
from app.modules.files import models as _stored_files  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_settings = get_settings()
_migration_url, _migration_engine_kwargs, _ = resolve_engine_kwargs(
    database_url=_settings.database_url,
    provider=_settings.resolved_db_provider,
    ssl_mode=_settings.db_ssl_mode,
    pool_size=1,
    max_overflow=0,
    pool_timeout=30,
    command_timeout=120,
    force_null_pool=True,
)
# ConfigParser treats % as interpolation — escape URL-encoded passwords (e.g. %40).
config.set_main_option("sqlalchemy.url", _migration_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_migration_url, **_migration_engine_kwargs)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
