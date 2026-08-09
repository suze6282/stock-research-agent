import logging as stdlib_logging
import re
import sys
from collections.abc import Mapping
from typing import cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger

from stock_research_agent.config import AppEnvironment, Settings

_REDACTED_VALUE = "***"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "signature",
    "token",
)
_POSTGRESQL_CREDENTIALS = re.compile(
    r"(?P<prefix>postgresql(?:\+[a-zA-Z0-9_]+)?://[^\s:/@]+:)(?P<password>[^\s@]+)(?=@)",
    re.IGNORECASE,
)
_HTTP_USERINFO = re.compile(
    r"(?P<prefix>https?://[^\s:/@]+:)(?P<password>[^\s@]+)(?=@)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?P<prefix>[?&](?:api[_-]?key|access[_-]?token|token|secret|signature)=)"
    r"(?P<value>[^&#\s]+)",
    re.IGNORECASE,
)


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED_VALUE
                if any(
                    part in re.sub(r"[^a-z0-9]+", "_", str(key).casefold())
                    for part in _SENSITIVE_KEY_PARTS
                )
                else _redact_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        redacted = _POSTGRESQL_CREDENTIALS.sub(r"\g<prefix>***", value)
        redacted = _HTTP_USERINFO.sub(r"\g<prefix>***", redacted)
        return _SENSITIVE_QUERY_VALUE.sub(r"\g<prefix>***", redacted)
    return value


def redact_sensitive_data(event_dict: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _redact_value(event_dict))


def _add_service(service: str) -> structlog.typing.Processor:
    def processor(
        _logger: FilteringBoundLogger,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict["service"] = service
        return event_dict

    return processor


def _redact_event(
    _logger: FilteringBoundLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    return redact_sensitive_data(dict(event_dict))


def configure_logging(settings: Settings) -> None:
    level = getattr(stdlib_logging, settings.log_level.upper(), stdlib_logging.INFO)
    renderer: structlog.typing.Processor
    if settings.app_env is AppEnvironment.DEVELOPMENT:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_service(settings.app_name),
            _redact_event,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
