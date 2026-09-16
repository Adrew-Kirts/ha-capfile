"""API client for Capfile."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiohttp

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes — /meters endpoint
# ---------------------------------------------------------------------------

@dataclass
class CapfileMeter:
    """A meter entry as returned by GET /meters."""
    prm: str
    name: str
    shared: bool = False  # True when the meter belongs to another user but is shared


# ---------------------------------------------------------------------------
# Data classes — /info endpoint
# ---------------------------------------------------------------------------

@dataclass
class CapfileCadranInfo:
    """Metadata for a single cadran as returned by /info."""
    name: str    # e.g. "BUHC"
    label: str   # e.g. "Bleu Heures Creuses"
    color: str   # e.g. "#61acf0"
    order: int   # 1-based cadran index for ordering


@dataclass
class CapfileInfo:
    """Parsed response from GET /data/{PRM}/info."""
    prm: str
    name: str                               # Site/contract name
    cadrans: dict[str, CapfileCadranInfo]   # cadran key → metadata
    prices_cts: dict[str, float]            # cadran key → price in cts/kWh
    subscription_eur_month: float           # Monthly subscription in €
    power_kva: float = 0.0                  # Subscribed power in kVA
    offer_name: str = ""                    # Tariff offer name
    injection_cadrans: dict[str, "CapfileCadranInfo"] = field(default_factory=dict)
    puissance_raccordement: float = 0.0     # Connection power in kVA (injection)

    @property
    def has_soutirage(self) -> bool:
        return bool(self.cadrans)

    @property
    def has_injection(self) -> bool:
        return bool(self.injection_cadrans)

    @property
    def cadran_names(self) -> list[str]:
        """Soutirage cadran keys in contract-defined order."""
        return sorted(self.cadrans.keys(), key=lambda c: self.cadrans[c].order)

    @property
    def injection_cadran_names(self) -> list[str]:
        """Injection cadran keys in contract-defined order."""
        return sorted(self.injection_cadrans.keys(), key=lambda c: self.injection_cadrans[c].order)

    @property
    def prices_eur(self) -> dict[str, float]:
        """Prices converted from centimes/kWh to €/kWh."""
        return {c: round(p / 100, 6) for c, p in self.prices_cts.items()}

    @property
    def cadran_labels(self) -> dict[str, str]:
        """Dict of {cadran: label} for soutirage cadrans."""
        return {name: info.label for name, info in self.cadrans.items()}

    @property
    def injection_cadran_labels(self) -> dict[str, str]:
        """Dict of {cadran: label} for injection cadrans."""
        return {name: info.label for name, info in self.injection_cadrans.items()}


# ---------------------------------------------------------------------------
# Data classes — /index endpoint
# ---------------------------------------------------------------------------

@dataclass
class CapfileEntry:
    """A single daily index entry returned by the /index endpoint."""
    date: datetime
    daily: dict[str, float]       # cadran → daily kWh (from base field name)
    cumulative: dict[str, float]  # cadran → cumulative kWh (from "cadran_X" field)
    total: float                  # total daily kWh across all cadrans


@dataclass
class CapfileData:
    """Parsed response from GET /data/{PRM}/index/cons."""
    prm: str
    cadrans: list[str]            # Detected cadran names in response order
    entries: list[CapfileEntry]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CapfileApiError(Exception):
    """Raised when the API returns success=false in its body."""


class CapfileActionRequiredError(Exception):
    """Raised when the API returns HTTP 422 — a user action is required before proceeding."""

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.url = url


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class CapfileApiClient:
    """Client to interact with the Capfile REST API."""

    def __init__(self, api_key: str, prm: str) -> None:
        self._api_key = api_key
        self._prm = prm.strip()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    @staticmethod
    async def async_get_api_key(login: str, password: str) -> str:
        """
        Retrieve the Capfile API key using login/password credentials.

        Uses HTTP Basic Auth on GET /api_key.
        Returns the API key string on success.
        Raises aiohttp.ClientResponseError on HTTP errors (401, 403, …).
        Raises CapfileApiError if the response body indicates failure.
        """
        url = f"{API_BASE_URL}/api_key"
        _LOGGER.debug("Capfile API request: GET %s (basic auth)", url)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                auth=aiohttp.BasicAuth(login, password),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                raw = await response.json()

        if not raw.get("success"):
            raise CapfileApiError(
                f"API /api_key returned success=false (code={raw.get('code')})"
            )
        return str(raw["data"]["api_key"])

    async def async_get_meters(self) -> list[CapfileMeter]:
        """
        Fetch the list of accessible meters from GET /meters.

        Returns all meters the API key has access to, including those shared
        by other Capfile users (marked with shared=True).
        """
        url = f"{API_BASE_URL}/meters"
        raw = await self._get(url, {})

        if not raw.get("success"):
            raise CapfileApiError(
                f"API /meters returned success=false (code={raw.get('code')})"
            )

        return [
            CapfileMeter(
                prm=str(item["prm"]),
                name=str(item.get("name", item["prm"])),
                shared=bool(item.get("shared", False)),
            )
            for item in (raw.get("data") or [])
        ]

    async def async_get_info(self) -> CapfileInfo:
        """
        Fetch site/contract information from GET /data/{PRM}/info.

        Returns cadran definitions, labels, colors, and contract prices.
        """
        url = f"{API_BASE_URL}/data/{self._prm}/info"
        raw = await self._get(url, {})

        if not raw.get("success"):
            raise CapfileApiError(
                f"API /info returned success=false (code={raw.get('code')})"
            )

        return self._parse_info(raw["data"])

    async def async_get_consumption(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> CapfileData:
        """
        Fetch daily consumption index data from GET /data/{PRM}/index/cons.

        start_date / end_date are optional filters.
        """
        params: dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")

        url = f"{API_BASE_URL}/data/{self._prm}/index/sou"
        _LOGGER.debug("Capfile API request: GET %s params=%s", url, params)
        raw = await self._get(url, params)

        if not raw.get("success"):
            raise CapfileApiError(
                f"API /index/sou returned success=false (code={raw.get('code')})"
            )

        result = self._parse_index(raw["data"])
        if result.entries:
            _LOGGER.info(
                "Capfile API returned %d entries for PRM %s (from %s to %s)",
                len(result.entries),
                result.prm,
                result.entries[0].date.date(),
                result.entries[-1].date.date(),
            )
        else:
            _LOGGER.warning("Capfile API returned 0 entries for PRM %s", result.prm)
        return result

    async def async_get_injection(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> CapfileData:
        """Fetch daily injection index data from GET /data/{PRM}/index/inj."""
        params: dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")

        url = f"{API_BASE_URL}/data/{self._prm}/index/inj"
        _LOGGER.debug("Capfile API request: GET %s params=%s", url, params)
        raw = await self._get(url, params)

        if not raw.get("success"):
            raise CapfileApiError(
                f"API /index/inj returned success=false (code={raw.get('code')})"
            )

        result = self._parse_index(raw["data"])
        if result.entries:
            _LOGGER.info(
                "Capfile injection API returned %d entries for PRM %s (from %s to %s)",
                len(result.entries),
                result.prm,
                result.entries[0].date.date(),
                result.entries[-1].date.date(),
            )
        else:
            _LOGGER.warning("Capfile injection API returned 0 entries for PRM %s", result.prm)
        return result

    async def async_validate(self) -> CapfileInfo:
        """
        Validate credentials and PRM by calling /info.

        Returns a CapfileInfo on success.
        Raises aiohttp.ClientResponseError (401/403/429/…) or CapfileApiError.
        """
        return await self.async_get_info()

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_info(self, data: dict[str, Any]) -> CapfileInfo:
        prm = (
            data.get("itc", {})
            .get("point", {})
            .get("id", self._prm)
        )

        # Soutirage (consumption) — nested under "soutirage", fall back to top-level
        soutirage: dict[str, Any] = data.get("soutirage") or {}
        cadrans_raw: dict[str, Any] = soutirage.get("cadrans") or data.get("cadrans") or {}
        prices_raw: dict[str, Any] = soutirage.get("prices") or data.get("prices") or {}

        cadrans = {
            name: CapfileCadranInfo(
                name=name,
                label=str(info.get("label", name)),
                color=str(info.get("color", "")),
                order=int(info.get("cadran", 99)),
            )
            for name, info in cadrans_raw.items()
        }
        prices_cts: dict[str, float] = {
            c: float(p)
            for c, p in (prices_raw.get("conso") or {}).items()
        }
        subscription = float(prices_raw.get("abonnement") or 0.0)
        power_kva = float(prices_raw.get("puissance_souscrite") or 0.0)
        offer_name = str(prices_raw.get("offer_name") or "")

        # Injection — nested under "injection"
        injection_raw: dict[str, Any] = data.get("injection") or {}
        injection_cadrans_raw: dict[str, Any] = injection_raw.get("cadrans") or {}
        injection_cadrans = {
            name: CapfileCadranInfo(
                name=name,
                label=str(info.get("label", name)),
                color=str(info.get("color", "")),
                order=int(info.get("cadran", 99)),
            )
            for name, info in injection_cadrans_raw.items()
        }
        puissance_raccordement = float(injection_raw.get("puissance_raccordement") or 0.0)

        return CapfileInfo(
            prm=prm,
            name=str(data.get("name", self._prm)),
            cadrans=cadrans,
            prices_cts=prices_cts,
            subscription_eur_month=subscription,
            power_kva=power_kva,
            offer_name=offer_name,
            injection_cadrans=injection_cadrans,
            puissance_raccordement=puissance_raccordement,
        )

    def _parse_index(self, data: dict[str, Any]) -> CapfileData:
        """Parse the /index response body into a CapfileData object."""
        head = data["head"]
        rows: list[dict[str, Any]] = data.get("data") or []

        # Detect cadran names dynamically from the first data row.
        # Cadran keys are those that are NOT "date" or "Total" and do NOT
        # start with the "cadran_" prefix (which marks cumulative values).
        cadrans: list[str] = []
        if rows:
            cadrans = [
                k
                for k in rows[0]
                if k not in ("date", "Total") and not k.startswith("cadran_")
            ]

        entries = [self._parse_row(row, cadrans) for row in rows]

        return CapfileData(
            prm=head["prm"],
            cadrans=cadrans,
            entries=entries,
        )

    @staticmethod
    def _parse_row(row: dict[str, Any], cadrans: list[str]) -> CapfileEntry:
        # API values are in Wh — convert to kWh
        return CapfileEntry(
            date=datetime.fromisoformat(str(row["date"])),
            daily={c: float(row.get(c) or 0.0) / 1000 for c in cadrans},
            cumulative={c: float(row.get(f"cadran_{c}") or 0.0) / 1000 for c in cadrans},
            total=float(row.get("Total") or 0.0) / 1000,
        )

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"x-api-key": self._api_key},
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 422:
                    raw = await response.json(content_type=None)
                    raise CapfileActionRequiredError(
                        message=raw.get("message", "Action requise sur votre compte Capfile"),
                        url=(raw.get("data") or {}).get("url", ""),
                    )
                response.raise_for_status()
                return await response.json()
