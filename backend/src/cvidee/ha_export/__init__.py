"""Export of summary sensors back to Home Assistant.

Publishes summary entities via MQTT discovery (retained config and state, stable
``unique_id`` values, availability topic with last will) under one ``CV-analyse`` device.
Only the own topics ``cv_analyse/#`` and ``homeassistant/+/cv_analyse/#`` are used.
Fallback without a broker: HA REST ``POST /api/states``.
"""
