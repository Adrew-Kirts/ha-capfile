"""Statistics injection for the Capfile integration."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)

# Note: async_add_external_statistics est @callback (sync, event loop uniquement).
# get_instance est utilisé uniquement pour get_last_statistics (requête DB bloquante).
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .api import CapfileApiClient
from .const import (
    CADRAN_LABELS_DEFAULT,
    CONF_AUTO_CONFIGURE_ENERGY,
    CONF_AUTO_UPDATE_PRICES,
    CONF_CADRAN_LABELS,
    CONF_CADRANS,
    CONF_INJECTION_CADRAN_LABELS,
    CONF_INJECTION_CADRANS,
    CONF_SUBSCRIPTION_COST,
    DEFAULT_PRICES_EUR,
    DOMAIN,
    SIGNAL_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Statistic ID helpers
# ---------------------------------------------------------------------------

def _energy_stat_id(cadran: str) -> str:
    """External statistic ID for a soutirage cadran's energy."""
    return f"{DOMAIN}:conso_{cadran.lower()}"


def _inj_energy_stat_id(cadran: str) -> str:
    """External statistic ID for an injection cadran's energy."""
    return f"{DOMAIN}:inj_{cadran.lower()}"


def _cost_stat_id(cadran: str | None = None) -> str:
    """
    External statistic ID for cost.

    Per-cadran: capfile:cost_buhc  → used in the Energy dashboard per source.
    Total (cadran=None): capfile:cost  → sum of all cadrans (informational).
    """
    if cadran:
        return f"{DOMAIN}:cost_{cadran.lower()}"
    return f"{DOMAIN}:cost"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def async_inject_statistics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: CapfileApiClient,
) -> None:
    """
    Fetch consumption data from Capfile and inject it into the HA recorder.

    Creates one external statistic per cadran (energy, kWh) and one for the
    total estimated cost (EUR).

    Sums are accumulated incrementally from daily values (not absolute meter
    readings) so that:
    - The first injected entry never produces a spike (sum starts at 0).
    - Incremental syncs continue from the last stored sum value.
    """
    prm = entry.data.get("prm", "?")
    _LOGGER.info("Starting Capfile statistics sync for PRM %s", prm)

    cadrans = _stored_cadrans(entry)
    entries: list = []

    # ------------------------------------------------------------------
    # Soutirage statistics (skipped for injection-only meters)
    # ------------------------------------------------------------------
    if cadrans:
        existing_cutoff, _ = await _get_last_stat_info(hass, _energy_stat_id(cadrans[0]))

        last_energy_sums: dict[str, float] = {}
        last_cost_sums: dict[str, float] = {}
        last_total_cost_sum = 0.0

        if existing_cutoff is not None:
            for c in cadrans:
                _, es = await _get_last_stat_info(hass, _energy_stat_id(c))
                _, cs = await _get_last_stat_info(hass, _cost_stat_id(c))
                last_energy_sums[c] = es
                last_cost_sums[c] = cs
            _, last_total_cost_sum = await _get_last_stat_info(hass, _cost_stat_id())

        month_start: date = date.today().replace(day=1)
        if existing_cutoff is None:
            start_date: date = date.today() - timedelta(days=3 * 365)
            _LOGGER.info("Initial sync for PRM %s — requesting full history from %s", prm, start_date)
        else:
            start_date = min(existing_cutoff.date(), month_start)
            _LOGGER.info("Incremental sync for PRM %s — from %s (last: %s)", prm, start_date, existing_cutoff)

        try:
            data = await client.async_get_consumption(start_date=start_date)
        except Exception as err:
            _LOGGER.error("Failed to fetch Capfile consumption data: %s", err)
            return

        if not data.entries:
            _LOGGER.warning("Capfile API returned no soutirage data for PRM %s", prm)
        else:
            prices = _get_prices(entry, cadrans)
            labels = _get_labels(entry)
            entries = sorted(data.entries, key=lambda e: e.date)
            new_entries = [
                e for e in entries
                if not (existing_cutoff and _to_utc(e.date) <= existing_cutoff)
            ]
            _LOGGER.info(
                "Cadrans: %s | Prices (€/kWh): %s | API entries: %d | New: %d",
                cadrans, prices, len(data.entries), len(new_entries),
            )

            if new_entries:
                running_energy: dict[str, float] = {c: last_energy_sums.get(c, 0.0) for c in cadrans}
                running_cost: dict[str, float] = {c: last_cost_sums.get(c, 0.0) for c in cadrans}
                running_total_cost = last_total_cost_sum
                stats_by_cadran: dict[str, list[StatisticData]] = {c: [] for c in cadrans}
                stats_cost_by_cadran: dict[str, list[StatisticData]] = {c: [] for c in cadrans}
                stats_cost_total: list[StatisticData] = []

                for entry_data in new_entries:
                    start = _to_utc(entry_data.date)
                    day_total_cost = 0.0
                    for cadran in cadrans:
                        price = prices.get(cadran, 0.0)
                        daily_kwh = entry_data.daily.get(cadran, 0.0)
                        daily_cost = daily_kwh * price
                        running_energy[cadran] += daily_kwh
                        running_cost[cadran] += daily_cost
                        day_total_cost += daily_cost
                        stats_by_cadran[cadran].append(
                            StatisticData(start=start, state=daily_kwh, sum=running_energy[cadran])
                        )
                        stats_cost_by_cadran[cadran].append(
                            StatisticData(start=start, state=daily_cost, sum=running_cost[cadran])
                        )
                    running_total_cost += day_total_cost
                    stats_cost_total.append(
                        StatisticData(start=start, state=day_total_cost, sum=running_total_cost)
                    )

                for c in cadrans:
                    label = labels.get(c, c)
                    if stats_by_cadran[c]:
                        async_add_external_statistics(
                            hass,
                            StatisticMetaData(
                                statistic_id=_energy_stat_id(c),
                                source=DOMAIN,
                                name=f"Capfile {label}",
                                unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                                has_mean=False,
                                has_sum=True,
                                mean_type=StatisticMeanType.NONE,
                                unit_class="energy",
                            ),
                            stats_by_cadran[c],
                        )
                    if stats_cost_by_cadran[c]:
                        async_add_external_statistics(
                            hass,
                            StatisticMetaData(
                                statistic_id=_cost_stat_id(c),
                                source=DOMAIN,
                                name=f"Capfile Coût {label}",
                                unit_of_measurement="EUR",
                                has_mean=False,
                                has_sum=True,
                                mean_type=StatisticMeanType.NONE,
                                unit_class=None,
                            ),
                            stats_cost_by_cadran[c],
                        )

                if stats_cost_total:
                    async_add_external_statistics(
                        hass,
                        StatisticMetaData(
                            statistic_id=_cost_stat_id(),
                            source=DOMAIN,
                            name="Capfile Coût total estimé",
                            unit_of_measurement="EUR",
                            has_mean=False,
                            has_sum=True,
                            mean_type=StatisticMeanType.NONE,
                            unit_class=None,
                        ),
                        stats_cost_total,
                    )

        # `entries`/`prices` are only bound in the `else` branch above, i.e. exactly
        # when data.entries is non-empty. Skip rather than dispatch zeros over
        # the current sensor values.
        if data.entries:
            _update_sensor_data(hass, entry, entries, cadrans, prices if cadrans else {})
        await _maybe_update_prices(hass, entry, client, cadrans)

    # ------------------------------------------------------------------
    # Injection statistics (skipped for soutirage-only meters)
    # ------------------------------------------------------------------
    inj_cadrans = _stored_injection_cadrans(entry)
    if inj_cadrans:
        await _sync_injection(hass, entry, client, prm, inj_cadrans)

    # Auto-configure the Energy dashboard after each sync (idempotent —
    # exits immediately if already configured or option disabled).
    # Called at the end so both soutirage and injection stats are injected first.
    from .energy_config import async_configure_energy_dashboard  # noqa: PLC0415
    hass.async_create_task(async_configure_energy_dashboard(hass, entry))

    # If auto-config is disabled, notify the user to configure manually.
    # Uses a fixed notification_id so HA deduplicates it across syncs.
    if not entry.options.get(CONF_AUTO_CONFIGURE_ENERGY, False):
        from homeassistant.components.persistent_notification import async_create as pn_create  # noqa: PLC0415
        pn_create(
            hass,
            (
                "Vos données de consommation Capfile sont disponibles dans le recorder.\n\n"
                "Configurez votre tableau de bord **Énergie** en suivant le "
                "[guide pas-à-pas](https://capfile.com/capfile/ha/tuto/#energy-config)."
            ),
            title="Capfile — Configurez le dashboard Énergie",
            notification_id=f"capfile_energy_manual_{entry.entry_id}",
        )


def _update_sensor_data(
    hass: HomeAssistant,
    entry: ConfigEntry,
    all_entries: list,
    cadrans: list[str],
    prices: dict[str, float],
) -> None:
    """Compute current-month aggregates and dispatch to sensor entities."""
    today = date.today()
    month_start = today.replace(day=1)

    month_kwh: dict[str, float] = {c: 0.0 for c in cadrans}
    month_cost: dict[str, float] = {c: 0.0 for c in cadrans}

    for e in all_entries:
        # Use the naive API date directly (Paris time) — converting to UTC
        # shifts midnight entries to the previous day, causing month-boundary errors.
        if e.date.date() >= month_start:
            for c in cadrans:
                daily = e.daily.get(c, 0.0)
                month_kwh[c] += daily
                month_cost[c] += daily * prices.get(c, 0.0)

    total_month_kwh = sum(month_kwh.values())
    total_month_cost_variable = sum(month_cost.values())

    # Subscription prorated: monthly × 12 / 365 × days elapsed this month
    subscription_monthly = float(
        entry.options.get(CONF_SUBSCRIPTION_COST,
                          entry.data.get(CONF_SUBSCRIPTION_COST, 0.0))
    )
    days_elapsed = (today - month_start).days + 1
    month_subscription = subscription_monthly * 12 / 365 * days_elapsed
    month_cost_total = total_month_cost_variable + month_subscription

    sensor_data = {
        "month_kwh": round(total_month_kwh, 3),
        "month_kwh_by_cadran": {c: round(v, 3) for c, v in month_kwh.items()},
        "month_cost_variable": round(total_month_cost_variable, 2),
        "month_cost_by_cadran": {c: round(v, 2) for c, v in month_cost.items()},
        "month_subscription": round(month_subscription, 2),
        "month_cost_total": round(month_cost_total, 2),
        "last_sync": datetime.now(timezone.utc).isoformat(),
    }

    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["sensor_data"] = sensor_data
        async_dispatcher_send(hass, f"{SIGNAL_UPDATE}_{entry.entry_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware (assumes Europe/Paris if naive)."""
    if dt.tzinfo is None:
        local_tz = dt_util.get_time_zone("Europe/Paris")
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


def _stored_cadrans(entry: ConfigEntry) -> list[str]:
    """Return the ordered soutirage cadran list stored in the config entry."""
    raw = entry.data.get(CONF_CADRANS, "")
    return [c for c in raw.split(",") if c]


def _stored_injection_cadrans(entry: ConfigEntry) -> list[str]:
    """Return the ordered injection cadran list stored in the config entry."""
    raw = entry.data.get(CONF_INJECTION_CADRANS, "")
    return [c for c in raw.split(",") if c]


async def _sync_injection(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: CapfileApiClient,
    prm: str,
    inj_cadrans: list[str],
) -> None:
    """Fetch injection data and inject energy statistics into the HA recorder."""
    first_stat_id = _inj_energy_stat_id(inj_cadrans[0])
    existing_cutoff, _ = await _get_last_stat_info(hass, first_stat_id)

    last_inj_sums: dict[str, float] = {}
    if existing_cutoff is not None:
        for c in inj_cadrans:
            _, s = await _get_last_stat_info(hass, _inj_energy_stat_id(c))
            last_inj_sums[c] = s

    month_start: date = date.today().replace(day=1)
    if existing_cutoff is None:
        start_date: date = date.today() - timedelta(days=3 * 365)
    else:
        start_date = min(existing_cutoff.date(), month_start)

    try:
        data = await client.async_get_injection(start_date=start_date)
    except Exception as err:
        _LOGGER.error("Failed to fetch Capfile injection data for PRM %s: %s", prm, err)
        return

    if not data.entries:
        _LOGGER.warning("Capfile injection API returned no data for PRM %s", prm)
        return

    cadrans = inj_cadrans or data.cadrans
    labels: dict[str, str] = {**CADRAN_LABELS_DEFAULT, **entry.data.get(CONF_INJECTION_CADRAN_LABELS, {})}

    entries = sorted(data.entries, key=lambda e: e.date)
    new_entries = [
        e for e in entries
        if not (existing_cutoff and _to_utc(e.date) <= existing_cutoff)
    ]

    if not new_entries:
        _LOGGER.info("No new Capfile injection data to inject for PRM %s", prm)
        return

    _LOGGER.info("Injecting %d new injection point(s) for PRM %s", len(new_entries), prm)

    running: dict[str, float] = {c: last_inj_sums.get(c, 0.0) for c in cadrans}
    stats_by_cadran: dict[str, list[StatisticData]] = {c: [] for c in cadrans}

    for entry_data in new_entries:
        start = _to_utc(entry_data.date)
        for cadran in cadrans:
            daily_kwh = entry_data.daily.get(cadran, 0.0)
            running[cadran] += daily_kwh
            stats_by_cadran[cadran].append(
                StatisticData(start=start, state=daily_kwh, sum=running[cadran])
            )

    for c in cadrans:
        if stats_by_cadran[c]:
            async_add_external_statistics(
                hass,
                StatisticMetaData(
                    statistic_id=_inj_energy_stat_id(c),
                    source=DOMAIN,
                    name=f"Capfile {labels.get(c, c)}",
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    has_mean=False,
                    has_sum=True,
                    mean_type=StatisticMeanType.NONE,
                    unit_class="energy",
                ),
                stats_by_cadran[c],
            )


def _get_prices(entry: ConfigEntry, cadrans: list[str]) -> dict[str, float]:
    """
    Return price-per-cadran in €/kWh.

    Prices are stored with 1-based indexed keys (price_1, price_2, …)
    whose order matches the cadrans list stored in CONF_CADRANS.
    Options override the initial data values.
    """
    prices: dict[str, float] = {}
    for i, cadran in enumerate(cadrans, 1):
        key = f"price_{i}"
        value = entry.options.get(key, entry.data.get(key))
        prices[cadran] = float(value) if value is not None else DEFAULT_PRICES_EUR.get(cadran, 0.0)
    return prices


def _get_labels(entry: ConfigEntry) -> dict[str, str]:
    """Return cadran labels from config entry (set from API at setup time)."""
    stored: dict[str, str] = entry.data.get(CONF_CADRAN_LABELS, {})
    return {**CADRAN_LABELS_DEFAULT, **stored}


async def _maybe_update_prices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: CapfileApiClient,
    cadrans: list[str],
) -> None:
    """If auto-update is enabled, fetch fresh prices from the API and update the entry if changed."""
    if not entry.options.get(CONF_AUTO_UPDATE_PRICES, False):
        return

    try:
        info = await client.async_get_info()
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Auto-update prices: failed to fetch /info: %s", err)
        return

    cadran_labels: dict[str, str] = entry.data.get(CONF_CADRAN_LABELS, {})
    new_options = dict(entry.options)
    changes: list[str] = []

    for i, c in enumerate(cadrans, 1):
        key = f"price_{i}"
        old_price = float(entry.options.get(key, entry.data.get(key, 0.0)))
        new_price = info.prices_eur.get(c, 0.0)
        if new_price > 0 and abs(new_price - old_price) > 0.0001:
            new_options[key] = new_price
            label = cadran_labels.get(c, c)
            changes.append(f"{label} : {old_price:.4f} → {new_price:.4f} €/kWh")

    old_sub = float(entry.options.get(CONF_SUBSCRIPTION_COST, entry.data.get(CONF_SUBSCRIPTION_COST, 0.0)))
    new_sub = info.subscription_eur_month
    if new_sub > 0 and abs(new_sub - old_sub) > 0.01:
        new_options[CONF_SUBSCRIPTION_COST] = new_sub
        changes.append(f"Abonnement : {old_sub:.2f} → {new_sub:.2f} €/mois")

    if not changes:
        _LOGGER.debug("Auto-update prices: no changes detected")
        return

    _LOGGER.info("Auto-update prices: changes detected — %s", ", ".join(changes))
    hass.config_entries.async_update_entry(entry, options=new_options)

    from homeassistant.components.persistent_notification import async_create as pn_create
    pn_create(
        hass,
        "Les tarifs Capfile ont été mis à jour automatiquement :\n\n"
        + "\n".join(f"- {c}" for c in changes),
        title="Capfile — Tarifs mis à jour",
        notification_id=f"capfile_prices_updated_{entry.entry_id}",
    )


async def _get_last_stat_info(
    hass: HomeAssistant, statistic_id: str | None
) -> tuple[datetime | None, float]:
    """Return (last timestamp, last sum value) for the given statistic."""
    if not statistic_id:
        return None, 0.0
    try:
        last = await get_instance(hass).async_add_executor_job(
            lambda: get_last_statistics(hass, 1, statistic_id, True, {"sum"})
        )
        if last and statistic_id in last:
            row = last[statistic_id][0]
            ts = datetime.fromtimestamp(row["start"], tz=timezone.utc)
            return ts, float(row.get("sum") or 0.0)
    except Exception:  # pylint: disable=broad-except
        pass
    return None, 0.0
