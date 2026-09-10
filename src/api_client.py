import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config


class APIFootballError(RuntimeError):
    pass


def _is_rate_limited(errors) -> bool:
    """API-Football returns HTTP 200 with a populated `errors` field for
    per-minute rate-limit violations (confirmed live: {"rateLimit": "Too many
    requests..."}), not an HTTP 429 -- so this must be detected from the body,
    separately from the status-code retry path."""
    if isinstance(errors, dict):
        if "rateLimit" in errors:
            return True
        return any("rate limit" in str(v).lower() for v in errors.values())
    if isinstance(errors, list):
        return any("rate limit" in str(e).lower() for e in errors)
    return False


class APIFootballClient:
    # Confirmed via response headers: x-ratelimit-limit=300 (per minute,
    # separate from the 7500/day quota). Proactively throttling to stay
    # comfortably under this avoids tripping it in the first place, rather
    # than relying purely on reactive retry-after-failure.
    MIN_REQUEST_INTERVAL = 0.25  # ~240/min

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        raw_dir: Path = None,
        max_retries: int = 5,
        backoff_base: float = 1.5,
        timeout: float = 15.0,
        session: requests.Session = None,
    ):
        self.api_key = api_key or config.API_FOOTBALL_KEY
        if not self.api_key:
            raise APIFootballError(
                "API_FOOTBALL_KEY is not set — copy .env.example to .env and fill it in."
            )
        self.base_url = (base_url or config.API_FOOTBALL_BASE_URL).rstrip("/")
        self.raw_dir = raw_dir or config.RAW_DIR
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self.session = session or requests.Session()
        self._last_request_at = 0.0

    def _cache_path(self, cache_key: str) -> Path:
        return self.raw_dir / f"{cache_key}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def get(self, path: str, params: dict, cache_key: str, force_refresh: bool = False) -> dict:
        cache_path = self._cache_path(cache_key)
        if cache_path.exists() and not force_refresh:
            return json.loads(cache_path.read_text())

        url = f"{self.base_url}{path}"
        headers = {"x-apisports-key": self.api_key}

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                print(
                    f"[api_client] attempt {attempt}/{self.max_retries} network error: {exc}",
                    file=sys.stderr,
                )
                self._sleep_backoff(attempt, None)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = APIFootballError(
                    f"HTTP {resp.status_code} from {url}: {resp.text[:200]}"
                )
                print(
                    f"[api_client] attempt {attempt}/{self.max_retries} retryable status {resp.status_code}",
                    file=sys.stderr,
                )
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue

            if resp.status_code >= 400:
                raise APIFootballError(
                    f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
                )

            body = resp.json()
            if _is_rate_limited(body.get("errors")):
                # HTTP 200 but rate-limited -- must NOT be cached (a cached
                # rate-limit error would poison every future run for this
                # cache_key until --force-refresh). Retryable, same as 429.
                last_error = APIFootballError(f"rate limited: {body.get('errors')}")
                print(
                    f"[api_client] attempt {attempt}/{self.max_retries} rate limited, backing off",
                    file=sys.stderr,
                )
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue

            envelope = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "url": resp.url,
                "params": params,
                "status_code": resp.status_code,
                "response": body,
            }
            self._write_cache(cache_path, envelope)
            return envelope

        raise APIFootballError(
            f"Exhausted {self.max_retries} retries fetching {url}: {last_error}"
        )

    def _sleep_backoff(self, attempt: int, retry_after: str) -> None:
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        delay = min(self.backoff_base ** attempt, 30) + random.uniform(0, 0.5)
        time.sleep(delay)

    @staticmethod
    def _write_cache(cache_path: Path, envelope: dict) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False))
        os.replace(tmp_path, cache_path)

    def get_league_coverage(self, league_id: int, season: int, force_refresh: bool = False) -> dict:
        return self.get(
            "/leagues",
            {"id": league_id, "season": season},
            cache_key=f"leagues/{league_id}_{season}",
            force_refresh=force_refresh,
        )

    def get_fixtures(self, league_id: int, season: int, force_refresh: bool = False) -> dict:
        """Fetch a full season's fixtures via /fixtures?league=&season=.

        Not expected to paginate for this query shape (a full league-season of
        fixtures normally comes back as one page), but defensively loops on
        `paging.total` rather than assuming. Raises immediately on a non-empty
        `errors` field -- unlike coverage_audit, a missing/broken fixtures page
        is a real ingestion failure, not an expected data gap.
        """
        items = []
        warnings = []
        page = 1
        fetched_at = None
        while True:
            cache_key = f"fixtures/{league_id}_{season}" if page == 1 else f"fixtures/{league_id}_{season}_p{page}"
            envelope = self.get(
                "/fixtures",
                {"league": league_id, "season": season, "page": page} if page > 1 else {"league": league_id, "season": season},
                cache_key=cache_key,
                force_refresh=force_refresh,
            )
            fetched_at = fetched_at or envelope.get("fetched_at")
            payload = envelope.get("response", {})
            errors = payload.get("errors")
            if errors:
                raise APIFootballError(
                    f"fixtures fetch errors for league={league_id} season={season} page={page}: {errors}"
                )
            items.extend(payload.get("response", []))
            paging = payload.get("paging") or {}
            total_pages = paging.get("total", 1)
            current_page = paging.get("current", page)
            if total_pages and total_pages > current_page:
                page = current_page + 1
                continue
            break

        return {"items": items, "warnings": warnings, "fetched_at": fetched_at, "pages_fetched": page}

    def get_team_fixtures(self, team_id: int, season: int, force_refresh: bool = False) -> dict:
        """Every fixture a club played in a season, across ALL competitions
        (/fixtures?team=&season=): league, domestic cups, European ties,
        friendlies. Used for rest/congestion so a midweek Champions League
        game counts. Same envelope/paging handling as get_fixtures."""
        items = []
        page = 1
        fetched_at = None
        while True:
            cache_key = f"fixtures/team_{team_id}_{season}" if page == 1 else f"fixtures/team_{team_id}_{season}_p{page}"
            params = {"team": team_id, "season": season}
            if page > 1:
                params["page"] = page
            envelope = self.get("/fixtures", params, cache_key=cache_key, force_refresh=force_refresh)
            fetched_at = fetched_at or envelope.get("fetched_at")
            payload = envelope.get("response", {})
            errors = payload.get("errors")
            if errors:
                raise APIFootballError(f"team fixtures fetch errors for team={team_id} season={season}: {errors}")
            items.extend(payload.get("response", []))
            paging = payload.get("paging") or {}
            if paging.get("total", 1) > paging.get("current", page):
                page = paging.get("current", page) + 1
                continue
            break
        return {"items": items, "fetched_at": fetched_at, "pages_fetched": page}

    def get_fixture_statistics(self, fixture_id: int, force_refresh: bool = False) -> dict:
        """Fetch /fixtures/statistics?fixture=. Confirmed non-paginated, but an
        empty response (0 items) is a legitimate non-error outcome for some
        older/edge-case fixtures -- callers must handle len(items) != 2
        themselves, not treat it as fatal."""
        envelope = self.get(
            "/fixtures/statistics",
            {"fixture": fixture_id},
            cache_key=f"fixture_statistics/{fixture_id}",
            force_refresh=force_refresh,
        )
        payload = envelope.get("response", {})
        errors = payload.get("errors")
        if errors:
            raise APIFootballError(f"fixture statistics fetch errors for fixture={fixture_id}: {errors}")
        return {"items": payload.get("response", []), "fetched_at": envelope.get("fetched_at")}

    def get_injuries(self, league_id: int, season: int, force_refresh: bool = False) -> dict:
        """Fetch /injuries?league=&season= -- one call returns ALL injury
        records for that league-season, already tagged to the specific
        fixture each one affected."""
        items = []
        page = 1
        fetched_at = None
        while True:
            cache_key = f"injuries/{league_id}_{season}" if page == 1 else f"injuries/{league_id}_{season}_p{page}"
            envelope = self.get(
                "/injuries",
                {"league": league_id, "season": season, "page": page} if page > 1 else {"league": league_id, "season": season},
                cache_key=cache_key,
                force_refresh=force_refresh,
            )
            fetched_at = fetched_at or envelope.get("fetched_at")
            payload = envelope.get("response", {})
            errors = payload.get("errors")
            if errors:
                raise APIFootballError(f"injuries fetch errors for league={league_id} season={season} page={page}: {errors}")
            items.extend(payload.get("response", []))
            paging = payload.get("paging") or {}
            total_pages = paging.get("total", 1)
            current_page = paging.get("current", page)
            if total_pages and total_pages > current_page:
                page = current_page + 1
                continue
            break
        return {"items": items, "fetched_at": fetched_at, "pages_fetched": page}

    def get_lineups(self, fixture_id: int, force_refresh: bool = False) -> dict:
        """Fetch /fixtures/lineups?fixture=. Confirmed non-paginated; same
        "empty response is not an error" caveat as get_fixture_statistics."""
        envelope = self.get(
            "/fixtures/lineups",
            {"fixture": fixture_id},
            cache_key=f"lineups/{fixture_id}",
            force_refresh=force_refresh,
        )
        payload = envelope.get("response", {})
        errors = payload.get("errors")
        if errors:
            raise APIFootballError(f"lineups fetch errors for fixture={fixture_id}: {errors}")
        return {"items": payload.get("response", []), "fetched_at": envelope.get("fetched_at")}

    def get_odds(self, fixture_id: int, cache_suffix: str, force_refresh: bool = False) -> dict:
        """Fetch /odds?fixture= (pre-match odds, all bookmakers/markets).
        Paginated by bookmaker set. cache_suffix must identify the snapshot
        window (e.g. "24h") so each window is fetched live exactly once and
        later re-runs inside the same window reuse the cache instead of
        burning quota. An empty response is a legitimate outcome (provider
        publishes odds only inside its own pre-match window)."""
        items = []
        page = 1
        fetched_at = None
        while True:
            key = f"odds/{fixture_id}_{cache_suffix}" if page == 1 else f"odds/{fixture_id}_{cache_suffix}_p{page}"
            envelope = self.get(
                "/odds",
                {"fixture": fixture_id, "page": page} if page > 1 else {"fixture": fixture_id},
                cache_key=key,
                force_refresh=force_refresh,
            )
            fetched_at = fetched_at or envelope.get("fetched_at")
            payload = envelope.get("response", {})
            errors = payload.get("errors")
            if errors:
                raise APIFootballError(f"odds fetch errors for fixture={fixture_id}: {errors}")
            items.extend(payload.get("response", []))
            paging = payload.get("paging") or {}
            total_pages = paging.get("total", 1)
            current_page = paging.get("current", page)
            if total_pages and total_pages > current_page:
                page = current_page + 1
                continue
            break
        return {"items": items, "fetched_at": fetched_at, "pages_fetched": page}
