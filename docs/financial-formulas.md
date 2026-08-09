# Deterministic formula registry

V0.1 contains 23 immutable `1.0.0` definitions implemented by whitelisted Python
functions. Stored expressions are documentation, never executable input; the engine
does not use `eval`, dynamic field access, user code, float, network access, or an LLM.

The registry covers revenue growth; gross, operating and parent net margin; ROE, ROA,
ROIC; operating and free cash flow; liabilities/assets; net debt; basic/diluted EPS;
market cap; PE, PB, PS; enterprise value; EV/EBITDA; FCF yield; and revenue, parent net
income and EBITDA TTM. Net debt V0.1 subtracts cash and cash equivalents only.

All inputs carry Decimal value, unit and currency. Same-basis operations reject mixed
currency or incompatible units. Average-balance returns require opening and closing
facts. Nonpositive valuation denominators produce `NOT_MEANINGFUL` without a number;
missing inputs produce `NULL/BLOCKED`; actual zero remains `ZERO`. Internal values are
not rounded. Formula version and ordered consumed inputs are persisted with each run.

Current offline sample snapshots contain no numeric financial facts, so their 23
definitions are instantiated as honest `BLOCKED/NULL` metrics. Formula and golden
tests use clearly synthetic values in isolated tests; no synthetic value enters the
production seed or sample fixtures.
