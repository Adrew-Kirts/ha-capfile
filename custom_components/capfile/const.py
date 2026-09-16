"""Constants for the Capfile integration."""

DOMAIN = "capfile"

# Fixed API base URL — no user configuration needed
API_BASE_URL = "https://api.capfile.com/free/v1"

# Config entry keys — credentials
CONF_API_KEY = "api_key"
CONF_PRM = "prm"

# Config entry keys — fetched from /info at setup time
CONF_SITE_NAME = "site_name"
CONF_CADRANS = "cadrans"          # comma-separated ordered cadran names
CONF_CADRAN_LABELS = "cadran_labels"   # dict {cadran: label} from API
CONF_CADRAN_COLORS = "cadran_colors"   # dict {cadran: hex color} from API
CONF_SUBSCRIPTION_COST = "subscription_cost"  # €/month from API
CONF_POWER_KVA = "power_kva"           # subscribed power in kVA
CONF_OFFER_NAME = "offer_name"         # tariff offer name

# Config entry keys — injection (P4/prosumer meters)
CONF_INJECTION_CADRANS = "injection_cadrans"              # comma-separated ordered cadran names
CONF_INJECTION_CADRAN_LABELS = "injection_cadran_labels"  # dict {cadran: label}
CONF_INJECTION_CADRAN_COLORS = "injection_cadran_colors"  # dict {cadran: hex color}
CONF_PUISSANCE_RACCORDEMENT = "puissance_raccordement"    # connection power in kVA

# Price config keys — prefix + cadran name (e.g. "price_BUHC")
# Stored in config entry data (from API) and can be overridden via options.
CONF_PRICE_PREFIX = "price_"

# Fallback labels if /info labels are unavailable
CADRAN_LABELS_DEFAULT: dict[str, str] = {
    "BASE": "Base",
    "HP": "Heures Pleines",
    "HC": "Heures Creuses",
    "BCHC": "Blanc Heures Creuses",
    "BCHP": "Blanc Heures Pleines",
    "BUHC": "Bleu Heures Creuses",
    "BUHP": "Bleu Heures Pleines",
    "RHC": "Rouge Heures Creuses",
    "RHP": "Rouge Heures Pleines",
}

# Fallback prices in €/kWh if /info prices are unavailable
DEFAULT_PRICES_EUR: dict[str, float] = {
    "BASE": 0.2516,
    "HP": 0.2516,
    "HC": 0.1740,
    "BCHC": 0.1499,
    "BCHP": 0.1871,
    "BUHC": 0.1325,
    "BUHP": 0.1612,
    "RHC": 0.1575,
    "RHP": 0.7060,
}

UNIT_ENERGY = "kWh"
UNIT_COST = "EUR"

# Dispatcher signal — fired after each sync to update sensor entities
SIGNAL_UPDATE = f"{DOMAIN}_update"

# Options flag — automatically fetch and apply updated prices from the API
CONF_AUTO_UPDATE_PRICES = "auto_update_prices"

# Options flag — automatically configure the Energy dashboard on first setup
CONF_AUTO_CONFIGURE_ENERGY = "auto_configure_energy"
