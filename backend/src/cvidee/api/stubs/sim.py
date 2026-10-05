"""Deterministic port of ``buildSim()`` from design v3 (``CV-analyse-v3.dc.html``).

Six hours of boiler behaviour, Sunday 4 October 2026 06:00-12:00 Europe/Amsterdam, in
minutes from the start (``m``). Arithmetic follows the JavaScript original operation by
operation so the numbers match the design; ``Math.round`` is ported as round-half-up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Literal

SimMode = Literal["cv", "tw", "naloop", "onbekend", "standby"]
SimEnd = Literal["stop", "tapwater", "onvolledig", "vraag"]

START = datetime(2026, 10, 4, 4, 0, tzinfo=UTC)
"""Minute 0 of the simulation (06:00 CEST)."""
END_MINUTE = 360
GAP = (250.0, 280.0)
"""CAN outage 10:10-10:40: no data."""


def at(minute: float) -> datetime:
    """Timestamp of simulation minute ``minute``."""
    return START + timedelta(minutes=minute)


def js_round(value: float) -> int:
    """JavaScript ``Math.round`` (half rounds towards +infinity)."""
    return math.floor(value + 0.5)


def fmt_duration(minutes: float) -> str:
    """``D()``: minutes as ``m:ss``."""
    return f"{math.floor(minutes)}:{js_round((minutes % 1) * 60):02d}"


def nl(value: float, digits: int = 1) -> str:
    """``nl()``: fixed decimals with a decimal comma."""
    return f"{value:.{digits}f}".replace(".", ",")


def clock(minute: float) -> str:
    """``H()``: local clock time of a simulation minute."""
    total = 360 + js_round(minute)
    return f"{total // 60:02d}:{total % 60:02d}"


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2


@dataclass(slots=True)
class SimCycle:
    s: float
    e: float
    mode: Literal["cv", "tw"]
    end: SimEnd
    n: int = 0
    d: float = 0.0
    max_t: float = 0.0
    gew: float | None = None
    mod: float = 0.0
    kort: bool = False


@dataclass(frozen=True, slots=True)
class SimPoint:
    m: float
    t: float
    r: float
    gew: float | None
    mod: float


@dataclass(frozen=True, slots=True)
class SimModeSpan:
    s: float
    e: float
    m: SimMode


@dataclass(frozen=True, slots=True)
class SimStats:
    observed_hours: float
    starts_per_hour: float
    ch_cycles: int
    dhw_cycles: int
    short_cycles: int
    ch_cycles_before_gap: int
    median_burn_min: float
    mean_burn_min: float
    median_pause_min: float
    total_burn_min: int


@dataclass(frozen=True, slots=True)
class Sim:
    cycles: list[SimCycle]
    modes: list[SimModeSpan]
    points: list[SimPoint | None]
    stats: SimStats
    pauses: list[float] = field(default_factory=list)


MODES = [
    SimModeSpan(0, 72, "cv"),
    SimModeSpan(72, 82, "tw"),
    SimModeSpan(82, 86, "naloop"),
    SimModeSpan(86, 250, "cv"),
    SimModeSpan(250, 280, "onbekend"),
    SimModeSpan(280, 320, "cv"),
    SimModeSpan(320, 360, "standby"),
]


def _mode_at(m: float) -> SimMode:
    for span in MODES:
        if span.s <= m < span.e:
            return span.m
    return "standby"


@cache
def build_sim() -> Sim:
    """Run the simulation once (pure and deterministic)."""
    iv: list[SimCycle] = []
    pat = [2.5, 2, 3.5, 2.5, 1.5, 2, 4, 2.5, 3, 2]
    i, t = 0, 5.0
    while t < 64:
        d = pat[i % 10]
        iv.append(SimCycle(t, t + d, "cv", "stop"))
        t += d + 5.5 + (i % 3)
        i += 1
    iv.append(SimCycle(72, 82, "tw", "tapwater"))
    t = 87
    while t < 204:
        d = pat[i % 10]
        iv.append(SimCycle(t, t + d, "cv", "stop"))
        t += d + 5.5 + (i % 3)
        i += 1
    t = max(t, 208)
    while t < 230:
        d = 7 + (i % 3)
        iv.append(SimCycle(t, t + d, "cv", "stop"))
        t += d + 5
        i += 1
    iv.append(SimCycle(245, 250, "cv", "onvolledig"))
    iv.append(SimCycle(282, 320, "cv", "vraag"))

    temp, ret = 46.0, 39.0
    pts: list[SimPoint | None] = []
    for step in range(0, END_MINUTE * 2 + 1):
        m = step / 2
        if GAP[0] <= m < GAP[1]:
            pts.append(None)
            temp, ret = 36.0, 33.0
            continue
        on = next((c for c in iv if c.s <= m < c.e), None)
        mode = _mode_at(m)
        gew = 70.0 if mode == "tw" else 55.0 if mode in ("cv", "naloop") else None
        if on is not None:
            tgt = 72 if on.mode == "tw" else (55.5 if on.e - on.s > 20 else 59.5)
            temp += (tgt - temp) * (0.35 if on.mode == "tw" else 0.5) * 0.5
        else:
            temp += (34 - temp) * 0.05 * 0.5
        ret += ((temp - (10 if on is not None else 3)) - ret) * 0.15 * 0.5
        if on is None:
            mod = 0.0
        elif m - on.s < 1:
            mod = 45.0
        elif on.mode == "tw":
            mod = 62.0
        else:
            mod = 24.0 if on.e - on.s > 20 else 19.0
        pts.append(SimPoint(m, temp, ret, gew, mod))

    for k, c in enumerate(iv):
        c.n = k + 1
        c.d = c.e - c.s
        in_pts = [p for p in pts if p is not None and c.s <= p.m <= c.e]
        c.max_t = max(p.t for p in in_pts)
        c.gew = in_pts[0].gew if in_pts else None
        mods = [p.mod for p in in_pts if p.mod > 0]
        c.mod = sum(mods) / len(mods) if mods else 0.0
        c.kort = c.mode == "cv" and c.end == "stop" and c.d < 3

    cv = [c for c in iv if c.mode == "cv" and c.end != "onvolledig"]
    pauses: list[float] = []
    for k in range(1, len(iv)):
        a, b = iv[k - 1], iv[k]
        if a.mode == "cv" and b.mode == "cv" and b.s < 250 and a.end == "stop":
            pauses.append(b.s - a.e)
    all_cv = [c for c in iv if c.mode == "cv"]
    stats = SimStats(
        observed_hours=5.5,
        starts_per_hour=len(all_cv) / 5.5,
        ch_cycles=len(all_cv),
        dhw_cycles=sum(1 for c in iv if c.mode == "tw"),
        short_cycles=sum(1 for c in iv if c.kort),
        ch_cycles_before_gap=sum(1 for c in cv if c.s < 250),
        median_burn_min=median([c.d for c in cv]),
        mean_burn_min=sum(c.d for c in cv) / len(cv),
        median_pause_min=median(pauses),
        total_burn_min=js_round(sum(c.d for c in all_cv)),
    )
    return Sim(cycles=iv, modes=MODES, points=pts, stats=stats, pauses=pauses)
