"""Schedules Direct JSON API (20141201) client.

Handles authentication, lineup discovery, schedule retrieval, and program metadata fetching.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "https://json.schedulesdirect.org/20141201"
USER_AGENT = "hdhr-open/0.1"
DEFAULT_TIMEOUT = 30.0
_SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class SchedulesDirectError(Exception):
    """Raised when a Schedules Direct API request fails."""

    def __init__(self, message: str, code: int | None = None, response_data: Any = None):
        super().__init__(message)
        self.detail = message
        self.code = code
        self.response_data = response_data


def hash_password(password: str) -> str:
    """Return lowercase SHA-1 hex digest of the password, or return as-is if already a 40-char hex string."""
    if _SHA1_RE.match(password.strip()):
        return password.strip().lower()
    return hashlib.sha1(password.strip().encode("utf-8")).hexdigest().lower()


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if token:
        headers["token"] = token
    return headers


def _check_response_for_errors(data: Any) -> None:
    if isinstance(data, dict):
        # Schedules Direct error response format: {"response": "ERR", "code": 4003, "message": "..."}
        # or {"code": 4003, "message": "..."} when code != 0
        code = data.get("code")
        response_type = data.get("response")
        if response_type == "ERR" or (isinstance(code, int) and code != 0 and code != 2000):
            message = data.get("message") or f"Schedules Direct error code {code}"
            raise SchedulesDirectError(message, code=code, response_data=data)


async def authenticate(username: str, password_or_hash: str) -> dict[str, Any]:
    """Authenticate with Schedules Direct and obtain a 24-hour session token."""
    if not username or not password_or_hash:
        raise SchedulesDirectError("Username and password are required")

    hashed_pw = hash_password(password_or_hash)
    payload = {
        "username": username.strip(),
        "password": hashed_pw,
    }

    url = f"{API_BASE_URL}/token"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=_headers())
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)

    token = data.get("token")
    if not token:
        raise SchedulesDirectError("Authentication response did not contain a token", response_data=data)

    return {
        "token": token,
        "serverID": data.get("serverID"),
        "datetime": data.get("datetime"),
        "message": data.get("message"),
    }


async def get_status(token: str) -> dict[str, Any]:
    """Fetch user account status, expiration, and active lineups."""
    url = f"{API_BASE_URL}/status"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)
    return data


async def get_headends(token: str, country: str, postal_code: str) -> list[dict[str, Any]]:
    """Fetch available headends and lineups for a given country and postal code."""
    url = f"{API_BASE_URL}/headends"
    params = {"country": country.strip(), "postalcode": postal_code.strip()}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)
    if isinstance(data, list):
        return data
    return []


async def add_lineup(token: str, lineup_id: str) -> dict[str, Any]:
    """Add a lineup to the user's Schedules Direct account."""
    url = f"{API_BASE_URL}/lineups/{lineup_id.strip()}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.put(url, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)
    return data


async def delete_lineup(token: str, lineup_id: str) -> dict[str, Any]:
    """Remove a lineup from the user's Schedules Direct account."""
    url = f"{API_BASE_URL}/lineups/{lineup_id.strip()}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.delete(url, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)
    return data


async def get_lineup(token: str, lineup_id: str) -> dict[str, Any]:
    """Fetch channel map and station metadata for a lineup."""
    url = f"{API_BASE_URL}/lineups/{lineup_id.strip()}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(token))
    except httpx.HTTPError as exc:
        raise SchedulesDirectError(f"HTTP request to Schedules Direct failed: {exc}") from exc

    try:
        data = resp.json()
    except Exception as exc:
        raise SchedulesDirectError(f"Invalid JSON received from Schedules Direct: {resp.text}") from exc

    _check_response_for_errors(data)
    return data


async def get_schedules(token: str, station_dates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch schedules for requested stations and dates in batches."""
    if not station_dates:
        return []

    url = f"{API_BASE_URL}/schedules"
    results: list[dict[str, Any]] = []
    batch_size = 500

    for i in range(0, len(station_dates), batch_size):
        chunk = station_dates[i : i + batch_size]
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=chunk, headers=_headers(token))
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch schedules batch: %s", exc)
            continue

        try:
            data = resp.json()
        except Exception:
            logger.warning("Invalid JSON response when fetching schedules")
            continue

        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            _check_response_for_errors(data)

    return results


async def get_programs(token: str, program_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch program metadata descriptions for a list of program IDs in batches."""
    if not program_ids:
        return []

    url = f"{API_BASE_URL}/programs"
    results: list[dict[str, Any]] = []
    batch_size = 500

    for i in range(0, len(program_ids), batch_size):
        chunk = program_ids[i : i + batch_size]
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=chunk, headers=_headers(token))
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch programs batch: %s", exc)
            continue

        try:
            data = resp.json()
        except Exception:
            logger.warning("Invalid JSON response when fetching programs")
            continue

        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            _check_response_for_errors(data)

    return results
