"""Capfile — intégration des données de consommation électrique via l'API Capfile."""
from __future__ import annotations



from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .api import CapfileApiClient
from .const import CONF_API_KEY, CONF_AUTO_CONFIGURE_ENERGY, CONF_PRM, DOMAIN

PLATFORMS = ["sensor"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Appelé si 'capfile:' est présent dans configuration.yaml (bootstrap ou utilisateur).
    Le composant fonctionne exclusivement via config entries — rien à faire ici."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Capfile integration entry."""
    hass.data.setdefault(DOMAIN, {})

    # Notification tutoriel — affichée une seule fois, à la première configuration,
    # uniquement si la configuration automatique du dashboard Énergie n'est pas activée.
    if not entry.data.get("tuto_shown"):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "tuto_shown": True}
        )
        if not entry.options.get(CONF_AUTO_CONFIGURE_ENERGY, False):
            hass.async_create_task(
                hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "Capfile — Configurer le dashboard Énergie",
                        "message": (
                            "L'intégration Capfile est configurée et la synchronisation des données a démarré.\n\n"
                            "Suivez le [guide pas-à-pas](https://capfile.com/capfile/ha/tuto/#energy-config) "
                            "pour ajouter vos données dans le tableau de bord Énergie."
                        ),
                        "notification_id": f"capfile_tuto_{entry.entry_id}",
                    },
                )
            )

    client = CapfileApiClient(
        api_key=entry.data[CONF_API_KEY],
        prm=entry.data[CONF_PRM],
    )

    hass.data[DOMAIN][entry.entry_id] = {"cancel": None, "client": client, "sensor_data": {}}

    async def _do_sync(_now=None) -> None:
        """Fetch data from Capfile and inject statistics into HA recorder."""
        from .statistics import async_inject_statistics
        await async_inject_statistics(hass, entry, client)

    # Register sensor platform before first sync so entities exist when data arrives
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Generate/update the Capfile theme with cadran colors from the API
    from .theme import async_generate_theme
    hass.async_create_task(async_generate_theme(hass, entry))

    # Energy dashboard auto-config is triggered from statistics.py after the
    # first data sync, because HA validates stat IDs against the recorder.

    # Immediate sync on startup
    hass.async_create_task(_do_sync())

    # Sync quotidienne à midi (heure locale du serveur HA)
    cancel = async_track_time_change(hass, _do_sync, hour=12, minute=0, second=0)

    hass.data[DOMAIN][entry.entry_id]["cancel"] = cancel
    entry.async_on_unload(cancel)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated (e.g. price change)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Capfile config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    if cancel := data.get("cancel"):
        cancel()
    # Regenerate the merged theme excluding this entry's colors
    from .theme import async_generate_theme
    hass.async_create_task(async_generate_theme(hass, entry, is_unloading=True))
    return unloaded
