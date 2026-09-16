"""Theme generation for the Capfile integration."""
from __future__ import annotations

import asyncio
import logging
import os
import threading

import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CADRAN_COLORS,
    CONF_CADRANS,
    CONF_INJECTION_CADRAN_COLORS,
    CONF_INJECTION_CADRANS,
    CONF_PRM,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Single shared theme file — replaces per-PRM files
_THEME_NAME = "Capfile"
_THEME_FILE = "capfile.yaml"

# Serialises collect+write: a config-entry reload fires an unload pass and a setup
# pass as independent tasks, which previously raced and corrupted the theme file.
_THEME_LOCK = asyncio.Lock()

# Perceived luminance threshold above which a color is considered "too light"
# for a white background (0–255 scale). Pure white = 255.
_LIGHT_THRESHOLD = 210


def _darken_for_light(hex_color: str) -> str:
    """
    Return a version of the color suitable for light mode.

    Colors with high perceived luminance (near white) are darkened so they
    remain visible against a white background. All other colors are unchanged.
    Perceived luminance = 0.299·R + 0.587·G + 0.114·B (ITU-R BT.601).
    """
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return hex_color

    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance <= _LIGHT_THRESHOLD:
        return hex_color

    factor = _LIGHT_THRESHOLD / max(luminance, 1) * 0.75
    r2 = min(255, int(r * factor))
    g2 = min(255, int(g * factor))
    b2 = min(255, int(b * factor))
    return f"#{r2:02x}{g2:02x}{b2:02x}"


async def _reset_capfile_theme_for_all_users(hass: HomeAssistant) -> None:
    """Reset the selected theme to 'default' for any user who had a Capfile theme selected.

    The theme preference is stored under the key ``"theme"`` (not ``"selectedTheme"``)
    in frontend.user_data_<user_id>.  The stored name may be the current merged
    name (``"Capfile"``) or an old per-PRM name (``"Capfile – …"``), so we match
    anything that starts with ``"Capfile"``.
    """
    from homeassistant.helpers.storage import Store  # noqa: PLC0415

    try:
        users = await hass.auth.async_get_users()
    except Exception:  # pylint: disable=broad-except
        return

    for user in users:
        store = Store(hass, 1, f"frontend.user_data_{user.id}")
        try:
            data = await store.async_load()
        except Exception:  # pylint: disable=broad-except
            continue
        if not isinstance(data, dict):
            continue
        theme_pref = data.get("theme")
        if not isinstance(theme_pref, dict):
            continue
        current_theme = theme_pref.get("theme", "")
        if not isinstance(current_theme, str) or not current_theme.startswith(_THEME_NAME):
            continue
        # Preserve dark-mode preference if present
        new_pref: dict = {"theme": "default"}
        if "dark" in theme_pref:
            new_pref["dark"] = theme_pref["dark"]
        data["theme"] = new_pref
        try:
            await store.async_save(data)
            _LOGGER.debug("Capfile: reset theme to default for user %s", user.id)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.warning("Capfile: could not reset theme for user %s", user.id)


async def async_generate_theme(
    hass: HomeAssistant,
    entry: ConfigEntry,
    is_unloading: bool = False,
) -> None:
    """
    Write (or update) a single merged HA theme combining cadran colors from
    all active Capfile config entries.

    Color indices are assigned in the same order as entries are registered,
    which matches the order used by energy_config.py when adding sources to
    the Energy dashboard:
      - energy-grid-consumption-color-N  →  N-th soutirage cadran across all entries
      - energy-grid-return-color-N       →  N-th injection cadran across all entries

    When is_unloading=True the current entry is excluded from the merge so
    its colors are removed when the entry is deleted.

    Old per-PRM theme files (capfile_<prm>.yaml) are cleaned up automatically.

    Requires in configuration.yaml:
        frontend:
          themes: !include_dir_merge_named themes/
    """
    themes_dir = hass.config.path("themes")
    theme_file = os.path.join(themes_dir, _THEME_FILE)

    # Collect entries that should contribute to the merged theme
    # Hold the lock across collect AND write: a reload schedules an unload pass
    # (which sees no active entry and would write the empty stub) and a setup pass
    # as independent tasks. Serialising both means the last writer collects the
    # current truth instead of stomping a stale snapshot over it.
    async with _THEME_LOCK:
        all_entries = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if not (is_unloading and e.entry_id == entry.entry_id)
        ]

        dark_vars: dict[str, str] = {}
        light_vars: dict[str, str] = {}
        cons_idx = 0
        inj_idx = 0

        for e in all_entries:
            cadrans = [c for c in e.data.get(CONF_CADRANS, "").split(",") if c]
            colors: dict[str, str] = e.data.get(CONF_CADRAN_COLORS, {})
            for cadran in cadrans:
                color = colors.get(cadran)
                if color:
                    dark_vars[f"energy-grid-consumption-color-{cons_idx}"] = color
                    light_vars[f"energy-grid-consumption-color-{cons_idx}"] = _darken_for_light(color)
                cons_idx += 1

            inj_cadrans = [c for c in e.data.get(CONF_INJECTION_CADRANS, "").split(",") if c]
            inj_colors: dict[str, str] = e.data.get(CONF_INJECTION_CADRAN_COLORS, {})
            for cadran in inj_cadrans:
                color = inj_colors.get(cadran)
                if color:
                    dark_vars[f"energy-grid-return-color-{inj_idx}"] = color
                    light_vars[f"energy-grid-return-color-{inj_idx}"] = _darken_for_light(color)
                inj_idx += 1

        legacy_files = [
            os.path.join(
                themes_dir,
                "capfile_%s.yaml" % "".join(
                    c if c.isalnum() else "_" for c in e.data.get(CONF_PRM, e.entry_id)
                ),
            )
            for e in hass.config_entries.async_entries(DOMAIN)
        ]

        def _write_and_cleanup() -> None:
            os.makedirs(themes_dir, exist_ok=True)

            if dark_vars:
                theme_content = {
                    _THEME_NAME: {
                        "modes": {
                            "light": light_vars,
                            "dark": dark_vars,
                        }
                    }
                }
            else:
                # No active entries: keep a stub theme with empty mode sections so
                # the HA frontend selector stays functional and the dark/light mode
                # preference is preserved (a theme without "modes" forces light mode).
                theme_content = {_THEME_NAME: {"modes": {"light": {}, "dark": {}}}}

            # Write to a temp file in the same directory, then rename atomically.
            # The temp name must not end in .yaml and starts with a dot, so that
            # !include_dir_merge_named never picks it up mid-write.
            tmp_file = os.path.join(
                themes_dir, f".{_THEME_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with open(tmp_file, "w", encoding="utf-8") as f:
                yaml.dump(theme_content, f, allow_unicode=True, default_flow_style=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, theme_file)

            # Remove old per-PRM theme files left over from previous versions.
            # The entry list is computed in the event loop (see legacy_files) —
            # hass.config_entries is not safe to read from an executor thread.
            for old_file in legacy_files:
                if old_file != theme_file and os.path.exists(old_file):
                    os.remove(old_file)
                    _LOGGER.debug("Capfile: removed old per-PRM theme file %s", old_file)

        await hass.async_add_executor_job(_write_and_cleanup)

    if not dark_vars:
        _LOGGER.debug("Capfile: no active entries — empty stub theme kept so the selector stays functional")
        try:
            await hass.services.async_call("frontend", "reload_themes")
        except Exception:  # pylint: disable=broad-except
            pass
        return

    _LOGGER.info(
        "Capfile merged theme written (%d consumption, %d injection colors)",
        cons_idx, inj_idx,
    )

    try:
        await hass.services.async_call("frontend", "reload_themes")
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Capfile: could not reload themes automatically. "
            "Add 'frontend: themes: !include_dir_merge_named themes/' "
            "to configuration.yaml, then restart HA."
        )
