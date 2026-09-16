"""Auto-configure the Home Assistant Energy dashboard with Capfile statistics."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_AUTO_CONFIGURE_ENERGY, CONF_CADRANS, CONF_INJECTION_CADRANS, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Energy storage minor_version tested and known to work with our flat-entry format
SUPPORTED_ENERGY_MINOR_VERSION = 3


# ---------------------------------------------------------------------------
# Stat ID helpers (duplicated from statistics.py to avoid circular imports)
# ---------------------------------------------------------------------------

def _energy_stat_id(cadran: str) -> str:
    return f"{DOMAIN}:conso_{cadran.lower()}"


def _inj_energy_stat_id(cadran: str) -> str:
    return f"{DOMAIN}:inj_{cadran.lower()}"


def _cost_stat_id(cadran: str) -> str:
    return f"{DOMAIN}:cost_{cadran.lower()}"


def _grid_entry_from(cadran: str) -> dict:
    """Build a flat grid source entry for a consumption cadran."""
    return {
        "type": "grid",
        "stat_energy_from": _energy_stat_id(cadran),
        "stat_energy_to": None,
        "stat_cost": _cost_stat_id(cadran),
        "stat_compensation": None,
        "entity_energy_price": None,
        "number_energy_price": None,
        "entity_energy_price_export": None,
        "number_energy_price_export": None,
        "cost_adjustment_day": 0.0,
    }


def _grid_entry_to(cadran: str) -> dict:
    """Build a flat grid source entry for an injection cadran."""
    return {
        "type": "grid",
        "stat_energy_from": None,
        "stat_energy_to": _inj_energy_stat_id(cadran),
        "stat_cost": None,
        "stat_compensation": None,
        "entity_energy_price": None,
        "number_energy_price": None,
        "entity_energy_price_export": None,
        "number_energy_price_export": None,
        "cost_adjustment_day": 0.0,
    }


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

async def async_configure_energy_dashboard(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """
    Add Capfile stat IDs to the Energy dashboard if not already present.

    Uses the flat per-cadran grid source format introduced in HA 2024/2025
    (minor_version 3): each cadran is its own top-level "grid" entry rather
    than being nested inside flow_from / flow_to arrays.

    Must be called AFTER statistics have been injected into the recorder.
    Is idempotent — no-op if all cadrans are already configured.
    """
    if not entry.options.get(CONF_AUTO_CONFIGURE_ENERGY, False):
        return

    cadrans = [c.strip() for c in entry.data.get(CONF_CADRANS, "").split(",") if c.strip()]
    inj_cadrans = [c.strip() for c in entry.data.get(CONF_INJECTION_CADRANS, "").split(",") if c.strip()]

    if not cadrans and not inj_cadrans:
        return

    prm = entry.data.get("prm", "?")

    # ------------------------------------------------------------------
    # Load the energy manager
    # ------------------------------------------------------------------
    try:
        from homeassistant.components.energy import async_get_manager  # noqa: PLC0415
    except ImportError:
        _LOGGER.debug("Capfile: energy component not available — skipping dashboard auto-config")
        return

    try:
        manager = await async_get_manager(hass)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.debug("Capfile: energy manager unavailable: %s", err)
        return

    prefs = manager.data
    if prefs is None:
        # Fresh instance: no energy storage yet — start with an empty source list.
        current_sources: list = []
    elif isinstance(prefs, dict):
        current_sources = prefs.get("energy_sources", [])
    else:
        current_sources = getattr(prefs, "energy_sources", [])

    # ------------------------------------------------------------------
    # Inspect what is already configured (flat format)
    # ------------------------------------------------------------------
    configured_from: set[str] = set()
    configured_to: set[str] = set()
    for source in current_sources:
        if source.get("type") == "grid":
            if source.get("stat_energy_from"):
                configured_from.add(source["stat_energy_from"])
            if source.get("stat_energy_to"):
                configured_to.add(source["stat_energy_to"])

    missing_from = [c for c in cadrans if _energy_stat_id(c) not in configured_from]
    missing_to = [c for c in inj_cadrans if _inj_energy_stat_id(c) not in configured_to]

    if not missing_from and not missing_to:
        _LOGGER.debug("Capfile: Energy dashboard already configured for PRM %s", prm)
        return

    # ------------------------------------------------------------------
    # Append missing entries (one flat grid entry per cadran)
    # ------------------------------------------------------------------
    sources = list(current_sources)
    for c in missing_from:
        sources.append(_grid_entry_from(c))
    for c in missing_to:
        sources.append(_grid_entry_to(c))

    _LOGGER.debug("Capfile: sending %d energy_sources for PRM %s", len(sources), prm)

    # ------------------------------------------------------------------
    # Apply the update
    # ------------------------------------------------------------------
    try:
        await manager.async_update({"energy_sources": sources})
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Capfile: failed to auto-configure Energy dashboard: %s", err)
        return

    _LOGGER.info(
        "Capfile: Energy dashboard auto-configured for PRM %s "
        "(%d consommation, %d injection added)",
        prm, len(missing_from), len(missing_to),
    )

    # Dismiss the "configure manually" notification if it was previously shown
    from homeassistant.components.persistent_notification import async_dismiss  # noqa: PLC0415
    async_dismiss(hass, notification_id=f"capfile_energy_manual_{entry.entry_id}")
