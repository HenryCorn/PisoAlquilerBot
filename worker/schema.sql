CREATE TABLE IF NOT EXISTS listings (
    fingerprint TEXT PRIMARY KEY,
    portal_ids TEXT NOT NULL,
    urls TEXT NOT NULL,
    last_rent INTEGER NOT NULL,
    last_total INTEGER,
    first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT
);
CREATE TABLE IF NOT EXISTS saved_homes (
    fingerprint TEXT PRIMARY KEY,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hidden_buildings (
    normalized_street TEXT PRIMARY KEY,
    hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
