# Stage 1 Feasibility Probe

`validate_public_sources.py` is a read-only Stage 1 probe. It is not a production provider adapter. It uses timeouts, low request frequency, a named User-Agent, no secret reads and no raw-response persistence.

## Usage

```powershell
python scripts/feasibility/validate_public_sources.py
```

For a production-compliant SEC test, the caller must configure a real contact rather than a fabricated placeholder:

```powershell
python scripts/feasibility/validate_public_sources.py --contact "REAL_PROJECT_CONTACT_EMAIL_OR_URL"
```

Provider flags only record that external configuration/terms were separately verified; they do not read keys:

```text
--tushare-configured
--us-eod-configured
--openai-auth-verified
```

## Output

The script prints one JSON object containing:

- `overall_status`: `PASS`, `PARTIAL`, `BLOCKED`, or `FAIL`;
- required and optional passed/failed checks;
- configuration gaps;
- warnings;
- per-check request/result metadata;
- selected exit code.

## Exit codes

| Code | Status | Meaning |
|---:|---|---|
| 0 | `PASS` | All required and optional checks passed; no gaps or warnings remain. |
| 1 | `FAIL` | At least one required check failed for a non-configuration reason such as timeout, parse error or invalid response. |
| 2 | `PARTIAL` | Required checks passed, but optional checks, configuration gaps or warnings remain. |
| 3 | `BLOCKED` | A required check was blocked by authentication, authorization, policy or rate control. |

CI must treat every nonzero value as not fully successful. The recorded full Python Stage 1 execution is `BLOCKED`/3 because SEC Archive index/document checks returned 403 with no real contact configured. A later same-header .NET retry retrieved valid index JSON, but Python remained 403 and both primary documents remained 403, so this does not upgrade the overall status.

## Tests

```powershell
python -m unittest -v scripts/feasibility/test_validate_public_sources.py
```
