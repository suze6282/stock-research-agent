# Deployment Feasibility

Assessment date: 2026-07-11.

## Current conclusion

Local public endpoints are reachable, but production deployment is unverified. Tencent Cloud mainland and OpenAI API cannot be assumed compatible: OpenAI's current official supported-country list says locations absent from the list are unsupported, and mainland China is absent. **OpenAI公共端点网络可达，但API鉴权、模型权限、配额、Responses API、Structured Outputs以及目标部署地区的生产连通性尚未验证。**

## Feasibility matrix

| Area | Current evidence | Status | Required decision/test |
|---|---|---|---|
| Tencent Cloud region | Tencent documents mainland, Hong Kong and overseas regions including Singapore for compute/storage products | `NEEDS_VALIDATION` | Choose where compute, DB, object storage, logs and model calls reside. Validate each service in the same selected region. |
| OpenAI API connectivity | Desktop public endpoint returned 401 without credentials | `PARTIALLY_VERIFIED` network path only | Authentication, model access, quota, Responses API, Structured Outputs and selected-region production connectivity all remain unverified. |
| OpenAI regional policy | Official list omits mainland China; Hong Kong also was not observed in the reviewed list; Singapore is listed | `BLOCKED` for mainland OpenAI plan | User must choose a supported deployment/model strategy and obtain legal/terms review; no circumvention design. |
| SEC connectivity | Desktop submissions and Company Facts returned 200; Archives had both isolated 200 and repeat-probe 403 | `PARTIALLY_VERIFIED` | Test from selected cloud region with real contact User-Agent, internal low rate, cache and bulk downloads. |
| A-share source connectivity | SSE/CNINFO home and SSE sample endpoints returned 200 | `PARTIALLY_VERIFIED` | Test authenticated selected provider from cloud region; confirm provider regional restrictions and contract. |
| Provider regional limits | Not in reviewed contracts | `NOT_VERIFIED` | Written/vendor confirmation for Tencent selected region and IP/network use. |
| Object storage | Tencent COS documents mainland/Hong Kong/Singapore regions and regional data placement | `PARTIALLY_VERIFIED` | Select region, encryption/KMS, lifecycle, object lock/versioning and access policy. |
| PostgreSQL | Tencent offers managed PostgreSQL and automatic backups; current local Docker/database not tested | `PARTIALLY_VERIFIED` service, `NOT_VERIFIED` project | Stage 2 local alternative or Docker, selected cloud SKU/region, TLS, least privilege, restore drill. |
| Backup | Tencent PostgreSQL default backup retention documented as seven days; COS transfer options exist | `NEEDS_VALIDATION` | Define RPO/RTO, longer retention, encrypted cross-account/region copy where lawful, and restore tests. |
| Timezone | A-share Asia/Shanghai; Nasdaq America/New_York; storage should use UTC | `DECIDED` | Persist timezone-aware UTC timestamps plus exchange timezone and market date. |
| Domain/filing | Mainland-hosted public sites generally require domain/ICP-related review; V0.1 has no frontend | `DEFERRED` | Revisit before Stage 10/public deployment. |
| Cross-border data | Filings and market data may cross borders; model prompts may contain issuer documents and user queries | `NEEDS_VALIDATION` | Data classification/minimization, provider/model terms and qualified cross-border/privacy review before production. |
| Secret management | No key names configured; model must not access secrets | `NOT_VERIFIED` | Use Tencent Secret Manager or equivalent in selected region, scoped identities, rotation and redaction tests. |
| Network failure degradation | Architecture defined, not implemented | `DECIDED` design | Cache immutable filings, return last eligible snapshot with staleness warning, queue retries, circuit-break provider, output `PARTIAL`; never substitute future/unlicensed data. |

## Recommended deployment options for later decision

1. **Local-only V0.1:** simplest personal-use boundary; still needs provider and model terms, backups and secret management.
2. **Tencent Cloud region in an OpenAI-supported country (for example Singapore, subject to account/user/terms review):** potentially aligns compute location with supported API geography, but may introduce cross-border/data-provider latency and regulatory questions.
3. **Mainland Tencent with a lawfully available model provider:** avoids claiming unsupported OpenAI use, but changes model/provider assumptions and requires separate quality/security review.

No option is selected in Stage 1.

## Data and service layout candidate

- Private application subnet; no public database.
- PostgreSQL for identities, facts, snapshots, calculations and report metadata.
- Encrypted object storage for authorized source artifacts and content-addressed parsed outputs.
- Separate queue/workers later for ingestion/RAG/report tasks.
- Egress proxy/allowlist for provider domains.
- Secret manager and workload identities.
- UTC logs/metrics with redaction; alert on provider failure, staleness, cost and backup status.

## Sources

- [OpenAI supported countries and territories](https://help.openai.com/en/articles/5347006-openai-api-supported-countries-and-territories)
- [Tencent COS regions](https://cloud.tencent.com/document/product/436/6224)
- [Tencent PostgreSQL automatic backup](https://cloud.tencent.com/document/product/409/68388)
- [Tencent PostgreSQL-to-COS backup](https://cloud.tencent.com/document/product/436/94087)
