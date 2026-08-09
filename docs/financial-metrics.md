# Financial metrics and interpretation limits

The calculation engine exposes 23 stable codes:

`revenue_growth`, `gross_margin`, `operating_margin`, `net_margin_parent`,
`roe_parent`, `roa_total`, `roic`, `operating_cash_flow`, `free_cash_flow`,
`liabilities_to_assets`, `net_debt`, `basic_eps`, `diluted_eps`, `market_cap`,
`pe_ttm_diluted`, `pb_parent`, `ps_ttm`, `enterprise_value`,
`ev_to_ebitda_ttm`, `fcf_yield_ttm`, `revenue_ttm`,
`net_income_parent_ttm`, and `ebitda_ttm`.

These are deterministic data products, not investment recommendations. PE with
nonpositive earnings, PB with nonpositive equity, PS with nonpositive revenue, and
EV/EBITDA with nonpositive EBITDA are N/M rather than misleading negative multiples.
Cycle, accounting policy, one-off items, share-class differences and incomplete
evidence still require analyst judgment. There is no narrative conclusion, target
price, scenario engine, portfolio advice, RAG, Agent, MCP Server or trading feature.

Read commands are bounded and never refresh data:

```powershell
uv run stock-research financials periods "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials facts "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials metrics "MU" --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials metric "MU" gross_margin --snapshot <SNAPSHOT_ID> --json
uv run stock-research financials lineage <CALCULATION_RUN_ID> gross_margin --json
```
