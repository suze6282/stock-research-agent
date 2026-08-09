from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.security_master import (
    Exchange,
    ExchangeAlias,
    Issuer,
    IssuerIdentifier,
    Market,
    Security,
    SecurityAlias,
    SecurityIdentifier,
)

STAGE_3_TABLES = {
    "markets",
    "exchanges",
    "exchange_aliases",
    "issuers",
    "issuer_identifiers",
    "securities",
    "security_identifiers",
    "security_aliases",
}


def test_all_security_master_models_are_registered_on_shared_metadata() -> None:
    assert STAGE_3_TABLES <= set(Base.metadata.tables)
    assert {
        Market.__tablename__,
        Exchange.__tablename__,
        ExchangeAlias.__tablename__,
        Issuer.__tablename__,
        IssuerIdentifier.__tablename__,
        Security.__tablename__,
        SecurityIdentifier.__tablename__,
        SecurityAlias.__tablename__,
    } == STAGE_3_TABLES


def test_all_foreign_keys_restrict_deletion() -> None:
    for table_name in STAGE_3_TABLES:
        for foreign_key in Base.metadata.tables[table_name].foreign_keys:
            assert foreign_key.ondelete == "RESTRICT"


def test_required_unique_constraints_are_named_and_scoped_correctly() -> None:
    expected = {
        "markets": {"uq_markets_code": ("code",)},
        "exchanges": {"uq_exchanges_mic": ("mic",)},
        "exchange_aliases": {"uq_exchange_aliases_normalized_alias": ("normalized_alias",)},
        "issuer_identifiers": {
            "uq_issuer_identifiers_scheme_normalized_value": (
                "scheme",
                "normalized_value",
            )
        },
        "securities": {"uq_securities_exchange_symbol": ("exchange_id", "normalized_symbol")},
        "security_identifiers": {
            "uq_security_identifiers_scheme_normalized_value": (
                "scheme",
                "normalized_value",
            )
        },
        "security_aliases": {
            "uq_security_aliases_security_type_normalized_alias": (
                "security_id",
                "alias_type",
                "normalized_alias",
            )
        },
    }
    for table_name, expected_constraints in expected.items():
        actual = {
            constraint.name: tuple(column.name for column in constraint.columns)
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert actual == expected_constraints

    issuer_unique_names = {
        constraint.name
        for constraint in Base.metadata.tables["issuers"].constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert not issuer_unique_names


def test_primary_and_foreign_key_names_and_columns_are_exact() -> None:
    for table_name in STAGE_3_TABLES:
        table = Base.metadata.tables[table_name]
        assert table.primary_key.name == f"pk_{table_name}"
        assert tuple(column.name for column in table.primary_key.columns) == ("id",)

    expected_foreign_keys = {
        "exchanges": {"fk_exchanges_market_id_markets": (("market_id",), "markets")},
        "exchange_aliases": {
            "fk_exchange_aliases_exchange_id_exchanges": (("exchange_id",), "exchanges")
        },
        "issuer_identifiers": {
            "fk_issuer_identifiers_issuer_id_issuers": (("issuer_id",), "issuers")
        },
        "securities": {
            "fk_securities_issuer_id_issuers": (("issuer_id",), "issuers"),
            "fk_securities_exchange_id_exchanges": (("exchange_id",), "exchanges"),
        },
        "security_identifiers": {
            "fk_security_identifiers_security_id_securities": (
                ("security_id",),
                "securities",
            )
        },
        "security_aliases": {
            "fk_security_aliases_security_id_securities": (
                ("security_id",),
                "securities",
            )
        },
    }
    for table_name, expected in expected_foreign_keys.items():
        actual = {}
        for constraint in Base.metadata.tables[table_name].constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                actual[constraint.name] = (
                    tuple(column.name for column in constraint.columns),
                    next(iter(constraint.elements)).column.table.name,
                )
        assert actual == expected


def test_all_checks_and_indexes_are_named_for_real_query_paths() -> None:
    for table_name in STAGE_3_TABLES:
        checks = {
            constraint.name
            for constraint in Base.metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert checks
        assert None not in checks

    expected_indexes = {
        "ix_issuers_normalized_legal_name",
        "ix_issuers_normalized_display_name",
        "ix_issuers_normalized_legal_name_prefix",
        "ix_issuers_normalized_display_name_prefix",
        "ix_securities_normalized_symbol",
        "ix_securities_normalized_symbol_prefix",
        "ix_security_aliases_normalized_alias",
        "ix_security_aliases_normalized_alias_prefix",
    }
    actual_indexes = {
        index.name
        for table_name in STAGE_3_TABLES
        for index in Base.metadata.tables[table_name].indexes
    }
    assert expected_indexes <= actual_indexes

    for table_name in ("issuers", "securities", "security_aliases"):
        for index in Base.metadata.tables[table_name].indexes:
            if index.name and index.name.endswith("_prefix"):
                operations = index.dialect_options["postgresql"]["ops"]
                assert set(operations.values()) == {"text_pattern_ops"}


def test_relationships_do_not_enable_delete_orphan_or_delete_cascade() -> None:
    for mapper in (
        Market.__mapper__,
        Exchange.__mapper__,
        Issuer.__mapper__,
        Security.__mapper__,
    ):
        for relationship in mapper.relationships:
            assert "delete" not in relationship.cascade
            assert "delete-orphan" not in relationship.cascade
