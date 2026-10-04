"""Findings and recommendations engine.

Deduplicates candidates per (rule, scope), bundles related candidates, prioritises
deterministically, manages the finding lifecycle and recovery criteria, derives
recommendations and their follow-up status, and snapshots advice history (measurement
period, settings, rule version and parameters).
"""
