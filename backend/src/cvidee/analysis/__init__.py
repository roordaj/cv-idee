"""Pure analysis pipeline (no I/O).

Steps on immutable data: timeline (validity intervals including explicit unknown), data
quality (stale / invalid / implausible / counter resets), operating modes, burner cycles
and metrics. The same functions serve live processing and historical import, so
processing in chunks yields the same result as processing at once.
"""
