# Provider Live validation isolation

This directory is not run by default pytest and is not run by default CI. Tests
here are operational Live validations, not ordinary integration tests. They must
never be moved into `tests/` or activated by the presence of credentials alone.

Before any command is run, the operator must disclose and record all of the
following for exactly one Provider and capability:

- Provider code and immutable Provider version;
- official domains and exact endpoint paths;
- capability code and immutable capability version;
- finite request budget and byte budget;
- finite record/document budget and duration;
- credential reference names only, never credential values;
- raw-storage decision and license/redistribution/retention status;
- expected cost and elapsed time;
- development and test database impact;
- cleanup and rollback procedure.

Execution then requires the user's exact phrase:

`批准执行该Provider的有限Live验证`

The approval is single-provider, single-capability, single-budget, and
single-validation-run authorization. SEC approval does not authorize Tushare.
A health-check approval does not authorize history backfill. Expired, consumed,
missing, mismatched, or broadened authorization remains `BLOCKED`, and the Live
status remains `NOT_ATTEMPTED` until a request is actually authorized and made.

Live results must never be inferred from offline fixtures. Missing credentials,
license approval, contact configuration, or endpoint authorization is reported as
`BLOCKED` or `NOT_ATTEMPTED`, never `PASS`.
