"""relcore: the True Revenue Partner relationship layer.

Relationship cards (people, partners, partnerships, employees) in the Obsidian vault, a SQLite index and context
graph beside them, prepared actions that only a human can approve (relapprove), and a separate sender (relsend)
that checks every message. Standard library only, except slack_sdk in the approvals service.
"""
__version__ = "0.1.0"
SCHEMA_VERSION = 1
BUNDLE_VERSION = 1
