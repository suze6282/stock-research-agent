from alembic import context
from sqlalchemy import engine_from_config, pool

from stock_research_agent.config import Settings
from stock_research_agent.db.models import Security

config = context.config
injected_settings = config.attributes.get("settings")
if injected_settings is None:
    settings = Settings()
elif isinstance(injected_settings, Settings):
    settings = Settings.model_validate(injected_settings.model_dump(warnings=False))
else:
    raise RuntimeError("Alembic settings must use the application Settings contract")

if settings.database_url is None:
    raise RuntimeError("DATABASE_URL is required to run migrations")

# Alembic stores options through ConfigParser, where percent signs interpolate.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Security.metadata


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    reflected: bool,
    _compare_to: object | None,
) -> bool:
    """Keep the legacy migration-only schema_meta table outside ORM autogeneration."""
    return not (type_ == "table" and reflected and name == "schema_meta")


def run_migrations_offline() -> None:
    """Render PostgreSQL migration SQL without creating an Engine."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through a short-lived, explicitly created Engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
