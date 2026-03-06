-- Phase 2.1: Soul engine tables — souls cache + character state

CREATE TABLE souls (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    yaml_hash   TEXT NOT NULL,
    definition  TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE character_state (
    soul_id     TEXT PRIMARY KEY REFERENCES souls(id),
    state_json  TEXT NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ensure only one soul is active at a time (covers both INSERT and UPDATE)
CREATE TRIGGER souls_single_active_on_update
AFTER UPDATE OF is_active ON souls
WHEN NEW.is_active = 1 AND OLD.is_active = 0
BEGIN
    UPDATE souls SET is_active = 0
    WHERE id != NEW.id AND is_active = 1;
END;

CREATE TRIGGER souls_single_active_on_insert
AFTER INSERT ON souls
WHEN NEW.is_active = 1
BEGIN
    UPDATE souls SET is_active = 0
    WHERE id != NEW.id AND is_active = 1;
END;
