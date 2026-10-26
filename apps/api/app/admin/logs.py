import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, Field, field_validator

SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class LogSearch(BaseModel):
    start: datetime
    end: datetime
    services: list[str] = []
    levels: list[Literal["DEBUG", "INFO", "WARNING", "ERROR"]] = []
    event: str | None = None
    request_id: str | None = None
    text: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=200, ge=1)

    @field_validator("services")
    @classmethod
    def safe_services(cls, values: list[str]) -> list[str]:
        if len(values) > 20 or any(not SAFE_VALUE.fullmatch(value) for value in values):
            raise ValueError("Invalid service filter")
        return values

    @field_validator("event", "request_id")
    @classmethod
    def safe_exact_filter(cls, value: str | None) -> str | None:
        if value is not None and not SAFE_VALUE.fullmatch(value):
            raise ValueError("Invalid exact filter")
        return value


class LokiClient:
    def __init__(
        self,
        url: str | None,
        *,
        tenant_id: str | None,
        environment: str,
        max_range_days: int,
        max_limit: int,
    ):
        self.url = url.rstrip("/") if url else None
        self.tenant_id = tenant_id
        self.environment = environment
        self.max_range = timedelta(days=max_range_days)
        self.max_limit = max_limit

    async def search(self, request: LogSearch) -> list[dict]:
        if self.url is None:
            raise RuntimeError("Log storage is not configured")
        start = request.start.astimezone(UTC)
        end = request.end.astimezone(UTC)
        if end <= start or end - start > self.max_range:
            raise ValueError("Invalid log time range")
        if request.limit > self.max_limit:
            raise ValueError("Log result limit is too large")
        query = self._query(request)
        headers = {"X-Scope-OrgID": self.tenant_id} if self.tenant_id else {}
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{self.url}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(int(start.timestamp() * 1_000_000_000)),
                    "end": str(int(end.timestamp() * 1_000_000_000)),
                    "limit": request.limit,
                    "direction": "backward",
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        entries = []
        for stream in payload.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for timestamp, line in stream.get("values", []):
                try:
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        parsed = {"message": line}
                except (json.JSONDecodeError, TypeError):
                    parsed = {"message": line}
                entries.append(
                    {
                        "timestamp": datetime.fromtimestamp(int(timestamp) / 1_000_000_000, UTC),
                        "service": labels.get("service_name") or labels.get("service") or "unknown",
                        "level": parsed.get("level") or labels.get("level") or "INFO",
                        "event": parsed.get("event"),
                        "message": parsed.get("message") or parsed.get("event") or line,
                        "request_id": parsed.get("request_id"),
                        "fields": {
                            key: value
                            for key, value in parsed.items()
                            if key not in {"time", "level", "event", "message", "request_id"}
                        },
                        "raw": line,
                    }
                )
        entries.sort(key=lambda item: item["timestamp"], reverse=True)
        return entries[: request.limit]

    def _query(self, request: LogSearch) -> str:
        labels = [f"environment={json.dumps(self.environment)}"]
        if request.services:
            pattern = "|".join(re.escape(value) for value in request.services)
            labels.append(f"service_name=~{json.dumps(pattern)}")
        query = "{" + ",".join(labels) + "} | json"
        if request.levels:
            pattern = "|".join(request.levels)
            query += f" | level=~{json.dumps(pattern)}"
        if request.event:
            query += f" | event={json.dumps(request.event)}"
        if request.request_id:
            query += f" | request_id={json.dumps(request.request_id)}"
        if request.text:
            query += f" |={json.dumps(request.text)}"
        return query
