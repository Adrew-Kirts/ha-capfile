"""Config flow for the Capfile integration."""
from __future__ import annotations

import json

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CapfileActionRequiredError, CapfileApiClient, CapfileApiError, CapfileInfo, CapfileMeter
from .energy_config import SUPPORTED_ENERGY_MINOR_VERSION
from .const import (
    CONF_API_KEY,
    CONF_AUTO_CONFIGURE_ENERGY,
    CONF_AUTO_UPDATE_PRICES,
    CONF_CADRAN_COLORS,
    CONF_CADRAN_LABELS,
    CONF_CADRANS,
    CONF_INJECTION_CADRAN_COLORS,
    CONF_INJECTION_CADRAN_LABELS,
    CONF_INJECTION_CADRANS,
    CONF_OFFER_NAME,
    CONF_POWER_KVA,
    CONF_PRM,
    CONF_PUISSANCE_RACCORDEMENT,
    CONF_SITE_NAME,
    CONF_SUBSCRIPTION_COST,
    DEFAULT_PRICES_EUR,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("login"): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        vol.Required("password"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


def _meter_schema(meters: list[CapfileMeter]) -> vol.Schema:
    """Build a meter selection schema from the /meters response."""
    options: dict[str, str] = {}
    for m in meters:
        label = f"{m.name} ({m.prm})"
        if m.shared:
            label += " [partagé]"
        options[m.prm] = label
    return vol.Schema({vol.Required(CONF_PRM): vol.In(options)})


def _prices_schema(
    cadran_names: list[str],
    prices_eur: dict[str, float],
    subscription: float,
    overrides: dict | None = None,
) -> vol.Schema:
    """
    Build the tariff schema using 1-based indexed keys (price_1, price_2, …).

    The association index↔cadran is determined by the order of cadran_names.
    Field labels shown in the UI come from translations data_description
    placeholders (label_1, label_2, …) filled with API labels at render time.

    When the API returns 0 for a price, DEFAULT_PRICES_EUR is used as fallback.
    """
    overrides = overrides or {}
    fields: dict = {}

    for i, c in enumerate(cadran_names, 1):
        key = f"price_{i}"
        api_price = prices_eur.get(c, 0.0)
        default = overrides.get(
            key,
            api_price if api_price > 0 else DEFAULT_PRICES_EUR.get(c, 0.0),
        )
        fields[vol.Optional(key, default=default)] = vol.Coerce(float)

    sub_default = overrides.get(
        CONF_SUBSCRIPTION_COST,
        subscription if subscription > 0 else 0.0,
    )
    fields[vol.Optional(CONF_SUBSCRIPTION_COST, default=sub_default)] = vol.Coerce(float)

    return vol.Schema(fields)


async def _read_energy_minor_version(hass) -> int | None:
    """Return the minor_version from .storage/energy, or None if the file is absent."""
    from pathlib import Path  # noqa: PLC0415
    try:
        path = Path(hass.config.path(".storage", "energy"))
        if not path.exists():
            return None
        raw = await hass.async_add_executor_job(path.read_text, "utf-8")
        return json.loads(raw).get("minor_version")
    except Exception:  # pylint: disable=broad-except
        return None


def _label_placeholders(cadran_names: list[str], cadran_labels: dict[str, str]) -> dict[str, str]:
    """Return {label_1: "Bleu HC", label_2: "Bleu HP", …} for description_placeholders."""
    return {
        f"label_{i}": cadran_labels.get(c, c)
        for i, c in enumerate(cadran_names, 1)
    }


class CapfileConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration flow (3 steps)."""

    VERSION = 1

    # State shared between steps
    _api_key: str
    _meters: list[CapfileMeter]
    _info: CapfileInfo

    # ------------------------------------------------------------------
    # Step 1 — Login/password → fetch API key → fetch meter list
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Ask for Capfile credentials, retrieve the API key, then fetch meters.

        If a Capfile entry already exists (same single account), the stored API
        key is reused and the login form is skipped entirely.
        """
        # Reuse existing API key if available (first display only, not on retry)
        if user_input is None:
            existing = next(
                (e for e in self.hass.config_entries.async_entries(DOMAIN)
                 if e.data.get(CONF_API_KEY)),
                None,
            )
            if existing:
                try:
                    self._api_key = existing.data[CONF_API_KEY]
                    client = CapfileApiClient(self._api_key, prm="")
                    self._meters = await client.async_get_meters()
                    return await self.async_step_meter()
                except Exception:  # pylint: disable=broad-except
                    pass  # key may have expired — fall through to login form

        errors: dict[str, str] = {}

        if user_input is not None:
            login = user_input["login"].strip()
            password = user_input["password"]
            try:
                self._api_key = await CapfileApiClient.async_get_api_key(login, password)
                client = CapfileApiClient(self._api_key, prm="")
                self._meters = await client.async_get_meters()
            except aiohttp.ClientResponseError as err:
                errors["base"] = {
                    401: "invalid_auth",
                    403: "forbidden",
                    429: "quota_exceeded",
                }.get(err.status, "cannot_connect")
            except (aiohttp.ClientError, CapfileApiError):
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            else:
                if not self._meters:
                    errors["base"] = "no_meters"
                else:
                    return await self.async_step_meter()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={},
        )

    # ------------------------------------------------------------------
    # Step 2 — Meter selection + /info retrieval
    # ------------------------------------------------------------------

    async def async_step_meter(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show the meter dropdown, then fetch /info for the selected PRM."""
        errors: dict[str, str] = {}

        if user_input is not None:
            prm = user_input[CONF_PRM]
            try:
                client = CapfileApiClient(self._api_key, prm)
                self._info = await client.async_get_info()
            except CapfileActionRequiredError as err:
                return self.async_abort(
                    reason="action_required",
                    description_placeholders={
                        "message": err.message,
                        "url": err.url,
                    },
                )
            except aiohttp.ClientResponseError as err:
                errors["base"] = {
                    401: "invalid_auth",
                    403: "forbidden",
                    429: "quota_exceeded",
                }.get(err.status, "cannot_connect")
            except (aiohttp.ClientError, CapfileApiError):
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            else:
                if self._info.has_soutirage:
                    return await self.async_step_prices()
                # Injection-only meter: skip prices step but still set energy option
                energy_minor_version = await _read_energy_minor_version(self.hass)
                energy_supported = (
                    energy_minor_version is None
                    or energy_minor_version == SUPPORTED_ENERGY_MINOR_VERSION
                )
                return self.async_create_entry(
                    title=f"Capfile – {self._info.name}",
                    data=self._build_entry_data({}),
                    options={CONF_AUTO_CONFIGURE_ENERGY: energy_supported},
                )

        return self.async_show_form(
            step_id="meter",
            data_schema=_meter_schema(self._meters),
            errors=errors,
            description_placeholders={},
        )

    # ------------------------------------------------------------------
    # Step 3 — Price confirmation (pre-filled from /info, labels from API)
    # ------------------------------------------------------------------

    async def async_step_prices(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show contract prices for review/adjustment, then create the entry."""
        if user_input is not None:
            _options_keys = {CONF_AUTO_UPDATE_PRICES, CONF_AUTO_CONFIGURE_ENERGY}
            price_data = {k: v for k, v in user_input.items() if k not in _options_keys}
            return self.async_create_entry(
                title=f"Capfile – {self._info.name}",
                data=self._build_entry_data(price_data),
                options={
                    CONF_AUTO_UPDATE_PRICES: user_input.get(CONF_AUTO_UPDATE_PRICES, False),
                    CONF_AUTO_CONFIGURE_ENERGY: user_input.get(CONF_AUTO_CONFIGURE_ENERGY, True),
                },
            )

        cadrans_display = ", ".join(
            self._info.cadrans[c].label for c in self._info.cadran_names
        )

        # Cocher par défaut si l'API a fourni des tarifs non nuls
        api_has_prices = (
            any(v > 0 for v in self._info.prices_eur.values())
            or self._info.subscription_eur_month > 0
        )

        # Vérifier la compatibilité du schéma du dashboard Énergie
        energy_minor_version = await _read_energy_minor_version(self.hass)
        energy_supported = (
            energy_minor_version is None
            or energy_minor_version == SUPPORTED_ENERGY_MINOR_VERSION
        )
        if not energy_supported:
            energy_compat_note = f" — ⚠️ schéma Énergie v{energy_minor_version} non testé, option désactivée"
        else:
            energy_compat_note = ""

        base_schema = _prices_schema(
            self._info.cadran_names,
            self._info.prices_eur,
            self._info.subscription_eur_month,
        )
        schema = vol.Schema({
            **base_schema.schema,
            vol.Optional(CONF_AUTO_UPDATE_PRICES, default=api_has_prices): BooleanSelector(),
            vol.Optional(CONF_AUTO_CONFIGURE_ENERGY, default=energy_supported): BooleanSelector(),
        })

        return self.async_show_form(
            step_id="prices",
            data_schema=schema,
            description_placeholders={
                "site_name": self._info.name,
                "prm": self._info.prm,
                "cadrans": cadrans_display,
                "offer_name": self._info.offer_name or "—",
                "power_kva": str(int(self._info.power_kva)) if self._info.power_kva else "—",
                "energy_compat_note": energy_compat_note,
                **_label_placeholders(self._info.cadran_names, self._info.cadran_labels),
            },
        )

    def _build_entry_data(self, price_input: dict) -> dict:
        """Build the config entry data dict from self._info + optional price fields."""
        return {
            CONF_API_KEY: self._api_key,
            CONF_PRM: self._info.prm,
            CONF_SITE_NAME: self._info.name,
            # Soutirage
            CONF_CADRANS: ",".join(self._info.cadran_names),
            CONF_CADRAN_LABELS: self._info.cadran_labels,
            CONF_CADRAN_COLORS: {n: i.color for n, i in self._info.cadrans.items()},
            CONF_OFFER_NAME: self._info.offer_name,
            CONF_POWER_KVA: self._info.power_kva,
            # Injection
            CONF_INJECTION_CADRANS: ",".join(self._info.injection_cadran_names),
            CONF_INJECTION_CADRAN_LABELS: self._info.injection_cadran_labels,
            CONF_INJECTION_CADRAN_COLORS: {n: i.color for n, i in self._info.injection_cadrans.items()},
            CONF_PUISSANCE_RACCORDEMENT: self._info.puissance_raccordement,
            # Price fields (price_1, price_2, …, subscription_cost) — empty for injection-only
            **price_input,
        }

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CapfileOptionsFlow:
        return CapfileOptionsFlow()


class CapfileOptionsFlow(config_entries.OptionsFlow):
    """Options flow — allows updating prices after initial setup."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        cadrans = _stored_cadrans(self.config_entry)
        cadran_labels: dict[str, str] = self.config_entry.data.get(CONF_CADRAN_LABELS, {})

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        def _get(key: str, fallback: float = 0.0) -> float:
            return float(
                self.config_entry.options.get(
                    key, self.config_entry.data.get(key, fallback)
                )
            )

        # Rebuild prices from indexed keys (price_1, price_2, …)
        prices_eur = {
            c: _get(f"price_{i}", DEFAULT_PRICES_EUR.get(c, 0.0))
            for i, c in enumerate(cadrans, 1)
        }
        subscription = _get(CONF_SUBSCRIPTION_COST, 0.0)
        auto_update = self.config_entry.options.get(CONF_AUTO_UPDATE_PRICES, False)
        auto_energy = self.config_entry.options.get(CONF_AUTO_CONFIGURE_ENERGY, False)

        base_schema = _prices_schema(cadrans, prices_eur, subscription, overrides={
            f"price_{i}": prices_eur[c] for i, c in enumerate(cadrans, 1)
        } | {CONF_SUBSCRIPTION_COST: subscription})

        schema = vol.Schema({
            **base_schema.schema,
            vol.Optional(CONF_AUTO_UPDATE_PRICES, default=auto_update): BooleanSelector(),
            vol.Optional(CONF_AUTO_CONFIGURE_ENERGY, default=auto_energy): BooleanSelector(),
        })

        cadrans_display = ", ".join(cadran_labels.get(c, c) for c in cadrans)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "cadrans": cadrans_display,
                **_label_placeholders(cadrans, cadran_labels),
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stored_cadrans(entry: config_entries.ConfigEntry) -> list[str]:
    """Return the ordered cadran list stored in the config entry."""
    raw = entry.data.get(CONF_CADRANS, "")
    return [c for c in raw.split(",") if c]
