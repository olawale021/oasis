"""Point-in-time squad market values from the Transfermarkt datasets
(dcaribou/transfermarkt-datasets, public CSVs, no account needed).

For every fixture in the live leagues (played since 2017 or kicking off in
the next 30 days) and each of its two clubs, the squad value as of kickoff:
  * a player belongs to the club if their LATEST valuation dated on or
    before kickoff was recorded at that club (valuation rows carry the
    club at valuation time, so membership is point-in-time with no
    lineup data needed -- which is what makes MLS work too)
  * that latest valuation must be within MAX_STALE_DAYS of kickoff, or
    the player is treated as gone (retired / left without re-valuation)
  * squad value = sum of the top TOP_N such valuations
  * fewer than MIN_PLAYERS valued players (the dataset profiles first-tier
    squads, so a promoted club arrives thin) = no row, so the feature reads
    0.0 (unknown) instead of a tiny squad

Clubs are matched to API-Football team ids by normalised name within the
club's country, with explicit OVERRIDES for the ones that differ; any
unmatched club that appears in a live-league fixture is a hard error, so a
promoted club never silently drops out.

    python3 src/ingest_squad_values.py --dry-run     # match clubs, write nothing
    python3 src/ingest_squad_values.py               # download if stale, compute, write
"""

import argparse
import csv
import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import db
import leagues

BASE_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
RAW_DIR = config.DATA_DIR / "raw" / "transfermarkt"
TABLES = ["competitions", "clubs", "player_valuations"]
REFRESH_DAYS = 7
TOP_N = 25
MAX_STALE_DAYS = 540
MIN_PLAYERS = 15  # fewer valued players = coverage gap (promoted club): treat as unknown, not as a tiny squad
FIRST_SEASON = 2017
HORIZON_DAYS = 30
COUNTRY_BY_LEAGUE = {39: "England", 140: "Spain", 135: "Italy", 78: "Germany", 253: "United States"}

# API-Football team_id -> Transfermarkt club_id, where names do not line up.
OVERRIDES = {}

GENERIC = {
    "fc", "cf", "sc", "afc", "ac", "as", "ss", "us", "ssc", "ud", "cd", "rcd", "sd", "club", "de", "del", "di", "e", "v",
    "calcio", "football", "soccer", "1", "04", "05", "09", "1846", "1899", "1900", "1904", "1909", "1910", "1919",
    "tsg", "vfb", "vfl", "fsv", "sv", "bsc", "1fc", "spvgg", "fk", "sgl", "bv", "balompie", "spa", "srl", "ltd", "the",
}
ALIASES = {
    "wolves": "wolverhampton", "spurs": "tottenham", "man": "manchester", "utd": "united", "inter": "internazionale",
    "gladbach": "monchengladbach", "brom": "bromwich", "koln": "cologne", "köln": "cologne", "nuremberg": "nurnberg", "bayern": "bayern", "munich": "munchen",
    "athletic": "athletic", "atletico": "atletico", "hellas": "hellas", "psv": "psv",
}


def norm_tokens(name: str) -> set:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace(".", "")  # "D.C. United" -> "dc united"
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = set()
    for t in s.split():
        t = ALIASES.get(t, t)
        if t not in GENERIC:
            toks.add(t)
    return toks


def download_if_stale(name: str) -> Path:
    path = RAW_DIR / f"{name}.csv.gz"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists() and (time.time() - path.stat().st_mtime) < REFRESH_DAYS * 86400:
        return path
    url = f"{BASE_URL}/{name}.csv.gz"
    print(f"downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; oasis-pipeline/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(path.with_suffix(".tmp"), "wb") as out:
            out.write(resp.read())
        path.with_suffix(".tmp").replace(path)
    except Exception as exc:
        if path.exists():
            # Refresh failed (the host 403s some address ranges): keep the
            # copy we have -- it can also be rsynced from the laptop.
            print(f"  download failed ({exc}); using existing {path.name}", file=sys.stderr)
        else:
            raise
    return path


def read_csv(name: str):
    with gzip.open(download_if_stale(name), "rt", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def load_clubs() -> dict:
    """tm_club_id -> {name, country}. Country via the club's domestic
    competition for clubs.csv; clubs only seen in valuation rows (second
    tiers, which the dataset does not profile) get country '' and are
    matched in a country-less fallback pass."""
    country_of_comp = {r["competition_id"]: r["country_name"] for r in read_csv("competitions")}
    clubs = {}
    for r in read_csv("clubs"):
        clubs[int(r["club_id"])] = {"name": r["name"], "country": country_of_comp.get(r["domestic_competition_id"], "")}
    for r in read_csv("player_valuations"):
        try:
            cid = int(r["current_club_id"] or 0)
        except ValueError:
            continue
        if cid and cid not in clubs and r["current_club_name"] and r["current_club_name"] != "Unknown":
            clubs[cid] = {"name": r["current_club_name"], "country": ""}
    return clubs


def live_teams(conn) -> dict:
    """team_id -> {name, country} for every club in a live-league fixture since FIRST_SEASON."""
    out = {}
    for league_id, country in COUNTRY_BY_LEAGUE.items():
        rows = conn.execute(
            "SELECT DISTINCT t.team_id, t.name FROM teams t JOIN fixtures f"
            " ON t.team_id IN (f.home_team_id, f.away_team_id) WHERE f.league_id = ? AND f.season >= ?",
            (league_id, FIRST_SEASON),
        ).fetchall()
        for r in rows:
            out[r["team_id"]] = {"name": r["name"], "country": country}
    return out


def match_clubs(teams: dict, clubs: dict) -> tuple[dict, list]:
    """team_id -> (tm_club_id, tm_name, method). Unmatched list for the error."""
    reserve = re.compile(r"\b(II|III|B|U1\d|U2\d|Youth|Reserves?)\b")
    by_country = defaultdict(list)
    for cid, c in clubs.items():
        if reserve.search(c["name"]):
            continue  # reserve / youth sides share the first team's name
        by_country[c["country"]].append((cid, c["name"], norm_tokens(c["name"])))
    mapping, unmatched = {}, []
    for team_id, t in teams.items():
        if team_id in OVERRIDES:
            cid = OVERRIDES[team_id]
            mapping[team_id] = (cid, clubs[cid]["name"], "override")
            continue
        toks = norm_tokens(t["name"])
        scored = []
        for cid, cname, ctoks in by_country[t["country"]]:
            if not toks or not ctoks:
                continue
            inter = len(toks & ctoks)
            if inter == 0:
                continue
            scored.append((inter / len(toks | ctoks), inter, cid, cname))
        scored.sort(reverse=True)
        if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
            # Fallback: clubs with no country (valuation-only), unique best >= 0.5.
            fb = []
            for cid, cname, ctoks in by_country[""]:
                inter = len(toks & ctoks)
                if inter:
                    fb.append((inter / len(toks | ctoks), inter, cid, cname))
            fb.sort(reverse=True)
            if fb and fb[0][0] >= 0.5 and (len(fb) == 1 or fb[0][0] > fb[1][0]):
                scored = [fb[0]]
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            mapping[team_id] = (scored[0][2], scored[0][3], f"name {scored[0][0]:.2f}")
        else:
            unmatched.append((team_id, t["name"], [s[3] for s in scored[:3]]))
    return mapping, unmatched


def fixtures_to_value(conn) -> list:
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT fixture_id, kickoff_utc, home_team_id, away_team_id FROM fixtures"
        " WHERE league_id IN ({}) AND season >= ? AND kickoff_utc <= ? ORDER BY kickoff_utc".format(
            ", ".join(str(i) for i in COUNTRY_BY_LEAGUE)),
        (FIRST_SEASON, (now + timedelta(days=HORIZON_DAYS)).isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def compute_values(fixtures: list, mapping: dict) -> list:
    """One chronological sweep over valuations and fixtures."""
    wanted_clubs = {cid for cid, _, _ in mapping.values()}
    team_of_club = defaultdict(list)
    for team_id, (cid, _, _) in mapping.items():
        team_of_club[cid].append(team_id)

    vals = []
    for r in read_csv("player_valuations"):
        try:
            vals.append((r["date"], int(r["player_id"]), int(r["current_club_id"] or 0), float(r["market_value_in_eur"] or 0)))
        except ValueError:
            continue
    vals.sort()
    latest = {}                      # player -> (date, club, value)
    members = defaultdict(dict)      # club -> {player: (date, value)}
    out = []
    vi = 0
    computed_at = datetime.now(timezone.utc).isoformat()
    for f in fixtures:
        as_of = f["kickoff_utc"][:10]
        while vi < len(vals) and vals[vi][0] <= as_of:
            date, pid, club, value = vals[vi]
            vi += 1
            prev = latest.get(pid)
            if prev and prev[1] in members and pid in members[prev[1]]:
                del members[prev[1]][pid]
            latest[pid] = (date, club, value)
            if club in wanted_clubs:
                members[club][pid] = (date, value)
        stale_before = (datetime.fromisoformat(as_of) - timedelta(days=MAX_STALE_DAYS)).strftime("%Y-%m-%d")
        for team_id in (f["home_team_id"], f["away_team_id"]):
            m = mapping.get(team_id)
            if not m:
                continue
            squad = sorted((v for d, v in members[m[0]].values() if d >= stale_before and v > 0), reverse=True)[:TOP_N]
            if len(squad) >= MIN_PLAYERS:
                out.append({"fixture_id": f["fixture_id"], "team_id": team_id, "value_eur": sum(squad),
                            "n_players": len(squad), "as_of": as_of, "computed_at": computed_at})
    return out


def main() -> None:
    global MIN_PLAYERS
    parser = argparse.ArgumentParser(description="Transfermarkt point-in-time squad values per fixture.")
    parser.add_argument("--dry-run", action="store_true", help="match clubs and report; write nothing")
    parser.add_argument("--min-players", type=int, default=MIN_PLAYERS, help=f"coverage guard (default {MIN_PLAYERS})")
    args = parser.parse_args()
    MIN_PLAYERS = args.min_players
    started = datetime.now(timezone.utc)
    conn = db.get_connection()
    db.init_db(conn)

    clubs = load_clubs()
    teams = live_teams(conn)
    mapping, unmatched = match_clubs(teams, clubs)
    print(f"clubs: {len(teams)} live-league teams, {len(mapping)} matched, {len(unmatched)} unmatched", file=sys.stderr)
    for team_id, name, cands in unmatched:
        print(f"  UNMATCHED {team_id} {name!r} candidates={cands}", file=sys.stderr)
    if args.dry_run:
        for team_id, (cid, cname, how) in sorted(mapping.items(), key=lambda kv: kv[1][1]):
            if not how.startswith("name 1.00"):
                print(f"  {team_id:>5} {teams[team_id]['name']:<28} -> {cname:<32} [{how}]", file=sys.stderr)
        return
    if unmatched:
        raise SystemExit("unmatched clubs -- add OVERRIDES entries (team_id -> tm club_id) and re-run")

    fixtures = fixtures_to_value(conn)
    rows = compute_values(fixtures, mapping)
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR REPLACE INTO tm_club_map (team_id, tm_club_id, tm_name, method, mapped_at) VALUES (?, ?, ?, ?, ?)",
        [(t, c, n, h, now) for t, (c, n, h) in mapping.items()],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO squad_values (fixture_id, team_id, value_eur, n_players, as_of, computed_at)"
        " VALUES (:fixture_id, :team_id, :value_eur, :n_players, :as_of, :computed_at)", rows,
    )
    conn.commit()
    conn.close()
    finished = datetime.now(timezone.utc)
    summary = {"fixtures": len(fixtures), "rows_written": len(rows), "teams_mapped": len(mapping)}
    config.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATUS_DIR / "ingest_squad_values_status.json").write_text(json.dumps({
        "success": True, "refreshed_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000), "counts": summary}, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
