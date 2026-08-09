"""Create issuer and listed-security master data tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_create_security_master"
down_revision: str | Sequence[str] | None = "0001_create_schema_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CHECK = "status IN ('ACTIVE', 'INACTIVE', 'UNKNOWN')"
_IDENTIFIER_SCHEME_CHECK = "scheme ~ '^[A-Z][A-Z0-9_]{1,63}$'"


def _identity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "markets",
        *_identity_columns(),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("default_currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_markets"),
        sa.UniqueConstraint("code", name="uq_markets_code"),
        sa.CheckConstraint("code ~ '^[A-Z][A-Z0-9_]{0,31}$'", name="ck_markets_code_format"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_markets_name_length"),
        sa.CheckConstraint("country_code IN ('CN', 'US')", name="ck_markets_country_code"),
        sa.CheckConstraint(
            "default_currency_code IN ('CNY', 'USD')", name="ck_markets_currency_code"
        ),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_markets_status"),
    )
    op.create_table(
        "exchanges",
        *_identity_columns(),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mic", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("short_name", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("default_currency_code", sa.String(length=3), nullable=False),
        sa.Column("calendar_code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_exchanges"),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name="fk_exchanges_market_id_markets",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("mic", name="uq_exchanges_mic"),
        sa.CheckConstraint("mic IN ('XNAS', 'XSHG')", name="ck_exchanges_mic"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_exchanges_name_length"),
        sa.CheckConstraint(
            "length(short_name) BETWEEN 1 AND 64", name="ck_exchanges_short_name_length"
        ),
        sa.CheckConstraint("country_code IN ('CN', 'US')", name="ck_exchanges_country_code"),
        sa.CheckConstraint(
            "length(timezone) BETWEEN 1 AND 64", name="ck_exchanges_timezone_length"
        ),
        sa.CheckConstraint(
            "default_currency_code IN ('CNY', 'USD')", name="ck_exchanges_currency_code"
        ),
        sa.CheckConstraint(
            "calendar_code IS NULL OR length(calendar_code) BETWEEN 1 AND 64",
            name="ck_exchanges_calendar_code_length",
        ),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_exchanges_status"),
    )
    op.create_table(
        "exchange_aliases",
        *_identity_columns(),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("normalized_alias", sa.String(length=32), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_exchange_aliases"),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name="fk_exchange_aliases_exchange_id_exchanges",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("normalized_alias", name="uq_exchange_aliases_normalized_alias"),
        sa.CheckConstraint(
            "length(alias) BETWEEN 1 AND 64", name="ck_exchange_aliases_alias_length"
        ),
        sa.CheckConstraint(
            "normalized_alias ~ '^[A-Z0-9]{1,32}$'",
            name="ck_exchange_aliases_normalized_alias_format",
        ),
        sa.CheckConstraint(
            "alias_type IN ('MIC', 'SUFFIX', 'SHORT_NAME', 'DISPLAY_NAME')",
            name="ck_exchange_aliases_alias_type",
        ),
    )
    op.create_index("ix_exchange_aliases_exchange_id", "exchange_aliases", ["exchange_id"])

    op.create_table(
        "issuers",
        *_identity_columns(),
        sa.Column("legal_name", sa.String(length=256), nullable=False),
        sa.Column("normalized_legal_name", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("normalized_display_name", sa.String(length=256), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("issuer_status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_issuers"),
        sa.CheckConstraint(
            "length(legal_name) BETWEEN 1 AND 256", name="ck_issuers_legal_name_length"
        ),
        sa.CheckConstraint(
            "length(normalized_legal_name) BETWEEN 1 AND 256",
            name="ck_issuers_normalized_legal_name_length",
        ),
        sa.CheckConstraint(
            "length(display_name) BETWEEN 1 AND 256", name="ck_issuers_display_name_length"
        ),
        sa.CheckConstraint(
            "length(normalized_display_name) BETWEEN 1 AND 256",
            name="ck_issuers_normalized_display_name_length",
        ),
        sa.CheckConstraint("country_code IN ('CN', 'US')", name="ck_issuers_country_code"),
        sa.CheckConstraint(
            "issuer_status IN ('ACTIVE', 'INACTIVE', 'UNKNOWN')", name="ck_issuers_status"
        ),
    )
    op.create_index("ix_issuers_normalized_legal_name", "issuers", ["normalized_legal_name"])
    op.create_index("ix_issuers_normalized_display_name", "issuers", ["normalized_display_name"])
    op.create_index(
        "ix_issuers_normalized_legal_name_prefix",
        "issuers",
        ["normalized_legal_name"],
        postgresql_ops={"normalized_legal_name": "text_pattern_ops"},
    )
    op.create_index(
        "ix_issuers_normalized_display_name_prefix",
        "issuers",
        ["normalized_display_name"],
        postgresql_ops={"normalized_display_name": "text_pattern_ops"},
    )

    op.create_table(
        "issuer_identifiers",
        *_identity_columns(),
        sa.Column("issuer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_issuer_identifiers"),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuers.id"],
            name="fk_issuer_identifiers_issuer_id_issuers",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "scheme",
            "normalized_value",
            name="uq_issuer_identifiers_scheme_normalized_value",
        ),
        sa.CheckConstraint(_IDENTIFIER_SCHEME_CHECK, name="ck_issuer_identifiers_scheme_format"),
        sa.CheckConstraint(
            "length(value) BETWEEN 1 AND 256", name="ck_issuer_identifiers_value_length"
        ),
        sa.CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 256",
            name="ck_issuer_identifiers_normalized_value_length",
        ),
        sa.CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128",
            name="ck_issuer_identifiers_source_name_length",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_issuer_identifiers_validity",
        ),
    )
    op.create_index("ix_issuer_identifiers_issuer_id", "issuer_identifiers", ["issuer_id"])

    op.create_table(
        "securities",
        *_identity_columns(),
        sa.Column("issuer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("normalized_symbol", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("security_type", sa.String(length=32), nullable=False),
        sa.Column("share_class", sa.String(length=64), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("listing_status", sa.String(length=16), nullable=False),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("delisting_date", sa.Date(), nullable=True),
        sa.Column("is_primary_listing", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_securities"),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["issuers.id"],
            name="fk_securities_issuer_id_issuers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name="fk_securities_exchange_id_exchanges",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "exchange_id", "normalized_symbol", name="uq_securities_exchange_symbol"
        ),
        sa.CheckConstraint("length(symbol) BETWEEN 1 AND 64", name="ck_securities_symbol_length"),
        sa.CheckConstraint(
            "normalized_symbol ~ '^[A-Z0-9]+([.:-][A-Z0-9]+)*$'",
            name="ck_securities_normalized_symbol_format",
        ),
        sa.CheckConstraint(
            "length(display_name) BETWEEN 1 AND 256", name="ck_securities_display_name_length"
        ),
        sa.CheckConstraint("security_type IN ('COMMON_STOCK')", name="ck_securities_security_type"),
        sa.CheckConstraint(
            "share_class IS NULL OR length(share_class) BETWEEN 1 AND 64",
            name="ck_securities_share_class_length",
        ),
        sa.CheckConstraint("currency_code IN ('CNY', 'USD')", name="ck_securities_currency_code"),
        sa.CheckConstraint(
            "listing_status IN ('ACTIVE', 'SUSPENDED', 'DELISTED', 'UNKNOWN')",
            name="ck_securities_listing_status",
        ),
        sa.CheckConstraint(
            "delisting_date IS NULL OR listing_date IS NULL OR delisting_date >= listing_date",
            name="ck_securities_listing_dates",
        ),
    )
    op.create_index("ix_securities_issuer_id", "securities", ["issuer_id"])
    op.create_index("ix_securities_normalized_symbol", "securities", ["normalized_symbol"])
    op.create_index(
        "ix_securities_normalized_symbol_prefix",
        "securities",
        ["normalized_symbol"],
        postgresql_ops={"normalized_symbol": "text_pattern_ops"},
    )

    op.create_table(
        "security_identifiers",
        *_identity_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=False),
        sa.Column("normalized_value", sa.String(length=256), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_security_identifiers"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_security_identifiers_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "scheme",
            "normalized_value",
            name="uq_security_identifiers_scheme_normalized_value",
        ),
        sa.CheckConstraint(_IDENTIFIER_SCHEME_CHECK, name="ck_security_identifiers_scheme_format"),
        sa.CheckConstraint(
            "length(value) BETWEEN 1 AND 256", name="ck_security_identifiers_value_length"
        ),
        sa.CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 256",
            name="ck_security_identifiers_normalized_value_length",
        ),
        sa.CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128",
            name="ck_security_identifiers_source_name_length",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_security_identifiers_validity",
        ),
    )
    op.create_index("ix_security_identifiers_security_id", "security_identifiers", ["security_id"])

    op.create_table(
        "security_aliases",
        *_identity_columns(),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=256), nullable=False),
        sa.Column("normalized_alias", sa.String(length=256), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_security_aliases"),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_security_aliases_security_id_securities",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "security_id",
            "alias_type",
            "normalized_alias",
            name="uq_security_aliases_security_type_normalized_alias",
        ),
        sa.CheckConstraint(
            "length(alias) BETWEEN 1 AND 256", name="ck_security_aliases_alias_length"
        ),
        sa.CheckConstraint(
            "length(normalized_alias) BETWEEN 1 AND 256",
            name="ck_security_aliases_normalized_alias_length",
        ),
        sa.CheckConstraint(
            "alias_type IN ('SYMBOL', 'SYMBOL_WITH_EXCHANGE', 'COMPANY_SHORT_NAME', "
            "'LEGAL_NAME', 'ENGLISH_NAME', 'PROVIDER_SYMBOL', 'FORMER_NAME')",
            name="ck_security_aliases_alias_type",
        ),
        sa.CheckConstraint(
            "locale IS NULL OR length(locale) BETWEEN 1 AND 16",
            name="ck_security_aliases_locale_length",
        ),
        sa.CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128", name="ck_security_aliases_source_name_length"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_security_aliases_validity",
        ),
    )
    op.create_index("ix_security_aliases_security_id", "security_aliases", ["security_id"])
    op.create_index(
        "ix_security_aliases_normalized_alias", "security_aliases", ["normalized_alias"]
    )
    op.create_index(
        "ix_security_aliases_normalized_alias_prefix",
        "security_aliases",
        ["normalized_alias"],
        postgresql_ops={"normalized_alias": "text_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_security_aliases_normalized_alias_prefix", table_name="security_aliases")
    op.drop_index("ix_security_aliases_normalized_alias", table_name="security_aliases")
    op.drop_index("ix_security_aliases_security_id", table_name="security_aliases")
    op.drop_table("security_aliases")
    op.drop_index("ix_security_identifiers_security_id", table_name="security_identifiers")
    op.drop_table("security_identifiers")
    op.drop_index("ix_securities_normalized_symbol_prefix", table_name="securities")
    op.drop_index("ix_securities_normalized_symbol", table_name="securities")
    op.drop_index("ix_securities_issuer_id", table_name="securities")
    op.drop_table("securities")
    op.drop_index("ix_issuer_identifiers_issuer_id", table_name="issuer_identifiers")
    op.drop_table("issuer_identifiers")
    op.drop_index("ix_issuers_normalized_display_name_prefix", table_name="issuers")
    op.drop_index("ix_issuers_normalized_legal_name_prefix", table_name="issuers")
    op.drop_index("ix_issuers_normalized_display_name", table_name="issuers")
    op.drop_index("ix_issuers_normalized_legal_name", table_name="issuers")
    op.drop_table("issuers")
    op.drop_index("ix_exchange_aliases_exchange_id", table_name="exchange_aliases")
    op.drop_table("exchange_aliases")
    op.drop_table("exchanges")
    op.drop_table("markets")
