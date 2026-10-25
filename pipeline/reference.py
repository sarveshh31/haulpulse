"""Reference data and business thresholds owned by the pipeline.

Kept separate from the generator on purpose: in real life the team maintains
this mapping, and any spelling not listed here is quarantined as UNKNOWN_CITY
so an analyst can add it and re-run.
"""

CITY_ALIASES = {
    "Mumbai":    ["Bombay", "MUM"],
    "Delhi":     ["New Delhi", "DEL"],
    "Bengaluru": ["Bangalore", "BLR", "Bengalore"],
    "Hyderabad": ["Hyd"],
    "Chennai":   ["Madras"],
    "Pune":      ["Poona"],
    "Kolkata":   ["Calcutta"],
    "Ahmedabad": ["Amdavad"],
    "Jaipur":    [],
    "Nagpur":    ["NGP"],
}

# lower-cased spelling -> canonical city name
CITY_LOOKUP: dict[str, str] = {}
for canonical, aliases in CITY_ALIASES.items():
    CITY_LOOKUP[canonical.lower()] = canonical
    for alias in aliases:
        CITY_LOOKUP[alias.lower()] = canonical

VALID_STATUSES = {"COMPLETED", "CANCELLED_BY_CUSTOMER", "CANCELLED_BY_DRIVER", "NO_DRIVER_FOUND"}
VALID_VEHICLE_TYPES = {"TWO_WHEELER", "THREE_WHEELER", "MINI_TRUCK", "TEMPO"}

# Rough bounding box of India
INDIA_LAT = (6.0, 38.0)
INDIA_LNG = (68.0, 98.0)

MAX_DISTANCE_KM = 500