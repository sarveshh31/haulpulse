"""Static configuration for the HaulPulse data generator."""

# City centres, share of trips, and RTO plate prefix (used for vehicle numbers)
CITIES = {
    "Mumbai":    {"lat": 19.0760, "lng": 72.8777, "weight": 0.16, "plate": "MH02"},
    "Delhi":     {"lat": 28.6139, "lng": 77.2090, "weight": 0.16, "plate": "DL01"},
    "Bengaluru": {"lat": 12.9716, "lng": 77.5946, "weight": 0.15, "plate": "KA01"},
    "Hyderabad": {"lat": 17.3850, "lng": 78.4867, "weight": 0.11, "plate": "TS09"},
    "Chennai":   {"lat": 13.0827, "lng": 80.2707, "weight": 0.09, "plate": "TN01"},
    "Pune":      {"lat": 18.5204, "lng": 73.8567, "weight": 0.09, "plate": "MH12"},
    "Kolkata":   {"lat": 22.5726, "lng": 88.3639, "weight": 0.07, "plate": "WB02"},
    "Ahmedabad": {"lat": 23.0225, "lng": 72.5714, "weight": 0.07, "plate": "GJ01"},
    "Jaipur":    {"lat": 26.9124, "lng": 75.7873, "weight": 0.05, "plate": "RJ14"},
    "Nagpur":    {"lat": 21.1458, "lng": 79.0882, "weight": 0.05, "plate": "MH31"},
}

# Messy spellings seen in real data. Phase 4 maps these back to the clean name.
CITY_ALIASES = {
    "Mumbai":    ["Bombay", "mumbai", "MUM", "MUMBAI "],
    "Delhi":     ["New Delhi", "delhi", "DEL", "DELHI"],
    "Bengaluru": ["Bangalore", "BLR", "bengaluru ", "BENGALURU", "Bengalore"],
    "Hyderabad": ["Hyd", "hyderabad", "HYDERABAD "],
    "Chennai":   ["Madras", "chennai", "CHENNAI"],
    "Pune":      ["pune", "PUNE", "Poona"],
    "Kolkata":   ["Calcutta", "kolkata", "KOLKATA "],
    "Ahmedabad": ["Ahmedabad ", "amdavad", "AHMEDABAD"],
    "Jaipur":    ["jaipur", "JAIPUR", "Jaipur "],
    "Nagpur":    ["nagpur", "NGP", "NAGPUR "],
}

# base fare (Rs), per-km rate (Rs), average speed (km/h), trip distance range (km), share of trips
VEHICLES = {
    "TWO_WHEELER":   {"base": 30,  "per_km": 8,  "speed_kmph": 25, "dist_km": (1, 15),  "weight": 0.40},
    "THREE_WHEELER": {"base": 80,  "per_km": 14, "speed_kmph": 22, "dist_km": (2, 30),  "weight": 0.20},
    "MINI_TRUCK":    {"base": 250, "per_km": 22, "speed_kmph": 28, "dist_km": (3, 60),  "weight": 0.25},
    "TEMPO":         {"base": 400, "per_km": 30, "speed_kmph": 30, "dist_km": (5, 80),  "weight": 0.15},
}

STATUS_WEIGHTS = {
    "COMPLETED": 0.87,
    "CANCELLED_BY_CUSTOMER": 0.06,
    "CANCELLED_BY_DRIVER": 0.05,
    "NO_DRIVER_FOUND": 0.02,  # legitimately has no driver_id
}

CANCEL_REASONS = {
    "CANCELLED_BY_CUSTOMER": ["Customer changed mind", "Booked by mistake",
                              "Found another vehicle", "Wait time too long"],
    "CANCELLED_BY_DRIVER": ["Vehicle breakdown", "Customer unreachable",
                            "Pickup location too far", "Driver unavailable"],
    "NO_DRIVER_FOUND": ["No driver available nearby"],
}

PAYMENT_MODES = {"UPI": 0.55, "CASH": 0.30, "WALLET": 0.10, "CARD": 0.05}

# Relative demand for each hour of the day (0-23). Peaks in the morning and evening.
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2,
                4, 6, 9, 10, 10, 9,
                8, 7, 7, 7, 8, 10,
                10, 9, 7, 5, 3, 2]

PEAK_HOURS = {8, 9, 10, 11, 17, 18, 19}
PEAK_SURGE = 1.2

# How the dirty-record budget is split across defect types (must sum to 1.0)
DIRTY_WEIGHTS = {
    "city_variant": 0.22,             # fixable: "Bangalore" -> "Bengaluru"
    "status_case": 0.07,              # fixable: "completed " -> "COMPLETED"
    "duplicate": 0.12,                # exact duplicate row
    "negative_fare": 0.08,
    "delivered_before_pickup": 0.08,
    "missing_driver": 0.08,
    "missing_fare": 0.06,
    "bad_status": 0.06,
    "bad_distance": 0.08,
    "gps_out_of_india": 0.06,
    "unparseable_timestamp": 0.05,
    "missing_city": 0.04,
}

assert abs(sum(DIRTY_WEIGHTS.values()) - 1.0) < 1e-9, "DIRTY_WEIGHTS must sum to 1"
assert abs(sum(c["weight"] for c in CITIES.values()) - 1.0) < 1e-9
assert abs(sum(v["weight"] for v in VEHICLES.values()) - 1.0) < 1e-9