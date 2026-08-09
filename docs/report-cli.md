# Report CLI and read contracts

Report writes are explicit and transaction-owned:

```text
stock-research report policy seed-v1
stock-research report reflection-policy seed-v1
stock-research report template seed-v1
stock-research report generate PACKAGE_ID --type TYPE --locale zh-CN
stock-research report reflect REPORT_ID --round 1
stock-research report revise REPORT_ID --reflection-run RUN_ID
stock-research report reflect REPORT_ID --round 2 --prior-reflection-run RUN_ID --revision-run RUN_ID
stock-research report release-check REPORT_ID --reflection-run ROUND_TWO_ID
stock-research report export-markdown REPORT_ID RELATIVE_FILENAME
```

Generate does not Reflect; Reflect does not Revise; Revise requires round 1;
release-check requires round 2. None implicitly runs a Tool, provider, model,
network refresh, Snapshot build, calculation or retrieval. Export reads one
persisted version and never publishes it.

Read commands (`show`, `sections`, `claims`, `evidence`, `citations`,
`findings`, `versions`) are bounded projections of persisted rows.
