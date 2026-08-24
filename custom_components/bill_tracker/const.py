"""Constants for Bill Tracker."""

DOMAIN = "bill_tracker"
STORAGE_VERSION = 1
STORAGE_SCHEMA_VERSION = 3
STORAGE_KEY = "bill_tracker.expenses"
EVENT_UPDATED = "bill_tracker_updated"
FRONTEND_VERSION = "0.3.0"

SUPPORTED_INTERVALS = (1, 2, 3, 4, 6, 12)
INTERVAL_LABELS = {
    1: "Mensile",
    2: "Bimestrale",
    3: "Trimestrale",
    4: "Quadrimestrale",
    6: "Semestrale",
    12: "Annuale",
}

DEFAULT_CATEGORIES = [
    {"id": "internet", "name": "Internet", "interval_months": 1, "enabled": True},
    {"id": "electricity", "name": "Elettricità", "interval_months": 1, "enabled": True},
    {"id": "water", "name": "Acqua", "interval_months": 2, "enabled": True},
    {"id": "gas", "name": "Gas", "interval_months": 2, "enabled": True},
    {"id": "condominium", "name": "Condominio", "interval_months": 1, "enabled": True},
    {"id": "phone", "name": "Telefono", "interval_months": 1, "enabled": True},
    {"id": "tari", "name": "TARI / Rifiuti", "interval_months": 12, "enabled": True},
    {"id": "other", "name": "Altro", "interval_months": 1, "enabled": True},
]
