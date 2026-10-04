"""Ingest from Home Assistant.

Live WebSocket subscription to ``state_changed`` (with reconnect and entity listing) and
idempotent, resumable historical import via the HA REST history API. Stores raw
observations and connection events; deduplicates identical states and keeps repeated
equal values as confirmations (heartbeats), not transitions.
"""
