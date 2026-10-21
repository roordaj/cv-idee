"""Persist lifecycle and idempotent references for normal-behavior models."""

from cvidee.normal_behavior.backend import NormalBehaviorBackend, capture_metric_references

__all__ = ["NormalBehaviorBackend", "capture_metric_references"]
