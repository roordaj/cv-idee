"""Notification policy.

Maps severity to channel (direct / daily bundle / weekly report / none), sends one
notification per finding (again only on deterioration) via a Home Assistant
``notify.*`` service and always fires the ``cv_analyse_finding`` event.
"""
