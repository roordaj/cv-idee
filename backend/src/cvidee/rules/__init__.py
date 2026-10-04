"""Versioned detection rules.

Each rule has an id and semantic version, declares required and optional signals,
installation and operating-mode applicability and a parameter schema, and evaluates a
rule context into finding candidates with a certainty category and hypotheses. Also
determines analysis availability (available / limited / unavailable) from mapped
signals, coverage and resolution.
"""
