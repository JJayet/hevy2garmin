"""Match Hevy workouts to existing Garmin activities by start time."""

from __future__ import annotations

import logging
from datetime import datetime

from garminconnect import Garmin

logger = logging.getLogger("hevy2garmin")

# Cache to avoid hammering Garmin API on every page load
_garmin_activities_cache: list[dict] | None = None
_cache_timestamp: float = 0
CACHE_TTL = 300  # 5 minutes


def fetch_garmin_activities(client: Garmin, count: int = 50) -> list[dict]:
    """Fetch recent Garmin activities with caching."""
    global _garmin_activities_cache, _cache_timestamp
    import time

    if _garmin_activities_cache is not None and (time.time() - _cache_timestamp) < CACHE_TTL:
        return _garmin_activities_cache

    try:
        from garmin_auth import RateLimiter
        limiter = RateLimiter(delay=1.0)
        activities = limiter.call(client.get_activities, 0, count)
        _garmin_activities_cache = activities
        _cache_timestamp = time.time()
        return activities
    except Exception as e:
        logger.warning("Could not fetch Garmin activities: %s", e)
        return []


def _parse_time(raw: str) -> datetime | None:
    """Parse various time formats to datetime."""
    if not raw:
        return None
    try:
        cleaned = raw.replace("Z", "+00:00")
        if "T" not in cleaned:
            cleaned = cleaned.replace(" ", "T")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def match_workouts_to_garmin(
    workouts: list[dict],
    garmin_activities: list[dict],
    window_minutes: int = 15,
) -> dict[str, dict]:
    """Match Hevy workouts to Garmin activities by start time.

    Returns dict mapping hevy_id → {"garmin_id": int, "garmin_name": str, "match_type": str}
    """
    matches: dict[str, dict] = {}

    for workout in workouts:
        hevy_id = workout.get("id", "")
        hevy_start_str = workout.get("start_time") or workout.get("startTime", "")
        hevy_start = _parse_time(hevy_start_str)
        if not hevy_start:
            continue

        hevy_naive = hevy_start.replace(tzinfo=None) if hevy_start.tzinfo else hevy_start

        for act in garmin_activities:
            # Use GMT time for comparison (Hevy uses UTC, Garmin local has timezone offset)
            act_start_str = act.get("startTimeGMT") or act.get("startTimeLocal", "")
            act_start = _parse_time(act_start_str)
            if not act_start:
                continue

            act_naive = act_start.replace(tzinfo=None) if act_start.tzinfo else act_start
            diff_seconds = abs((hevy_naive - act_naive).total_seconds())

            if diff_seconds < window_minutes * 60:
                matches[hevy_id] = {
                    "garmin_id": act.get("activityId"),
                    "garmin_name": act.get("activityName", ""),
                    "garmin_type": act.get("activityType", {}).get("typeKey", ""),
                    "match_type": "time_match",
                }
                break

    return matches
