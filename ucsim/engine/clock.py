"""The shape of a simulated day: 24 hours, from 6 am to 6 am the next morning.

Behavior is resolved hour by hour: each hour everyone is somewhere (asleep at home, in class, on a shift, at a dinner,
out for food with a friend at 1 am) and the people who share a place can meet. Planned things (occasions, shifts,
classes, travel) are kept in minutes, so whether someone *can* make a 7:30 dinner after a shift that ends at 7:00 is
decided at minute resolution, while what happens there is resolved in the hours it overlaps (weighted by the minutes
of overlap).

A simulated day runs from 6 am to 6 am, so the small hours belong to the evening before them: minute 1500 of a Friday
is 1 am on Saturday morning ("Friday night"). Minutes past 1440 are those small hours; `day_minute` maps a clock time
like 1 am (60) onto the day.

For words and records the hours are grouped into five parts of the day (events, messages and conversations carry the
part, not the hour):

    part 0  morning        6 am–noon
    part 1  afternoon      noon–5 pm
    part 2  evening        5–8 pm
    part 3  late evening   8 pm–midnight
    part 4  night          midnight–6 am

A "block" in the engine is one hour of the day (step 0 = 6–7 am … step 23 = 5–6 am).
"""
from __future__ import annotations

import numpy as np

DAY0 = 6 * 60                       # the simulated day starts at 6 am
N_BLOCKS = 24                       # hourly steps
START = (DAY0 + 60 * np.arange(N_BLOCKS)).astype(np.int32)
END = (START + 60).astype(np.int32)
LENGTH_H = (END - START) / 60.0
HOUR = ((START // 60) % 24).astype(np.int32)      # the clock hour each step starts at (6, 7, … 23, 0, … 5)
# the simulation clock (Simulation.w.hour runs 6 … 29) at which each step runs: the start of its hour
BLOCK_HOUR = tuple(int(s // 60) for s in START)
SLOTS_PER_WEEK = 7 * N_BLOCKS
DAY_START, DAY_END = int(START[0]), int(END[-1])

PARTS = ("morning", "afternoon", "evening", "late", "night")
PART_LABELS = ("Morning · 6 am–noon", "Afternoon · noon–5 pm", "Evening · 5–8 pm", "Late evening · 8 pm–midnight",
               "Night · midnight–6 am")
PART_START = np.array([6 * 60, 12 * 60, 17 * 60, 20 * 60, 24 * 60], np.int32)
PART_END = np.array([12 * 60, 17 * 60, 20 * 60, 24 * 60, 30 * 60], np.int32)
N_PARTS = len(PARTS)
PART = (np.searchsorted(PART_END, START, side="right")).astype(np.int8)    # part of the day of each step
SOCIAL_NIGHT = tuple(int(s) for s in np.flatnonzero(PART >= 2))          # evening, late evening and night
# a representative clock hour for each part (for words and for records that carry only the part)
PART_HOUR = (9, 14, 18, 21, 25)


def _hm(minute: int) -> str:
    h, m = divmod(int(minute), 60)
    h %= 24
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


BLOCK_NAMES = tuple(_hm(s) for s in START)
BLOCK_LABELS = tuple(f"{_hm(s)}–{_hm(e)}" for s, e in zip(START, END))

# Encounter rates and conversation lengths were calibrated per "old block" of five hours (the first engine had three:
# morning, afternoon, a five-hour evening), and the four-block day that followed spread one old evening over the six
# hours from 5:30 to 11:30 pm. Ambient time (home, the complex, a venue, a shift) in each hour is its share of such an
# old block: a fifth of a block per daytime hour, a sixth per hour from 5:30 pm on (the small hours too), so a day like
# the old ones adds up to the same contact the rates were fitted to, and the new hours (early mornings, after
# midnight) add contact only for the people actually awake and together then.
_EVENING_FROM = 17 * 60 + 30
LEGACY_SHARE = (np.clip(np.minimum(END, _EVENING_FROM) - START, 0, 60) / 60 * 0.2
                + np.clip(END - np.maximum(START, _EVENING_FROM), 0, 60) / 60 / 6).astype(np.float32)


def day_minute(minute) -> np.ndarray | int:
    """A clock time in minutes after midnight (0–1439) placed on the simulated day: before 6 am it is the small hours
    at the end of the day (1 am → 1500). Minutes already past 1440 are kept."""
    m = np.asarray(minute)
    out = np.where(m < DAY0, m + 1440, m)
    return int(out) if out.ndim == 0 else out


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
    if not (0 <= h <= 30 and 0 <= m < 60):
        raise ValueError(f"not a clock time: {text!r}")
    return h * 60 + m


def main_blocks(start, dur, min_minutes: int = 30) -> list[int]:
    """Hours a planned thing occupies: those holding at least `min_minutes` of it (or its largest share)."""
    ov = [int(overlap(start, dur, b)) for b in range(N_BLOCKS)]
    out = [b for b, m in enumerate(ov) if m >= min_minutes]
    return out or ([int(np.argmax(ov))] if max(ov) > 0 else [])


def block_mask(start, dur, min_minutes: int = 30) -> np.ndarray:
    """Bit mask (bit b = step b) of the hours each planned thing occupies (vectorized `main_blocks`)."""
    s = np.asarray(start, np.int64)
    d = np.asarray(dur, np.int64)
    ov = np.stack([overlap(s, d, b) for b in range(N_BLOCKS)], axis=-1)          # (..., 24)
    need = np.minimum(min_minutes, np.maximum(ov.max(axis=-1, keepdims=True), 1))
    bits = (ov >= need) & (ov > 0)
    return (bits.astype(np.uint32) << np.arange(N_BLOCKS, dtype=np.uint32)).sum(axis=-1).astype(np.uint32)


def slot(weekday, block):
    """Weekly slot index (0..SLOTS_PER_WEEK-1) for a weekday (Mon=0) and hour step."""
    return np.asarray(weekday) * N_BLOCKS + np.asarray(block)


def block_of(minute) -> np.ndarray:
    """The hour step a minute of the day falls in (clock times before 6 am count as the small hours; −1 outside)."""
    m = day_minute(np.asarray(minute))
    b = (np.asarray(m) - DAY0) // 60
    return np.where((m >= DAY_START) & (m < DAY_END), b, -1)


def part_of(minute) -> np.ndarray:
    """The part of the day (0 morning … 4 night) a minute of the day falls in."""
    m = day_minute(np.asarray(minute))
    return np.clip(np.searchsorted(PART_END, m, side="right"), 0, N_PARTS - 1)


def overlap(start, dur, block: int) -> np.ndarray:
    """Minutes of [start, start+dur) inside hour step `block`."""
    s = np.asarray(start, np.int32)
    e = s + np.asarray(dur, np.int32)
    return np.clip(np.minimum(e, END[block]) - np.maximum(s, START[block]), 0, None)


def hhmm(minute: int) -> str:
    """'7:30 pm' style clock text (minutes past midnight of the day wrap: 1500 is '1 am')."""
    return _hm(minute)
