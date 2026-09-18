"""Measure network distance from wherever this app runs to each Supabase region.

Why this exists: page responsiveness here is roughly (queries per page x
round-trip time), and round-trip time is dominated by the physical distance
between the app and the database. That distance can only be measured from
where the app actually runs -- a developer laptop tells you nothing about
the deployed container, and this app is deployed on Streamlit Community
Cloud, which does not document which region it runs in.

Rather than infer the answer, this probes it: it opens a bare TCP connection
to each Supabase region's shared pooler endpoint and times the handshake.
One handshake is one network round trip, which is the same unit a query on
an already-open connection costs -- so these numbers are directly comparable
to db.database.measure_round_trip_latency().

No credentials and no database access are involved: this only opens and
immediately closes a TCP socket to a public hostname, and never sends a
single byte of Postgres protocol. It reveals nothing about this project and
does not require a project to exist in the region being probed.

Kept out of db/database.py deliberately -- that module owns the SQLAlchemy
engine and session, while this is pure socket work that happens to inform
where the database should live.
"""

from __future__ import annotations

import re
import socket
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

# Supabase's AWS regions, as the shared pooler hostnames
# aws-0-<region>.pooler.supabase.com. These resolve regardless of whether
# you have a project in that region, which is what makes them usable as
# neutral distance probes.
SUPABASE_REGIONS: list[tuple[str, str]] = [
    ("us-east-1", "East US (N. Virginia)"),
    ("us-east-2", "East US (Ohio)"),
    ("us-west-1", "West US (N. California)"),
    ("us-west-2", "West US (Oregon)"),
    ("ca-central-1", "Canada (Central)"),
    ("eu-west-1", "West EU (Ireland)"),
    ("eu-west-2", "West EU (London)"),
    ("eu-central-1", "Central EU (Frankfurt)"),
    ("ap-southeast-1", "Southeast Asia (Singapore)"),
    ("ap-southeast-2", "Oceania (Sydney)"),
    ("ap-northeast-1", "Northeast Asia (Tokyo)"),
    ("ap-south-1", "South Asia (Mumbai)"),
    ("sa-east-1", "South America (Sao Paulo)"),
]

_POOLER_PORT = 5432


def pooler_host(region: str) -> str:
    return f"aws-0-{region}.pooler.supabase.com"


def current_region(database_url: str | None) -> str | None:
    """The region token out of a Supabase pooler URL, or None.

    Returns only the region (e.g. "us-east-1") -- never the host, username,
    password, or any other part of the connection string, so the result is
    safe to display in the UI.
    """
    if not database_url:
        return None
    match = re.search(r"aws-\d+-([a-z]{2}-[a-z]+-\d)\.pooler\.supabase\.com", database_url)
    return match.group(1) if match else None


def configured_region() -> str | None:
    """Which region this app's own database is in, or None if not determinable.

    Resolves the connection string through the app's normal secret lookup and
    extracts only the region token from it -- the URL itself never leaves this
    function. Importing get_secret lazily keeps this module free of an
    import-time dependency on the engine layer.
    """
    from db.database import get_secret

    return current_region(get_secret("DATABASE_URL"))


def _probe_one(region: str, label: str, samples: int, timeout: float) -> dict:
    host = pooler_host(region)
    timings: list[float] = []
    for _ in range(max(1, samples)):
        try:
            started = time.perf_counter()
            sock = socket.create_connection((host, _POOLER_PORT), timeout=timeout)
            timings.append((time.perf_counter() - started) * 1000)
            sock.close()
        except OSError as exc:
            return {
                "region": region,
                "label": label,
                "ok": False,
                "median_ms": None,
                "error": type(exc).__name__,
            }
    return {
        "region": region,
        "label": label,
        "ok": True,
        "median_ms": round(statistics.median(timings), 1),
        "error": None,
    }


def probe_regions(samples: int = 3, timeout: float = 4.0) -> list[dict]:
    """Time a TCP handshake to every Supabase region, nearest first.

    Regions are probed concurrently (a handshake is latency-bound, not
    bandwidth-bound, so parallel probes to different hosts don't meaningfully
    distort each other) to keep this responsive enough for a UI button.
    Unreachable regions are returned with ok=False rather than dropped, so a
    blocked or failing region is visible instead of silently missing.
    """
    with ThreadPoolExecutor(max_workers=len(SUPABASE_REGIONS)) as pool:
        results = list(
            pool.map(
                lambda entry: _probe_one(entry[0], entry[1], samples, timeout),
                SUPABASE_REGIONS,
            )
        )
    # Reachable regions first, nearest to furthest; failures last.
    return sorted(results, key=lambda r: (not r["ok"], r["median_ms"] or float("inf")))
