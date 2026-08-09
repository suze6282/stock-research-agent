"""Read-only Stage 1 probes for public Stock Research Agent sources.

The script prints one structured JSON report. It does not read secrets, persist responses,
or implement any production provider adapter.

Exit codes:
    0: PASS -- every required and optional check passed with no gaps/warnings.
    1: FAIL -- at least one required check failed for a non-configuration reason.
    2: PARTIAL -- required checks passed, but optional checks, gaps, or warnings remain.
    3: BLOCKED -- at least one required check was blocked by auth, policy, or rate control.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.25
SSE_REFERER = "https://www.sse.com.cn/"
STATUSES = {"PASS", "PARTIAL", "BLOCKED", "FAIL"}
EXIT_CODES = {"PASS": 0, "FAIL": 1, "PARTIAL": 2, "BLOCKED": 3}
REQUIRED_CHECK_PREFIXES = {
    "sse_security_identity",
    "sse_daily_bars",
    "sse_periodic_reports",
    "sse_pdf_accounting_basis",
    "sec_micron_identity_and_filings",
    "sec_companyfacts",
    "sec_filing_index",
    "sec_filing_document_archive",
    "sec_micron_custom_xbrl",
    "nasdaq_public_historical_mu",
    "nasdaq_public_dividends_mu",
}
_RESULTS: list[dict[str, Any]] = []


def check_is_required(check: str) -> bool:
    return any(
        check == prefix or check.startswith(f"{prefix}:") for prefix in REQUIRED_CHECK_PREFIXES
    )


def emit(check: str, status: str, *, required: bool | None = None, **details: Any) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unsupported check status: {status}")
    _RESULTS.append(
        {
            "check": check,
            "status": status,
            "required": check_is_required(check) if required is None else required,
            **details,
        }
    )


def build_summary(
    results: list[dict[str, Any]],
    *,
    configuration_gaps: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    required = [result for result in results if result["required"]]
    optional = [result for result in results if not result["required"]]
    required_failures = [result for result in required if result["status"] != "PASS"]
    optional_failures = [result for result in optional if result["status"] != "PASS"]

    if any(result["status"] == "FAIL" for result in required_failures):
        overall_status = "FAIL"
    elif any(result["status"] == "BLOCKED" for result in required_failures):
        overall_status = "BLOCKED"
    elif required_failures or optional_failures or configuration_gaps or warnings:
        overall_status = "PARTIAL"
    else:
        overall_status = "PASS"

    return {
        "overall_status": overall_status,
        "required_checks": {
            "passed": [result["check"] for result in required if result["status"] == "PASS"],
            "failed": [
                {"check": result["check"], "status": result["status"]}
                for result in required_failures
            ],
        },
        "optional_checks": {
            "passed": [result["check"] for result in optional if result["status"] == "PASS"],
            "failed": [
                {"check": result["check"], "status": result["status"]}
                for result in optional_failures
            ],
        },
        "configuration_gaps": configuration_gaps,
        "warnings": warnings,
        "results": results,
    }


def exit_code_for_status(status: str) -> int:
    try:
        return EXIT_CODES[status]
    except KeyError as error:
        raise ValueError(f"Unsupported overall status: {status}") from error


class Reader:
    def __init__(self, contact: str) -> None:
        self.user_agent = (
            "StockResearchAgent-Feasibility/0.1 "
            f"contact={contact} purpose=personal-read-only-research"
        )

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        referer: str | None = None,
        accept: str = "application/json, text/plain, */*",
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Accept-Encoding": "identity",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                if response_headers.get("content-encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return response.status, response_headers, raw
        except urllib.error.HTTPError as error:
            return (
                error.code,
                {key.lower(): value for key, value in error.headers.items()},
                error.read(4096),
            )
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)


def fetch_with_error(
    reader: Any, url: str, **kwargs: Any
) -> tuple[int | None, dict[str, str], bytes, str | None]:
    try:
        status, headers, raw = reader.fetch(url, **kwargs)
        return status, headers, raw, None
    except Exception as error:  # noqa: BLE001 - endpoint isolation is intentional
        return None, {}, b"", f"{type(error).__name__}: {error}"


def json_body(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace").strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return json.loads(text)


def probe_connectivity(reader: Reader) -> None:
    targets = {
        "sse_home": "https://www.sse.com.cn/",
        "cninfo_home": "https://www.cninfo.com.cn/",
        "sec_data": "https://data.sec.gov/",
        "micron_ir": "https://investors.micron.com/",
        "openai_api_without_key": "https://api.openai.com/v1/models",
    }
    for name, url in targets.items():
        try:
            status, headers, raw = reader.fetch(url, referer=SSE_REFERER)
            expected = status == 200 or (name == "openai_api_without_key" and status == 401)
            check_status = "PASS" if expected else "FAIL"
            details: dict[str, Any] = {}
            if name == "openai_api_without_key" and status == 401:
                check_status = "PARTIAL"
                details = {
                    "network_reachable": True,
                    "verified_scope": "Public endpoint DNS/TLS/HTTP reachability only.",
                    "not_verified": [
                        "API authentication",
                        "model permissions",
                        "quota",
                        "Responses API",
                        "Structured Outputs",
                        "production connectivity from the target deployment region",
                    ],
                }
            emit(
                name,
                check_status,
                http_status=status,
                content_type=headers.get("content-type"),
                response_bytes=len(raw),
                **details,
            )
        except Exception as error:  # noqa: BLE001 - probe must report all failures
            emit(name, "FAIL", error=f"{type(error).__name__}: {error}")


def probe_sse(reader: Reader) -> None:
    status, _, raw = reader.fetch(
        "https://www.sse.com.cn/js/common/ssesuggestdata.js", referer=SSE_REFERER
    )
    text = raw.decode("utf-8", "replace")
    match = re.search(r'val:"601138",val2:"([^"]+)",val3:"([^"]+)"', text)
    emit(
        "sse_security_identity",
        "PASS" if status == 200 and match else "FAIL",
        http_status=status,
        security_code="601138" if match else None,
        security_name=match.group(1) if match else None,
        pinyin_alias=match.group(2) if match else None,
    )

    status, _, raw = reader.fetch(
        "https://yunhq.sse.com.cn:32042/v1/sh1/dayk/601138?begin=-10&end=-1&period=day",
        referer=SSE_REFERER,
    )
    payload = json_body(raw) if status == 200 else {}
    bars = payload.get("kline") or []
    emit(
        "sse_daily_bars",
        "PASS" if status == 200 and bars else "FAIL",
        http_status=status,
        returned_bars=len(bars),
        latest_bar=bars[-1] if bars else None,
        note="Array field semantics are not documented by a public API contract.",
    )

    parameters = {
        "isPagination": "true",
        "productId": "601138",
        "keyWord": "",
        "securityType": "0101,120100,020100,020200,120200",
        "reportType2": "DQBG",
        "reportType": "ALL",
        "beginDate": "2024-01-01",
        "endDate": "2026-07-11",
        "pageHelp.pageSize": "100",
        "pageHelp.pageCount": "50",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
    }
    url = (
        "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do?"
        + urllib.parse.urlencode(parameters)
    )
    status, _, raw = reader.fetch(
        url, referer="https://www.sse.com.cn/disclosure/listedinfo/announcement/"
    )
    payload = json_body(raw) if status == 200 else {}
    records = (payload.get("pageHelp") or {}).get("data") or []
    selected = [
        {
            "published_date": row.get("SSEDATE"),
            "report_type": row.get("BULLETIN_TYPE"),
            "title": row.get("TITLE"),
            "url": row.get("URL"),
        }
        for row in records
        if row.get("BULLETIN_TYPE") in {"年报", "第一季度季报", "半年报", "第三季度季报"}
    ]
    emit(
        "sse_periodic_reports",
        "PASS" if status == 200 and selected else "FAIL",
        http_status=status,
        matched_reports=len(selected),
        latest_reports=selected[:6],
    )


def probe_sse_pdfs(reader: Reader) -> None:
    try:
        import pdfplumber
    except ImportError:
        emit("sse_pdf_accounting_basis", "SKIP", reason="pdfplumber is not installed")
        return

    documents = {
        "annual_2025": (
            "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/"
            "announcement/c/new/2026-03-11/601138_20260311_SU8W.pdf"
        ),
        "q3_2025": (
            "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/"
            "announcement/c/new/2025-10-30/601138_20251030_B2JS.pdf"
        ),
    }
    for name, url in documents.items():
        status, _, raw = reader.fetch(url, referer=SSE_REFERER, accept="application/pdf")
        if status != 200 or not raw.startswith(b"%PDF-"):
            emit("sse_pdf_accounting_basis", "FAIL", document=name, http_status=status)
            continue
        unit_hits: list[dict[str, Any]] = []
        ytd_hits: list[dict[str, Any]] = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                for line in text.splitlines():
                    if "单位：千元" in line and len(unit_hits) < 5:
                        unit_hits.append({"page": page_number, "text": line[:160]})
                    if any(
                        marker in line for marker in ("年初至报告期末", "2025年1—9月", "（1-9月）")
                    ):
                        if len(ytd_hits) < 8:
                            ytd_hits.append({"page": page_number, "text": line[:160]})
            emit(
                "sse_pdf_accounting_basis",
                "PASS" if unit_hits and (name == "annual_2025" or ytd_hits) else "FAIL",
                document=name,
                http_status=status,
                pages=len(pdf.pages),
                unit_evidence=unit_hits,
                cumulative_evidence=ytd_hits,
            )


def latest_forms(recent: dict[str, list[Any]], form: str, limit: int = 5) -> list[dict[str, Any]]:
    output = []
    for index, value in enumerate(recent.get("form", [])):
        if value == form:
            output.append(
                {
                    key: recent[key][index]
                    for key in (
                        "form",
                        "filingDate",
                        "reportDate",
                        "accessionNumber",
                        "primaryDocument",
                    )
                }
            )
            if len(output) == limit:
                break
    return output


def sec_request_record(reader: Reader, url: str, accept: str) -> dict[str, Any]:
    return {
        "method": "GET",
        "url": url,
        "headers": {
            "User-Agent": reader.user_agent,
            "Accept": accept,
            "Accept-Encoding": "identity",
        },
    }


def blocked_or_failed(http_status: int) -> str:
    return "BLOCKED" if http_status in {401, 403, 429} else "FAIL"


def response_failure(headers: dict[str, str], raw: bytes, status: int) -> dict[str, Any]:
    return {
        "http_status": status,
        "content_type": headers.get("content-type"),
        "body_prefix": raw[:240].decode("utf-8", "replace").replace("\r", " ").replace("\n", " "),
    }


def probe_sec(reader: Reader) -> None:
    submissions_url = "https://data.sec.gov/submissions/CIK0000723125.json"
    status, headers, raw, error = fetch_with_error(reader, submissions_url)
    submissions = json_body(raw) if status == 200 else {}
    recent = (submissions.get("filings") or {}).get("recent") or {}
    emit(
        "sec_micron_identity_and_filings",
        "PASS" if status == 200 and submissions.get("tickers") == ["MU"] else "FAIL",
        http_status=status,
        cik=submissions.get("cik"),
        name=submissions.get("name"),
        tickers=submissions.get("tickers"),
        exchanges=submissions.get("exchanges"),
        fiscal_year_end=submissions.get("fiscalYearEnd"),
        forms={form: latest_forms(recent, form) for form in ("10-K", "10-Q", "8-K")},
        request=sec_request_record(reader, submissions_url, "application/json, text/plain, */*"),
        failure=(
            {"error": error}
            if error
            else response_failure(headers, raw, int(status or 0))
            if status != 200
            else None
        ),
    )

    companyfacts_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json"
    status, headers, raw, error = fetch_with_error(reader, companyfacts_url)
    facts = json_body(raw) if status == 200 else {}
    namespaces = list((facts.get("facts") or {}).keys())
    standard = (facts.get("facts") or {}).get("us-gaap", {})
    selected = {}
    for concept in (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "Assets",
        "StockholdersEquity",
        "CommonStockDividendsPerShareDeclared",
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
    ):
        value = standard.get(concept)
        if value:
            selected[concept] = {
                "label": value.get("label"),
                "units": list((value.get("units") or {}).keys()),
            }
    emit(
        "sec_companyfacts",
        "PASS" if status == 200 and selected else "FAIL",
        http_status=status,
        entity_name=facts.get("entityName"),
        namespaces=namespaces,
        selected_concepts=selected,
        request=sec_request_record(reader, companyfacts_url, "application/json, text/plain, */*"),
        failure=(
            {"error": error}
            if error
            else response_failure(headers, raw, int(status or 0))
            if status != 200
            else None
        ),
    )

    filing_index_url = (
        "https://www.sec.gov/Archives/edgar/data/723125/000072312526000015/index.json"
    )
    status, headers, raw, error = fetch_with_error(reader, filing_index_url)
    index_payload = json_body(raw) if status == 200 else {}
    index_items = ((index_payload.get("directory") or {}).get("item")) or []
    emit(
        "sec_filing_index:10q_2026_q3",
        "PASS"
        if status == 200 and index_items
        else ("FAIL" if error else blocked_or_failed(int(status or 0))),
        http_status=status,
        item_count=len(index_items),
        request=sec_request_record(reader, filing_index_url, "application/json, text/plain, */*"),
        failure=(
            {"error": error}
            if error
            else response_failure(headers, raw, int(status or 0))
            if status != 200
            else None
        ),
    )

    for label, accession, document in (
        ("10q_2026_q3", "000072312526000015", "mu-20260528.htm"),
        ("10k_2025", "000072312525000028", "mu-20250828.htm"),
    ):
        url = f"https://www.sec.gov/Archives/edgar/data/723125/{accession}/{document}"
        status, headers, raw, error = fetch_with_error(reader, url, accept="text/html")
        names = sorted(set(re.findall(r"mu:[A-Za-z0-9_]+", raw.decode("utf-8", "replace"), re.I)))
        document_status = (
            "PASS"
            if status == 200 and raw
            else ("FAIL" if error else blocked_or_failed(int(status or 0)))
        )
        request = sec_request_record(reader, url, "text/html")
        failure = (
            {"error": error}
            if error
            else response_failure(headers, raw, int(status or 0))
            if status != 200
            else None
        )
        emit(
            f"sec_filing_document_archive:{label}",
            document_status,
            http_status=status,
            response_bytes=len(raw),
            request=request,
            failure=failure,
        )
        emit(
            f"sec_micron_custom_xbrl:{label}",
            "PASS" if status == 200 and names else document_status,
            document=label,
            http_status=status,
            custom_tag_count=len(names),
            sample=names[:12],
            request=request,
            failure=failure,
        )


def probe_nasdaq_public_site(reader: Reader) -> None:
    headers_referer = "https://www.nasdaq.com/market-activity/stocks/mu"
    query = urllib.parse.urlencode(
        {
            "assetclass": "stocks",
            "fromdate": "2026-07-01",
            "todate": "2026-07-11",
            "limit": "20",
        }
    )
    status, _, raw = reader.fetch(
        f"https://api.nasdaq.com/api/quote/MU/historical?{query}", referer=headers_referer
    )
    payload = json_body(raw) if status == 200 else {}
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    emit(
        "nasdaq_public_historical_mu",
        "PASS" if status == 200 and rows else "FAIL",
        http_status=status,
        latest_rows=rows[:3],
        note="Public website endpoint; no production API or reuse entitlement was established.",
    )

    status, _, raw = reader.fetch(
        "https://api.nasdaq.com/api/quote/MU/dividends?assetclass=stocks",
        referer=headers_referer,
    )
    payload = json_body(raw) if status == 200 else {}
    rows = ((payload.get("data") or {}).get("dividends") or {}).get("rows") or []
    emit(
        "nasdaq_public_dividends_mu",
        "PASS" if status == 200 and rows else "FAIL",
        http_status=status,
        latest_rows=rows[:4],
        note="Nasdaq states dividend history is not adjusted for stock splits.",
    )


def main() -> int:
    _RESULTS.clear()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contact",
        default=None,
        help="Real project contact email or URL included in the SEC User-Agent.",
    )
    parser.add_argument("--tushare-configured", action="store_true")
    parser.add_argument("--us-eod-configured", action="store_true")
    parser.add_argument("--openai-auth-verified", action="store_true")
    arguments = parser.parse_args()
    contact = arguments.contact or "USER_CONTACT_NOT_CONFIGURED"
    reader = Reader(contact)
    for probe in (
        probe_connectivity,
        probe_sse,
        probe_sse_pdfs,
        probe_sec,
        probe_nasdaq_public_site,
    ):
        try:
            probe(reader)
        except Exception as error:  # noqa: BLE001 - keep remaining probes running
            emit(
                probe.__name__,
                "FAIL",
                required=True,
                error=f"{type(error).__name__}: {error}",
            )

    configuration_gaps = []
    if arguments.contact is None:
        configuration_gaps.append("SEC_CONTACT_NOT_CONFIGURED")
    if not arguments.tushare_configured:
        configuration_gaps.append("TUSHARE_TOKEN_AND_CACHE_PERMISSION_NOT_VERIFIED")
    if not arguments.us_eod_configured:
        configuration_gaps.append("LICENSED_US_EOD_PROVIDER_NOT_CONFIGURED")
    if not arguments.openai_auth_verified:
        configuration_gaps.append("OPENAI_AUTH_MODEL_QUOTA_AND_TARGET_REGION_NOT_VERIFIED")

    warnings = [
        "SSE_AND_NASDAQ_PUBLIC_WEBSITE_ENDPOINTS_ARE_FEASIBILITY_CROSS_CHECKS_ONLY",
        "PUBLIC_ENDPOINT_REACHABILITY_DOES_NOT_ESTABLISH_API_AUTHORIZATION_OR_PRODUCTION_AVAILABILITY",
    ]
    summary = build_summary(
        list(_RESULTS),
        configuration_gaps=configuration_gaps,
        warnings=warnings,
    )
    summary["exit_code"] = exit_code_for_status(summary["overall_status"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
