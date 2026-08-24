"""Constants for Bill Tracker."""

DOMAIN = "bill_tracker"
STORAGE_VERSION = 1
STORAGE_SCHEMA_VERSION = 5
STORAGE_KEY = "bill_tracker.expenses"
EVENT_UPDATED = "bill_tracker_updated"
FRONTEND_VERSION = "0.4.4"

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
    {"id": "internet", "name": "Internet", "interval_months": 1, "enabled": True, "color": "#5B8FF9"},
    {"id": "electricity", "name": "Elettricità", "interval_months": 1, "enabled": True, "color": "#F6BD16"},
    {"id": "water", "name": "Acqua", "interval_months": 2, "enabled": True, "color": "#5AD8A6"},
    {"id": "gas", "name": "Gas", "interval_months": 2, "enabled": True, "color": "#E8684A"},
    {"id": "condominium", "name": "Condominio", "interval_months": 1, "enabled": True, "color": "#9270CA"},
    {"id": "phone", "name": "Telefono", "interval_months": 1, "enabled": True, "color": "#6DC8EC"},
    {"id": "tari", "name": "TARI / Rifiuti", "interval_months": 12, "enabled": True, "color": "#FF9D4D"},
    {"id": "other", "name": "Altro", "interval_months": 1, "enabled": True, "color": "#A0A7B4"},
]

FALLBACK_COLORS = (
    "#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16", "#E8684A",
    "#6DC8EC", "#9270CA", "#FF9D4D", "#269A99", "#FF99C3",
)
