from typing import Any

import httpx


class PrometheusClient:
    def __init__(self, base_url: str | None):
        self.base_url = base_url.rstrip("/") if base_url else None

    async def status(self) -> dict[str, Any]:
        if not self.base_url:
            return {"configured": False, "targets": []}

        queries = {
            "service": 'max by (job, instance) (up{job=~"api|loki|prometheus"})',
            "probe": 'max by (monitor_name, instance) (probe_success{job=~"blackbox-.+"})',
        }
        targets: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=5) as client:
            for kind, query in queries.items():
                response = await client.get(
                    f"{self.base_url}/api/v1/query", params={"query": query}
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != "success":
                    raise RuntimeError("Prometheus query failed")
                for sample in payload.get("data", {}).get("result", []):
                    labels = sample.get("metric", {})
                    value = float(sample.get("value", [0, "0"])[1])
                    targets.append(
                        {
                            "name": labels.get("monitor_name") or labels.get("job") or "unknown",
                            "instance": labels.get("instance", ""),
                            "kind": kind,
                            "available": value == 1,
                        }
                    )
        return {"configured": True, "targets": targets}
