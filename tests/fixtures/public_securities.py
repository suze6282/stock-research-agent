"""Project-authored synthetic securities used by public Fixture integration tests."""

from __future__ import annotations

from sqlalchemy import Engine, text


def add_public_synthetic_securities(engine: Engine) -> None:
    """Add fictional securities without changing the production seed manifest."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO issuers "
                "(id, legal_name, normalized_legal_name, display_name, "
                "normalized_display_name, country_code, issuer_status) VALUES "
                "('39000000-0000-0000-0000-000000000001', "
                "'示例测试股份有限公司', '示例测试股份有限公司', "
                "'示例测试股份有限公司', '示例测试股份有限公司', 'CN', 'UNKNOWN'), "
                "('39000000-0000-0000-0000-000000000002', "
                "'Example Test Technologies Inc.', 'EXAMPLE TEST TECHNOLOGIES INC', "
                "'Example Test Technologies', 'EXAMPLE TEST TECHNOLOGIES', "
                "'US', 'UNKNOWN')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO securities "
                "(id, issuer_id, exchange_id, symbol, normalized_symbol, display_name, "
                "security_type, currency_code, listing_status) "
                "SELECT '49000000-0000-0000-0000-000000000001'::uuid, "
                "'39000000-0000-0000-0000-000000000001'::uuid, id, 'TEST001', 'TEST001', "
                "'示例测试股份有限公司', 'COMMON_STOCK', 'CNY', 'UNKNOWN' "
                "FROM exchanges WHERE mic = 'XSHG' UNION ALL SELECT "
                "'49000000-0000-0000-0000-000000000002'::uuid, "
                "'39000000-0000-0000-0000-000000000002'::uuid, id, 'TSTX', 'TSTX', "
                "'Example Test Technologies', 'COMMON_STOCK', 'USD', 'UNKNOWN' "
                "FROM exchanges WHERE mic = 'XNAS'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO security_aliases "
                "(id, security_id, alias, normalized_alias, alias_type, source_name, is_active) "
                "VALUES ('59000000-0000-0000-0000-000000000001', "
                "'49000000-0000-0000-0000-000000000001', 'TEST001.SH', 'TEST001.SH', "
                "'SYMBOL_WITH_EXCHANGE', 'Public synthetic fixture', true), "
                "('59000000-0000-0000-0000-000000000002', "
                "'49000000-0000-0000-0000-000000000002', 'NASDAQ:TSTX', 'NASDAQ:TSTX', "
                "'SYMBOL_WITH_EXCHANGE', 'Public synthetic fixture', true)"
            )
        )
