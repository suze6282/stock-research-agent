"""SQLAlchemy models for issuer and listed-security master data."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_research_agent.db.base import Base


class TimestampedUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )


class Market(TimestampedUuidMixin, Base):
    __tablename__ = "markets"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_markets"),
        UniqueConstraint("code", name="uq_markets_code"),
        CheckConstraint("code ~ '^[A-Z][A-Z0-9_]{0,31}$'", name="ck_markets_code_format"),
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_markets_name_length"),
        CheckConstraint("country_code IN ('CN', 'US')", name="ck_markets_country_code"),
        CheckConstraint("default_currency_code IN ('CNY', 'USD')", name="ck_markets_currency_code"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'UNKNOWN')", name="ck_markets_status"),
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    default_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    exchanges: Mapped[list[Exchange]] = relationship(
        back_populates="market",
        passive_deletes=True,
    )


class Exchange(TimestampedUuidMixin, Base):
    __tablename__ = "exchanges"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_exchanges"),
        ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name="fk_exchanges_market_id_markets",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("mic", name="uq_exchanges_mic"),
        CheckConstraint("mic IN ('XNAS', 'XSHG')", name="ck_exchanges_mic"),
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="ck_exchanges_name_length"),
        CheckConstraint(
            "length(short_name) BETWEEN 1 AND 64", name="ck_exchanges_short_name_length"
        ),
        CheckConstraint("country_code IN ('CN', 'US')", name="ck_exchanges_country_code"),
        CheckConstraint("length(timezone) BETWEEN 1 AND 64", name="ck_exchanges_timezone_length"),
        CheckConstraint(
            "default_currency_code IN ('CNY', 'USD')", name="ck_exchanges_currency_code"
        ),
        CheckConstraint(
            "calendar_code IS NULL OR length(calendar_code) BETWEEN 1 AND 64",
            name="ck_exchanges_calendar_code_length",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'UNKNOWN')", name="ck_exchanges_status"),
    )

    market_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    mic: Mapped[str] = mapped_column(String(4), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    short_name: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    default_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    calendar_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    market: Mapped[Market] = relationship(back_populates="exchanges")
    aliases: Mapped[list[ExchangeAlias]] = relationship(
        back_populates="exchange",
        passive_deletes=True,
    )
    securities: Mapped[list[Security]] = relationship(
        back_populates="exchange",
        passive_deletes=True,
    )


class ExchangeAlias(TimestampedUuidMixin, Base):
    __tablename__ = "exchange_aliases"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_exchange_aliases"),
        ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name="fk_exchange_aliases_exchange_id_exchanges",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("normalized_alias", name="uq_exchange_aliases_normalized_alias"),
        CheckConstraint("length(alias) BETWEEN 1 AND 64", name="ck_exchange_aliases_alias_length"),
        CheckConstraint(
            "normalized_alias ~ '^[A-Z0-9]{1,32}$'",
            name="ck_exchange_aliases_normalized_alias_format",
        ),
        CheckConstraint(
            "alias_type IN ('MIC', 'SUFFIX', 'SHORT_NAME', 'DISPLAY_NAME')",
            name="ck_exchange_aliases_alias_type",
        ),
        Index("ix_exchange_aliases_exchange_id", "exchange_id"),
    )

    exchange_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(32), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    exchange: Mapped[Exchange] = relationship(back_populates="aliases")


class Issuer(TimestampedUuidMixin, Base):
    __tablename__ = "issuers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_issuers"),
        CheckConstraint(
            "length(legal_name) BETWEEN 1 AND 256", name="ck_issuers_legal_name_length"
        ),
        CheckConstraint(
            "length(normalized_legal_name) BETWEEN 1 AND 256",
            name="ck_issuers_normalized_legal_name_length",
        ),
        CheckConstraint(
            "length(display_name) BETWEEN 1 AND 256", name="ck_issuers_display_name_length"
        ),
        CheckConstraint(
            "length(normalized_display_name) BETWEEN 1 AND 256",
            name="ck_issuers_normalized_display_name_length",
        ),
        CheckConstraint("country_code IN ('CN', 'US')", name="ck_issuers_country_code"),
        CheckConstraint(
            "issuer_status IN ('ACTIVE', 'INACTIVE', 'UNKNOWN')",
            name="ck_issuers_status",
        ),
        Index("ix_issuers_normalized_legal_name", "normalized_legal_name"),
        Index("ix_issuers_normalized_display_name", "normalized_display_name"),
        Index(
            "ix_issuers_normalized_legal_name_prefix",
            "normalized_legal_name",
            postgresql_ops={"normalized_legal_name": "text_pattern_ops"},
        ),
        Index(
            "ix_issuers_normalized_display_name_prefix",
            "normalized_display_name",
            postgresql_ops={"normalized_display_name": "text_pattern_ops"},
        ),
    )

    legal_name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_legal_name: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    issuer_status: Mapped[str] = mapped_column(String(16), nullable=False)

    identifiers: Mapped[list[IssuerIdentifier]] = relationship(
        back_populates="issuer",
        passive_deletes=True,
    )
    securities: Mapped[list[Security]] = relationship(
        back_populates="issuer",
        passive_deletes=True,
    )


class IssuerIdentifier(TimestampedUuidMixin, Base):
    __tablename__ = "issuer_identifiers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_issuer_identifiers"),
        ForeignKeyConstraint(
            ["issuer_id"],
            ["issuers.id"],
            name="fk_issuer_identifiers_issuer_id_issuers",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "scheme",
            "normalized_value",
            name="uq_issuer_identifiers_scheme_normalized_value",
        ),
        CheckConstraint(
            "scheme ~ '^[A-Z][A-Z0-9_]{1,63}$'", name="ck_issuer_identifiers_scheme_format"
        ),
        CheckConstraint(
            "length(value) BETWEEN 1 AND 256", name="ck_issuer_identifiers_value_length"
        ),
        CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 256",
            name="ck_issuer_identifiers_normalized_value_length",
        ),
        CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128",
            name="ck_issuer_identifiers_source_name_length",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_issuer_identifiers_validity",
        ),
        Index("ix_issuer_identifiers_issuer_id", "issuer_id"),
    )

    issuer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool | None] = mapped_column(Boolean)

    issuer: Mapped[Issuer] = relationship(back_populates="identifiers")


class Security(TimestampedUuidMixin, Base):
    __tablename__ = "securities"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_securities"),
        ForeignKeyConstraint(
            ["issuer_id"],
            ["issuers.id"],
            name="fk_securities_issuer_id_issuers",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name="fk_securities_exchange_id_exchanges",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("exchange_id", "normalized_symbol", name="uq_securities_exchange_symbol"),
        CheckConstraint("length(symbol) BETWEEN 1 AND 64", name="ck_securities_symbol_length"),
        CheckConstraint(
            "normalized_symbol ~ '^[A-Z0-9]+([.:-][A-Z0-9]+)*$'",
            name="ck_securities_normalized_symbol_format",
        ),
        CheckConstraint(
            "length(display_name) BETWEEN 1 AND 256", name="ck_securities_display_name_length"
        ),
        CheckConstraint("security_type IN ('COMMON_STOCK')", name="ck_securities_security_type"),
        CheckConstraint(
            "share_class IS NULL OR length(share_class) BETWEEN 1 AND 64",
            name="ck_securities_share_class_length",
        ),
        CheckConstraint("currency_code IN ('CNY', 'USD')", name="ck_securities_currency_code"),
        CheckConstraint(
            "listing_status IN ('ACTIVE', 'SUSPENDED', 'DELISTED', 'UNKNOWN')",
            name="ck_securities_listing_status",
        ),
        CheckConstraint(
            "delisting_date IS NULL OR listing_date IS NULL OR delisting_date >= listing_date",
            name="ck_securities_listing_dates",
        ),
        Index("ix_securities_issuer_id", "issuer_id"),
        Index("ix_securities_normalized_symbol", "normalized_symbol"),
        Index(
            "ix_securities_normalized_symbol_prefix",
            "normalized_symbol",
            postgresql_ops={"normalized_symbol": "text_pattern_ops"},
        ),
    )

    issuer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    exchange_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    security_type: Mapped[str] = mapped_column(String(32), nullable=False)
    share_class: Mapped[str | None] = mapped_column(String(64))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    listing_status: Mapped[str] = mapped_column(String(16), nullable=False)
    listing_date: Mapped[date | None] = mapped_column(Date)
    delisting_date: Mapped[date | None] = mapped_column(Date)
    is_primary_listing: Mapped[bool | None] = mapped_column(Boolean)

    issuer: Mapped[Issuer] = relationship(back_populates="securities")
    exchange: Mapped[Exchange] = relationship(back_populates="securities")
    identifiers: Mapped[list[SecurityIdentifier]] = relationship(
        back_populates="security",
        passive_deletes=True,
    )
    aliases: Mapped[list[SecurityAlias]] = relationship(
        back_populates="security",
        passive_deletes=True,
    )


class SecurityIdentifier(TimestampedUuidMixin, Base):
    __tablename__ = "security_identifiers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_security_identifiers"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_security_identifiers_security_id_securities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "scheme",
            "normalized_value",
            name="uq_security_identifiers_scheme_normalized_value",
        ),
        CheckConstraint(
            "scheme ~ '^[A-Z][A-Z0-9_]{1,63}$'", name="ck_security_identifiers_scheme_format"
        ),
        CheckConstraint(
            "length(value) BETWEEN 1 AND 256", name="ck_security_identifiers_value_length"
        ),
        CheckConstraint(
            "length(normalized_value) BETWEEN 1 AND 256",
            name="ck_security_identifiers_normalized_value_length",
        ),
        CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128",
            name="ck_security_identifiers_source_name_length",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_security_identifiers_validity",
        ),
        Index("ix_security_identifiers_security_id", "security_id"),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(256), nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool | None] = mapped_column(Boolean)

    security: Mapped[Security] = relationship(back_populates="identifiers")


class SecurityAlias(TimestampedUuidMixin, Base):
    __tablename__ = "security_aliases"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_security_aliases"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_security_aliases_security_id_securities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "security_id",
            "alias_type",
            "normalized_alias",
            name="uq_security_aliases_security_type_normalized_alias",
        ),
        CheckConstraint("length(alias) BETWEEN 1 AND 256", name="ck_security_aliases_alias_length"),
        CheckConstraint(
            "length(normalized_alias) BETWEEN 1 AND 256",
            name="ck_security_aliases_normalized_alias_length",
        ),
        CheckConstraint(
            "alias_type IN ('SYMBOL', 'SYMBOL_WITH_EXCHANGE', 'COMPANY_SHORT_NAME', "
            "'LEGAL_NAME', 'ENGLISH_NAME', 'PROVIDER_SYMBOL', 'FORMER_NAME')",
            name="ck_security_aliases_alias_type",
        ),
        CheckConstraint(
            "locale IS NULL OR length(locale) BETWEEN 1 AND 16",
            name="ck_security_aliases_locale_length",
        ),
        CheckConstraint(
            "length(source_name) BETWEEN 1 AND 128", name="ck_security_aliases_source_name_length"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_security_aliases_validity",
        ),
        Index("ix_security_aliases_security_id", "security_id"),
        Index("ix_security_aliases_normalized_alias", "normalized_alias"),
        Index(
            "ix_security_aliases_normalized_alias_prefix",
            "normalized_alias",
            postgresql_ops={"normalized_alias": "text_pattern_ops"},
        ),
    )

    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(256), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str | None] = mapped_column(String(16))
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    security: Mapped[Security] = relationship(back_populates="aliases")
