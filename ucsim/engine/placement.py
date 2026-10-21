"""Where exactly each person is, for the map: in their bed or living room on the right floor of their real building, in
a seat at the table, party or stadium they are at, in a real campus building for class. Display only: nothing in the
simulation reads these positions, and nothing here draws random numbers (layouts follow from ids and places).

Positions are metres east (x) and north (y) of ORIGIN, and metres above the ground (z). `Layout` builds the geometry
of a world's homes once (apartments laid out along each building's long side, two rows when it is wide enough for a
corridor; bedrooms along each apartment; beds side by side) and is reused until the world's homes change.

    f = frame(sim)                             # a snapshot of where everyone is (activity keeps one per block)
    pos = place(sim, f)                        # → dict of x, y, z (float32 m), building (int32), floor (int8)
"""
from __future__ import annotations

import numpy as np

from .state import CTX_ID

ORIGIN = (-111.70, 40.26)
KX, KY = 111_320 * np.cos(np.radians(40.26)), 111_320.0
STOREY = 3.2
EYE = 0.9                    # a person's dot sits this far above the floor
NONE = 255


def to_xy(lon, lat):
    return (np.asarray(lon, np.float64) - ORIGIN[0]) * KX, (np.asarray(lat, np.float64) - ORIGIN[1]) * KY


def to_lonlat(x, y):
    return ORIGIN[0] + np.asarray(x, np.float64) / KX, ORIGIN[1] + np.asarray(y, np.float64) / KY


# ---------------------------------------------------------------------- buildings (shared by every world)
_BLD = None


def buildings():
    """The building layer as arrays (box centre in metres, long-axis angle, half extents, floors), loaded once."""
    global _BLD
    if _BLD is None:
        from ..geo.buildings import OUT
        import polars as pl
        if not OUT.exists():
            _BLD = {"n": 0}
            return _BLD
        b = pl.read_parquet(OUT, columns=["box_lon", "box_lat", "angle", "half_len_m", "half_wid_m", "floors", "kind", "name", "area_m2"])
        cx, cy = to_xy(b["box_lon"].to_numpy(), b["box_lat"].to_numpy())
        # rooms sit inside the walls: 86% of the outline's box
        half = np.c_[np.maximum(1.5, b["half_len_m"].to_numpy() * 0.86), np.maximum(1.5, b["half_wid_m"].to_numpy() * 0.86)]
        _BLD = {"n": b.height, "x": cx, "y": cy, "ang": b["angle"].to_numpy(), "half": half,
                "floors": b["floors"].to_numpy().astype(np.int16), "kind": b["kind"].to_numpy(),
                "name": b["name"].to_list(), "area": b["area_m2"].to_numpy()}
    return _BLD


def _frame(bi: np.ndarray):
    B = buildings()
    a = B["ang"][bi]
    return B["x"][bi], B["y"][bi], np.cos(a), np.sin(a), B["half"][bi, 0], B["half"][bi, 1]


# ---------------------------------------------------------------------- homes
class Layout:
    """Apartment cells and their rooms for every unit of one world."""

    def __init__(self, w):
        U = w.units
        self.n_units = len(U.lon)
        m = self.n_units
        B = buildings()
        bi = U.building_id if U.building_id is not None else np.full(m, -1, np.int32)
        bi = np.where((bi >= 0) & (bi < B["n"]), bi, -1)
        fl = U.floor.astype(np.int16) if U.floor is not None else np.zeros(m, np.int16)
        self.cx, self.cy = to_xy(U.lon, U.lat)
        self.ux, self.uy = np.ones(m), np.zeros(m)          # the cell's long direction
        self.hl, self.hw = np.full(m, 4.0), np.full(m, 3.0)  # half length, half width (m)
        self.z0 = np.zeros(m)
        self.bi, self.fl = bi.astype(np.int32), fl.astype(np.int8)
        has = bi >= 0
        if has.any():
            ids = np.flatnonzero(has)
            order = np.lexsort((ids, fl[ids], bi[ids]))
            ids = ids[order]
            key = bi[ids].astype(np.int64) * 64 + fl[ids]
            start = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
            cnt = np.diff(np.r_[start, len(ids)])
            rank = np.arange(len(ids)) - np.repeat(start, cnt)
            n_on = np.repeat(cnt, cnt)
            bx, by, ca, sa, L, W = _frame(bi[ids])
            rows = np.where((n_on > 2) & (W > 7.0), 2, 1)
            per_row = np.ceil(n_on / rows).astype(int)
            row = rank // per_row
            col = rank % per_row
            corridor = np.where(rows == 2, 1.0, 0.0)
            cell_l = 2 * L / per_row
            cell_w = (2 * W - corridor * 2) / rows
            u = -L + (col + 0.5) * cell_l
            v = np.where(rows == 2, np.where(row == 0, -(corridor + cell_w / 2), corridor + cell_w / 2), 0.0)
            self.cx[ids] = bx + u * ca - v * sa
            self.cy[ids] = by + u * sa + v * ca
            self.ux[ids], self.uy[ids] = ca, sa
            self.hl[ids], self.hw[ids] = np.maximum(cell_l / 2 * 0.92, 1.0), np.maximum(cell_w / 2 * 0.92, 1.0)
            self.z0[ids] = fl[ids] * STOREY
        # homes with no footprint (a few address points): several at one point are spread 9 m apart on a grid
        nob = np.flatnonzero(~has)
        if len(nob):
            key = np.round(self.cx[nob], 1) * 1e7 + np.round(self.cy[nob], 1)
            order = np.lexsort((nob, key))
            k_s = key[order]
            start = np.r_[0, np.flatnonzero(np.diff(k_s)) + 1]
            cnt = np.diff(np.r_[start, len(k_s)])
            rank = np.arange(len(k_s)) - np.repeat(start, cnt)
            side = np.ceil(np.sqrt(np.repeat(cnt, cnt)))
            uu = nob[order]
            self.cx[uu] += (rank % side - (side - 1) / 2) * 9.0
            self.cy[uu] += (rank // side - (side - 1) / 2) * 9.0
        # a home alone in a house with upper floors: bedrooms upstairs, living room on the ground floor
        self.upstairs = np.zeros(m, np.int16)
        if has.any():
            n_in = np.bincount(bi[has], minlength=B["n"])
            alone = has & (n_in[np.maximum(bi, 0)] == 1)
            self.upstairs[alone] = np.maximum(B["floors"][bi[alone]] - 1, 0)
        self.room0, self.n_rooms, self.room_cap = U.room0, U.n_rooms.astype(np.int32), U.room_cap

    def living(self, u: np.ndarray):
        """Centre of each unit's living area (the first slice of the apartment), and its height."""
        nr = self.n_rooms[u]
        slices = nr + 1
        t = -self.hl[u] + (2 * self.hl[u] / slices) * 0.5
        return self.cx[u] + t * self.ux[u], self.cy[u] + t * self.uy[u], self.z0[u] + EYE

    def bed(self, u: np.ndarray, room: np.ndarray, slot: np.ndarray):
        """Position of bed `slot` (0…) in global room `room` of unit u."""
        k = (room - self.room0[u]).astype(np.int64)
        nr = np.maximum(self.n_rooms[u], 1)
        slices = nr + 1
        step = 2 * self.hl[u] / slices
        t = -self.hl[u] + step * (k + 1.5)
        cap = np.maximum(self.room_cap[room].astype(np.int64), np.maximum(slot + 1, 1))
        side = ((slot + 0.5) / cap - 0.5) * self.hw[u] * 1.2
        x = self.cx[u] + t * self.ux[u] - side * self.uy[u]
        y = self.cy[u] + t * self.uy[u] + side * self.ux[u]
        z = self.z0[u] + self.upstairs[u] * STOREY + EYE
        return x, y, z


    def outlines(self, u: int) -> dict:
        """The drawn shape of unit u: its apartment rectangle and each slice (living area, then bedrooms) as
        rectangles of four (x, y) corners in metres, and the floor heights they sit at."""
        nr = max(int(self.n_rooms[u]), 1)
        slices = nr + 1
        step = 2 * self.hl[u] / slices

        def rect(t0, t1, z):
            cs = []
            for t, s_ in ((t0, -1), (t1, -1), (t1, 1), (t0, 1)):
                side = s_ * self.hw[u]
                cs.append([float(self.cx[u] + t * self.ux[u] - side * self.uy[u]), float(self.cy[u] + t * self.uy[u] + side * self.ux[u])])
            return {"corners": cs, "z": float(z)}
        z_home = float(self.z0[u])
        z_bed = float(self.z0[u] + self.upstairs[u] * STOREY)
        out = {"unit": rect(-self.hl[u], self.hl[u], z_home), "living": rect(-self.hl[u], -self.hl[u] + step, z_home),
               "rooms": [rect(-self.hl[u] + step * (k + 1), -self.hl[u] + step * (k + 2), z_bed) for k in range(nr)]}
        return out


_LAYOUT: dict = {}


def layout(w) -> Layout:
    key = id(w.units)
    L = _LAYOUT.get(key)
    if L is None or L.n_units != len(w.units.lon):
        if len(_LAYOUT) > 6:
            _LAYOUT.clear()
        L = _LAYOUT[key] = Layout(w)
    return L


# ---------------------------------------------------------------------- seats
def seat_offsets(rank: np.ndarray, size: np.ndarray, spacing: float = 0.8):
    """Offsets (m) for the rank-th of `size` people sharing a spot: a pair side by side, a small group in a circle,
    a crowd in a sunflower spiral."""
    rank = rank.astype(np.float64)
    size = size.astype(np.float64)
    ox = np.zeros(len(rank))
    oy = np.zeros(len(rank))
    pair = size == 2
    ox[pair] = (rank[pair] - 0.5) * spacing * 1.1
    ring = (size > 2) & (size <= 12)
    r = spacing * size[ring] / (2 * np.pi) + 0.4
    a = 2 * np.pi * rank[ring] / size[ring]
    ox[ring], oy[ring] = r * np.cos(a), r * np.sin(a)
    big = size > 12
    rr = spacing * 0.62 * np.sqrt(rank[big] + 0.5)
    aa = rank[big] * 2.39996323
    ox[big], oy[big] = rr * np.cos(aa), rr * np.sin(aa)
    return ox, oy


def table_offsets(px: np.ndarray, py: np.ndarray, gkey: np.ndarray, size: np.ndarray):
    """Where each group's table is when several groups share one place point: the groups (in key order) on a
    sunflower around the point, spaced by the size of the biggest group there. One group: the point itself."""
    k = len(px)
    tx, ty = np.zeros(k), np.zeros(k)
    if not k:
        return tx, ty
    pk = np.round(px, 1) * 1e7 + np.round(py, 1)
    order = np.lexsort((gkey, pk))
    p_s, g_s = pk[order], gkey[order]
    new_pt = np.r_[True, p_s[1:] != p_s[:-1]]
    new_g = new_pt | np.r_[True, g_s[1:] != g_s[:-1]]
    gnum = np.cumsum(new_g) - 1                        # running group number
    first_g = np.maximum.accumulate(np.where(new_pt, gnum, 0))
    t = gnum - first_g                                 # the group's table number at its point
    pt_id = np.cumsum(new_pt) - 1
    n_tab = np.bincount(pt_id, weights=new_g.astype(float))[pt_id]
    big = np.zeros(pt_id.max() + 1)
    np.maximum.at(big, pt_id, size[order].astype(float))
    radius = 0.8 * big[pt_id] / (2 * np.pi) + 1.2    # a table's reach
    multi = n_tab > 1
    r = np.where(multi, 2.1 * radius * np.sqrt(t + 0.5), 0.0)
    a = t * 2.39996323
    tx[order], ty[order] = r * np.cos(a), r * np.sin(a)
    return tx, ty


def group_rank(ctype: np.ndarray, cid: np.ndarray, ids: np.ndarray):
    """Rank of each person (in id order) within their (ctype, cid) group, and the group's size."""
    if not len(ids):
        return np.empty(0, np.int64), np.empty(0, np.int64)
    key = ctype[ids].astype(np.int64) * (1 << 40) + (cid[ids].astype(np.int64) + 1)
    order = np.lexsort((ids, key))
    k = key[order]
    start = np.r_[0, np.flatnonzero(np.diff(k)) + 1]
    cnt = np.diff(np.r_[start, len(k)])
    rank = np.empty(len(ids), np.int64)
    size = np.empty(len(ids), np.int64)
    rank[order] = np.arange(len(k)) - np.repeat(start, cnt)
    size[order] = np.repeat(cnt, cnt)
    return rank, size


# ---------------------------------------------------------------------- campus buildings for classes
_CAMPUS: dict = {}


def campus_buildings(school: int) -> np.ndarray:
    """Real teaching buildings of a campus (largest first): campus-kind footprints within reach of its centre."""
    if school not in _CAMPUS:
        from .systems.activity import BYU, UVU
        B = buildings()
        if not B["n"]:
            _CAMPUS[school] = np.empty(0, np.int64)
            return _CAMPUS[school]
        c = BYU if school == 1 else UVU
        x0, y0 = to_xy(*c)
        d = np.hypot(B["x"] - x0, B["y"] - y0)
        reach = 900 if school == 1 else 700
        ok = (d < reach) & np.isin(B["kind"], ["campus", "school", "civic"]) & (B["area"] > 900)
        ids = np.flatnonzero(ok)
        _CAMPUS[school] = ids[np.argsort(-B["area"][ids])][:60]
    return _CAMPUS[school]


# ---------------------------------------------------------------------- everyone
def frame(sim, ctype=None, cid=None, act=None) -> dict:
    """What placement needs, copied and compact (23 bytes a person): contexts (activity's, or the ones given), the place
    points, homes and rooms, who is here."""
    P = sim.w.P
    a = sim.systems["activity"]
    n = P.n
    ct = (a.ctype if ctype is None else ctype)[:n]
    ci = (a.cid if cid is None else cid)[:n]
    room = P.internal["room"][:n] if "room" in P.internal else np.full(n, -1, np.int32)
    return {"day": int(sim.w.day), "hour": int(sim.w.hour), "ctype": np.array(ct, np.uint8),
            "cid": np.clip(ci, -1, 2**31 - 1).astype(np.int32),
            "act": np.array(P["activity_now"][:n] if act is None else act[:n], np.uint8),
            "lon": np.array(P["loc_lon"][:n], np.float32), "lat": np.array(P["loc_lat"][:n], np.float32),
            "unit": np.array(P["unit_id"][:n], np.int32), "room": np.array(room, np.int32),
            "present": np.array(P["present"][:n], bool)}


def place(sim, f: dict) -> dict:
    """Precise positions for everyone in frame f (see `frame`)."""
    w = sim.w
    U = w.units
    ctype, cid = f["ctype"], f["cid"]
    n = len(ctype)
    x = np.full(n, np.nan)
    y = np.full(n, np.nan)
    z = np.zeros(n)
    bld = np.full(n, -1, np.int32)
    flo = np.zeros(n, np.int8)
    L = layout(w) if U.room0 is not None else None
    present, unit, room = f["present"], f["unit"], f["room"]

    # at home: in their own room (a bed each) — or, as a visitor or at a party, around the living room
    home = (ctype == CTX_ID["unit"]) & present & (cid >= 0)
    own = home & (cid == unit) & (room >= 0)
    if L is not None and own.any():
        ii = np.flatnonzero(own)
        # bed slot: rank among the room's occupants present (id order)
        rank, _ = group_rank(np.zeros(n, np.uint8), room, ii)
        bx, by, bz = L.bed(unit[ii], room[ii], rank)
        x[ii], y[ii], z[ii] = bx, by, bz
        bld[ii], flo[ii] = L.bi[unit[ii]], L.fl[unit[ii]] + L.upstairs[unit[ii]]
    visit = home & ~own
    occ_home = np.zeros(n, bool)
    occ_unit = np.full(n, -1, np.int64)
    m_occ = (ctype == CTX_ID["date"]) | (ctype == CTX_ID["occasion"])
    if m_occ.any():
        O = sim.book.occ
        pos = O.pos(cid[m_occ])
        ok = pos >= 0
        posc = np.maximum(pos, 0)
        kinds = O.cols["kind"][posc]
        where = sim.systems["occasions"].k_where[np.maximum(kinds, 0)] if len(kinds) else np.empty(0, object)
        pl_ = O.cols["place"][posc]
        is_home = ok & (where == "home") & (pl_ >= 0) & (pl_ < len(U.lon))
        jj = np.flatnonzero(m_occ)
        occ_home[jj[is_home]] = True
        occ_unit[jj[is_home]] = pl_[is_home]
    gather = visit | occ_home
    if L is not None and gather.any():
        ii = np.flatnonzero(gather)
        uu = np.where(occ_home[ii], occ_unit[ii], cid[ii]).astype(np.int64)
        uu = np.clip(uu, 0, len(U.lon) - 1)
        lx, ly, lz = L.living(uu)
        rank, size = group_rank(np.full(n, 1, np.uint8), np.where(occ_home, occ_unit, cid).astype(np.int64), ii)
        ox, oy = seat_offsets(rank, size, 0.7)
        x[ii], y[ii], z[ii] = lx + ox, ly + oy, lz
        bld[ii], flo[ii] = L.bi[uu], L.fl[uu]

    # everywhere else: the place's point from the simulation, people sharing it seated around it
    rest = present & np.isnan(x) & (ctype != NONE)
    if rest.any():
        ii = np.flatnonzero(rest)
        px, py = to_xy(f["lon"][ii], f["lat"][ii])
        # classes: a real teaching building of that campus, and a floor
        cls = ctype[ii] == CTX_ID["class"]
        if cls.any():
            ac = sim.systems["academics"]
            sec = cid[ii][cls]
            sch = ac.sec_school[sec]
            B = buildings()
            for s in (1, 2):
                cb = campus_buildings(s)
                mm = sch == s
                if not len(cb) or not mm.any():
                    continue
                b = cb[(ac.sec_bldg[sec[mm]].astype(np.int64) * 7 + sec[mm]) % len(cb)]
                k = np.flatnonzero(cls)[mm]
                px[k], py[k] = B["x"][b], B["y"][b]
                f = (sec[mm] % np.maximum(B["floors"][b], 1)).astype(np.int8)
                z[ii[k]] = f * STOREY + EYE
                bld[ii[k]], flo[ii[k]] = b, f
        # hanging out on campus: spread over the campus's buildings (library, student centre…) by person
        camp = ctype[ii] == CTX_ID["campus"]
        if camp.any():
            B = buildings()
            for s in (1, 2):
                cb = campus_buildings(s)[:12]
                mm = camp & (cid[ii] == s)
                if len(cb) and mm.any():
                    b = cb[(ii[mm] * 7919) % len(cb)]
                    px[mm], py[mm] = B["x"][b], B["y"][b]
                    bld[ii[mm]] = b
        gkey = np.where(cls | camp, bld[ii].astype(np.int64) * 1000 + (cid[ii] % 997), cid[ii])
        g = np.full(n, -1, np.int64)
        g[ii] = gkey
        rank, size = group_rank(ctype, g, ii)
        spacing = np.where(size > 200, 0.55, 0.8)
        ox, oy = seat_offsets(rank, size, 0.8)
        ox, oy = ox * spacing / 0.8, oy * spacing / 0.8
        # several groups at one spot (two couples at a restaurant, two wards in a meetinghouse): each its own table
        tx, ty = table_offsets(px, py, ctype[ii].astype(np.int64) * (1 << 40) + gkey + 1, size)
        x[ii], y[ii] = px + tx + ox, py + ty + oy
        z[ii] = np.where(z[ii] > 0, z[ii], EYE)
    return {"x": x.astype(np.float32), "y": y.astype(np.float32), "z": z.astype(np.float32), "building": bld, "floor": flo}
