"""Analysis runner.

Periodically runs the pure pipeline over a sliding window (watermark minus lookback up
to now minus settle time), upserts derived results on deterministic keys and records the
rule versions and configuration hash per run. Historical import uses the same runner in
chunks.
"""
