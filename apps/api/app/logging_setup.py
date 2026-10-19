import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        if current_id := request_id.get():
            data["request_id"] = current_id
        data.update(getattr(record, "fields", {}))
        # Deliberately omit exception text and tracebacks: upstream errors can contain credentials.
        return json.dumps(data, ensure_ascii=False)


def configure_logging() -> None:
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logging.getLogger("ossapi").setLevel(logging.WARNING)
