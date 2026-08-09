# Claim-level report bindings

`report_claim_bindings`, `report_evidence_bindings` and
`report_citation_bindings` preserve exact immutable lineage.

- A Claim binding identifies one sentence or one table/item key.
- An Evidence binding identifies the exact Stage 7 Claim-Evidence Link, role,
  Evidence, source checksum and stable `EV-nnn` or `MET-nnn` reference.
- A Citation binding permits only a `VALID` Stage 6 Citation, exact
  `DocumentVersion`, locator, unchanged bounded excerpt and excerpt checksum.

References are allocated by first canonical appearance. Duplicate locations,
links or visible references fail. A Citation with unknown/future publication
time, invalid verification, a changed excerpt, wrong Security/Snapshot/Run, or
Synthetic contamination cannot support a real-company fact.
