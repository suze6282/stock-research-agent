# Internal report release gate

The deterministic Gate evaluates 18 requirements after Reflection round 2.
Only it can create `internal_release_status=PUBLISHABLE`.

`PUBLISHABLE` means the immutable report passed internal integrity, safety and
traceability checks. It does not mean public publication, client distribution,
analyst sign-off, regulatory or compliance approval, live-data readiness,
investment advice, a rating, target price, position recommendation or permission
to trade. It cannot trigger automatic trading.

Real-company `PARTIAL`/`BLOCKED` Packages remain `PARTIAL`/`BLOCKED`.
A neutral Synthetic report may be internally `PUBLISHABLE` only when all four
test markers and the full binding/Reflection/Revision/Gate contract pass. That
status proves engineering behavior only.
