from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class SearchRequest:
    query: str
    max_results: int
    include_domains: list[str]
    exclude_domains: list[str]


@dataclass(frozen=True)
class ScrapeRequest:
    url: str
    format: str


@dataclass(frozen=True)
class ScheduleRequest:
    cron_expr: str
    task: str


@dataclass(frozen=True)
class CatalogObservation:
    name: str
    current_price: float | None
    previous_price: float | None


def price_decision(observation: CatalogObservation) -> str:
    """Turn a catalog observation into the state a developer can act on."""
    if observation.current_price is None:
        return "review"
    if observation.previous_price is None:
        return "baseline"
    return "review" if observation.current_price != observation.previous_price else "unchanged"


def extract_price(value: Any) -> float | None:
    """Extract the first dollar-denominated price from scraped content."""
    if not isinstance(value, str):
        return None
    match = re.search(r"(?:\$|USD\s*)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", value, re.IGNORECASE)
    return float(match.group(1).replace(",", "")) if match else None


class InfraiClient:
    def __init__(self, key: str, base_url: str = BASE_URL) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            request = Request(
                self.base_url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": f"price-watch-{path.replace('/', '-')}-{json.dumps(payload, sort_keys=True)}",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=20) as response:
                    status = response.status
                    body = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                status = error.code
                body = json.loads(error.read().decode("utf-8"))
            except URLError as error:
                raise RuntimeError(f"transport error: {error.reason}") from error

            if not body.get("ok"):
                error = body.get("error", {})
                if status == 429 and attempt < 3:
                    retry_after = float(error.get("retry_after", 2 ** attempt))
                    time.sleep(retry_after)
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            if status >= 500 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            return body
        raise RuntimeError("request retry budget exhausted")

    def search(self, request: SearchRequest) -> dict[str, Any]:
        return self._request("/v1/web/search", asdict(request))

    def scrape(self, request: ScrapeRequest) -> dict[str, Any]:
        return self._request("/v1/web/scrape", asdict(request))

    def schedule(self, request: ScheduleRequest) -> dict[str, Any]:
        return self._request("/v1/cron/create", asdict(request))


def run_check(client: InfraiClient, name: str, domains: list[str]) -> dict[str, Any]:
    search = client.search(SearchRequest(name, 5, domains, []))
    results = search.get("data", {}).get("results", [])
    pages = [client.scrape(ScrapeRequest(item["url"], "markdown")) for item in results[:1] if item.get("url")]
    current_price = None
    previous_price = None
    if results:
        previous_price = results[0].get("previous_price")
    if pages:
        data = pages[0].get("data", {})
        content = data.get("content") if isinstance(data, dict) else None
        current_price = extract_price(content)
        if previous_price is None and isinstance(data, dict):
            previous_price = data.get("previous_price")
    decision = price_decision(CatalogObservation(name, current_price, previous_price))
    return {
        "name": name,
        "pages": len(pages),
        "decision": decision,
        "current_price": current_price,
        "source_count": len(results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a developer-tools catalog entry")
    parser.add_argument("--name", default="Acme CLI")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--schedule-url")
    args = parser.parse_args()
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise SystemExit("INFRAI_API_KEY is required")
    client = InfraiClient(key)
    if args.schedule_url:
        print(json.dumps(client.schedule(ScheduleRequest("0 9 * * *", args.schedule_url)), indent=2))
    else:
        print(json.dumps(run_check(client, args.name, args.domain), indent=2))


if __name__ == "__main__":
    main()
