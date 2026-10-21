"""Bedrooms: which room of their home each person sleeps in (the units' rooms: population/structure.py Units).

`assign_all` gives everyone a bed when a world is built; `sync` runs every night and settles whoever moved, arrived
or left since. A person moving in takes, in order: their spouse's room; a room where a close friend already sleeps
(stage ≥ 3) with a free bed; the room with the most free beds (the first such room). When every bed is taken (a
What-if cut the beds, or a crowded house), they double up in the largest room. No random draws: rooms follow from
who lives where, so paired worlds stay comparable.

Bedroom-mates (`room_mates`) are the people sharing a person's room; the simulation and the map read them here.
"""
from __future__ import annotations

import numpy as np

NO_ROOM = -1


def ensure(P):
    if "room" not in P.internal:
        P.add_internal("room", np.int32, NO_ROOM)
    return P.internal["room"]


def _occupancy(room: np.ndarray, live: np.ndarray, n_rooms: int) -> np.ndarray:
    r = room[live & (room >= 0)]
    return np.bincount(r, minlength=n_rooms).astype(np.int32)


def assign_all(w):
    """Beds for everyone at home when a world is built: within each home, couples first (into the first two-bed
    room), then everyone else in id order, filling rooms in order."""
    P, U = w.P, w.units
    room = ensure(P)
    room[: P.n] = NO_ROOM
    if U.room0 is None:
        return
    unit = P["unit_id"]
    live = np.flatnonzero((unit >= 0) & P["present"])
    if not len(live):
        return
    partner = P["partner_id"] if "partner_id" in P else np.full(P.n, -1)
    # couples sort together: key = the smaller id of the pair; singles after couples
    pid = partner[live]
    coupled = (pid >= 0) & (pid < P.n)
    coupled[coupled] &= unit[np.maximum(pid[coupled], 0)] == unit[live[coupled]]
    key2 = np.where(coupled, np.minimum(live, np.maximum(pid, 0)), live)
    order = np.lexsort((live, key2, ~coupled, unit[live]))
    ids = live[order]
    u = unit[ids]
    # rank of each person within their home, then the bed of that rank (rooms filled in order; two-bed rooms first
    # for couples is approximated by the rooms' own order, which puts the main bedroom first)
    start = np.r_[0, np.flatnonzero(np.diff(u)) + 1]
    rank = np.arange(len(ids)) - np.repeat(start, np.diff(np.r_[start, len(ids)]))
    cum = np.cumsum(U.room_cap.astype(np.int64))
    total = np.r_[0, cum]                                # beds before each room (flat bed numbering)
    beds0 = total[U.room0[u]]
    home_beds = total[U.room0[u] + U.n_rooms[u].astype(np.int64)] - beds0
    flat = beds0 + np.minimum(rank, np.maximum(home_beds - 1, 0))
    r = np.searchsorted(cum, flat, side="right")         # the room holding that bed
    over = rank >= home_beds                            # more people than beds: the home's largest room
    if over.any():
        for k in np.flatnonzero(over):
            rr = np.arange(U.room0[u[k]], U.room0[u[k]] + U.n_rooms[u[k]])
            r[k] = rr[np.argmax(U.room_cap[rr])] if len(rr) else NO_ROOM
    ok = U.n_rooms[u] > 0
    room[ids[ok]] = r[ok]
    # couples share one room, even in a home of private rooms (the other bedroom stays free)
    cp = live[coupled]
    first = cp < pid[coupled]
    a_, b_ = cp[first], pid[coupled][first]
    room[b_] = room[a_]


def sync(sim) -> np.ndarray:
    """Give a room to everyone at home without one (moved, arrived, back from a trip) and free the beds of people who
    left. Returns the ids that got a new room."""
    w = sim.w
    P, U = w.P, w.units
    room = ensure(P)
    if U.room0 is None:
        return np.empty(0, np.int64)
    n = P.n
    unit = P["unit_id"][:n]
    present = P["present"][:n].astype(bool)
    r = room[:n]
    stale = (r >= 0) & ((unit < 0) | (U.room_unit[np.maximum(r, 0)] != unit))
    r[stale] = NO_ROOM
    need = np.flatnonzero((unit >= 0) & (r < 0) & (U.n_rooms[np.maximum(unit, 0)] > 0))
    if not len(need):
        return need
    occ = _occupancy(r, present, len(U.room_cap))
    E = w.E
    partner = P["partner_id"][:n] if "partner_id" in P else np.full(n, -1)
    for i in need:
        u = int(unit[i])
        rr = np.arange(U.room0[u], U.room0[u] + U.n_rooms[u])
        free = U.room_cap[rr].astype(np.int32) - occ[rr]
        pick = -1
        j = int(partner[i])
        if 0 <= j < n and unit[j] == u and r[j] >= 0:
            pick = int(r[j])                             # with their spouse, even if that crowds the room
        if pick < 0 and (free > 0).any():
            mates = np.flatnonzero(np.isin(r, rr[free > 0]) & present)
            mates = mates[mates != i]
            if len(mates) and E.n:
                idx = E.find(E.make_keys(np.full(len(mates), i), mates))
                close = mates[(idx >= 0) & (E["stage"][np.maximum(idx, 0)] >= 3)]
                if len(close):
                    pick = int(r[close[0]])
        if pick < 0:
            pick = int(rr[np.argmax(free)]) if (free > 0).any() else int(rr[np.argmax(U.room_cap[rr])])
        r[i] = pick
        occ[pick] += 1
    return need


def room_mates(w, i: int) -> np.ndarray:
    """The other people present who sleep in person i's room."""
    P = w.P
    room = ensure(P)
    r = int(room[i])
    if r < 0:
        return np.empty(0, np.int64)
    m = np.flatnonzero((room[: P.n] == r) & P["present"][: P.n].astype(bool))
    return m[m != i]


def same_room(w, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Whether each pair (a[k], b[k]) shares a bedroom."""
    room = ensure(w.P)
    ra, rb = room[a], room[b]
    return (ra >= 0) & (ra == rb)
