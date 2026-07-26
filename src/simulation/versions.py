"""Version identifiers for the model and its serialized projections.

These live apart from the engine so that observation and the engine can both
declare them without importing each other. ``src.simulation.engine`` re-exports
both names, so existing imports from there continue to work.
"""

# Incremented when a mechanic changes such that runs are no longer comparable
# across revisions for the same configuration and seed.
MODEL_VERSION = "0.3"

# Incremented when the shape of Simulation.snapshot() changes.
SNAPSHOT_SCHEMA_VERSION = 3
