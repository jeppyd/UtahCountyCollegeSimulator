"""The shape of a simulated day: four activity blocks with clock times.

Behavior is resolved per block (who is where, who meets whom). Planned occasions, shifts and travel are kept in
minutes, so whether someone *can* make a 7:30 dinner after a shift that ends at 7:00 is decided at minute resolution,
while what happens there is resolved in the blocks the occasion overlaps (weighted by the minutes of overlap).

    block 0  morning        08:00–12:30
    block 1  afternoon      12:30–17:30
    block 2  evening        17:30–20:15
    block 3  late evening   20:15–23:30

The map and timelines show these four moments; nothing in the model moves minute by minute.
"""
from __future__ import annotations

import numpy as np

BLOCKS = (
    ("morning", 8 * 60, 12 * 60 + 30),
    ("afternoon", 12 * 60 + 30, 17 * 60 + 30),
    ("evening", 17 * 60 + 30, 20 * 60 + 15),
    ("late", 20 * 60 + 15, 23 * 60 + 30),
)
N_BLOCKS = len(BLOCKS)
BLOCK_NAMES = tuple(b[0] for b in BLOCKS)
BLOCK_LABELS = ("Morning · 8 am–12:30", "Afternoon · 12:30–5:30", "Evening · 5:30–8:15", "Late evening · 8:15–11:30")
START = np.array([b[1] for b in BLOCKS], np.int32)
END = np.array([b[2] for b in BLOCKS], np.int32)
LENGTH_H = (END - START) / 60.0
EVENING = (2, 3)            # the two evening blocks
# clock hour at which each block's phase runs (Simulation.advance_hours steps whole hours)
BLOCK_HOUR = (8, 13, 18, 20)
SLOTS_PER_WEEK = 7 * N_BLOCKS
# the old three-block day (8, 13, 18) had a five-hour evening; per-block encounter rates and durations calibrated on it
# are scaled by this block's share of that evening (see encounters.py)
LEGACY_LEN_H = (5.0, 5.0, 5.0)
# Ambient time (home, the complex, a venue, a shift) in each block as a share of the old block it replaces: the
# morning and afternoon by length, the two evening blocks by their share of the evening they split, so a whole
# evening at home (0.46 + 0.54) adds up to exactly one old evening and calibrated encounter rates carry over.
LEGACY_SHARE = np.array([LENGTH_H[0] / LEGACY_LEN_H[0], LENGTH_H[1] / LEGACY_LEN_H[1],
                         *(LENGTH_H[b] / LENGTH_H[list(EVENING)].sum() for b in EVENING)], np.float32)
DAY_START, DAY_END = int(START[0]), int(END[-1])


def parse_hhmm(text) -> int:
    """'19:30' or '7:30 pm' or 1170 -> minutes after midnight."""
    if isinstance(text, (int, float, np.integer, np.floating)):
        return int(text)
    s = str(text).strip().lower().replace(".", "")
    pm, am = s.endswith("pm"), s.endswith("am")
    s = s[:-2].strip() if pm or am else s
    h, _, m = s.partition(":")
    h, m = int(h), int(m or 0)
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"not a clock time: {text!r}")
    return h * 60 + m


def main_blocks(start, dur, min_minutes: int = 30) -> list[int]:
    """Blocks a planned thing occupies: those holding at least `min_minutes` of it (or its largest share)."""
    ov = [int(overlap(start, dur, b)) for b in range(N_BLOCKS)]
    out = [b for b, m in enumerate(ov) if m >= min_minutes]
    return out or ([int(np.argmax(ov))] if max(ov) > 0 else [])


def slot(weekday, block):
    """Weekly slot index (0..SLOTS_PER_WEEK-1) for a weekday (Mon=0) and block."""
    return np.asarray(weekday) * N_BLOCKS + np.asarray(block)


def block_of(minute) -> np.ndarray:
    """The block a clock minute falls in (−1 before 8 am or after 11:30 pm)."""
    m = np.asarray(minute)
    b = np.searchsorted(END, m, side="right")
    return np.where((m >= START[0]) & (m < END[-1]), b, -1)


def overlap(start, dur, block: int) -> np.ndarray:
    """Minutes of [start, start+dur) inside `block`."""
    s = np.asarray(start, np.int32)
    e = s + np.asarray(dur, np.int32)
    return np.clip(np.minimum(e, END[block]) - np.maximum(s, START[block]), 0, None)


def hhmm(minute: int) -> str:
    """'7:30 pm' style clock text."""
    minute = int(minute)
    h, m = divmod(minute, 60)
    suffix = "am" if h < 12 or h == 24 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"
