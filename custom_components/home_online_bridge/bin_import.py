"""Parse a Domati controller .bin export into a list of slaves (no HA imports).

Port of domati_bin2csv.py (v2). The file stores a module list in which every module
carries its own start slave number; those are the anchors. Slave records are then read
in file order and numbered from the lowest module start, skipping the number range of
remote/IR modules (their buttons are not stored). Because every normal module starts on
a stored number, a counting error cannot run on into the next module.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

REMOTE_KIND = "remote"
BLOCK_KIND = "dimmer/cover-blok"
IR_KIND = "IR-ontvanger"
ITEM_KIND = "item"

# Type byte of a dimmer/cover block. Verified against the mappings of an existing install:
# 0x0b = curtain/cover, 0x13 = dimmer; 0x11 only occurs on blocks named "Dimmer N"/"Fakkel ...".
_BLOCK_TYPE = {0x0B: "cover", 0x11: "dimmer", 0x13: "dimmer"}

# Direction byte of an item record (15 bytes after the record start). Checked against the mappings of an
# existing install: 2 on 9/9 real sensors (inputs), 3 or 35 on 34/38 relays (outputs). 0/1 (buttons, leds)
# and other values are not trusted, so no direction is shown for those.
_DIRECTION = {2: "input", 3: "output", 35: "output"}

_SENSORISH = re.compile(r"sens|therm|status|state", re.I)
_INPUTISH = re.compile(r"^\s*(shift\s*)?(button|input)\b", re.I)


class BinParseError(ValueError):
    """Raised when the file is not a recognisable Domati .bin; the message is a translation key."""


@dataclass(frozen=True)
class BinSlave:
    id: int
    kind: str  # item | IR-ontvanger | dimmer/cover-blok
    name: str
    suggested_type: str  # relay | sensor | dimmer | cover
    module: str = ""  # name of the controller module this slave sits on
    direction: str = ""  # "input" / "output" when the file says so, else ""

    @property
    def is_input(self) -> bool:
        """Physical inputs/buttons: rarely worth a mapping, hidden by default in the UI."""
        return self.kind == ITEM_KIND and bool(_INPUTISH.match(self.name))


@dataclass
class BinImport:
    slaves: list[BinSlave]
    warnings: list[str] = field(default_factory=list)


# --- module list ----------------------------------------------------------------
def _read_modules(d: bytes) -> list[tuple[int, str, str, int]]:
    mods = []
    for m in re.finditer(rb"\x01(..)\x0e\x01\x0a.{4,12}?\xff\xff\x00.([\x20-\x7e]+)\x00", d, re.S):
        mods.append((m.start(), int.from_bytes(m.group(1), "big"), "module", m.group(2).decode("latin1").strip()))
    for m in re.finditer(rb"\x02(..)\x09.{4}\x11([\x20-\x7e]+)\x00", d, re.S):
        mods.append((m.start(), int.from_bytes(m.group(1), "big"), REMOTE_KIND, m.group(2).decode("latin1").strip()))
    mods.sort()
    out, last = [], -1
    for offset, start, kind, name in mods:  # only the module list itself: ascending start numbers
        if start > last:
            out.append((start, kind, name, offset))
            last = start
    return out


# --- slave records ----------------------------------------------------------------
def _read_records(d: bytes, gap: int = 5000) -> list[tuple[int, str, str, str | None, str]]:
    """Return (offset, kind, name, type_hint, direction) in file order."""
    # lookahead: a 0x01 flag byte right before a name must not swallow a real header
    cand = [
        (m.start(), m.start() + 3, int.from_bytes(m.group(1), "big"))
        for m in re.finditer(rb"(?=\x01(..))", d, re.S)
    ]
    seq: list[tuple[int, int, int]] = []
    for s0, first in enumerate(cand):  # longest chain 0,1,2,... (ids ascending)
        if first[2] != 0:
            continue
        cur: list[tuple[int, int, int]] = []
        want = 0
        for o, e, i in cand[s0:]:
            if i == want and (not cur or o - cur[-1][0] < gap):
                cur.append((o, e, i))
                want += 1
        if len(cur) > len(seq):
            seq = cur
    if not seq:
        raise BinParseError("bin_no_records")
    last = seq[-1][0]
    ev: list[tuple[int, str, str, str | None, str]] = []
    for n, (o, e, _i) in enumerate(seq):
        nxt = seq[n + 1][0] if n + 1 < len(seq) else o + 400
        seg = d[e:nxt][3:]  # past id + kind byte
        m = re.search(rb"\xff[^\xff]([\x20-\x7e]{2,})\x00", seg, re.S)
        if m:
            name = m.group(1).decode("latin1").strip()
        else:  # without 'ff' flag: first readable text
            m = re.search(rb"([\x20-\x7e]{3,})\x00", seg)
            name = m.group(1).decode("latin1").lstrip("@!").strip() if m else ""
        direction = _DIRECTION.get(d[o + 15], "") if o + 15 < len(d) else ""
        ev.append((o, ITEM_KIND, name, None, direction))
    for m in re.finditer(rb"\x16 \x04\x00\xff\xff\xff\x05\x86([\x20-\x7e]+)\x00", d):
        if m.start() < last:
            ev.append((m.start(), IR_KIND, m.group(1).decode("latin1"), None, ""))
    block = re.compile(
        rb"\x02\x00(.)\x00([\x0b\x11\x13])(.{0,22}?)\x18\x00\x03.{1,6}?\xff?\x64(...)([\x20-\x7e]+)\x00", re.S
    )
    for m in block.finditer(d):
        if m.start() < last:
            ev.append((m.start(), BLOCK_KIND, m.group(5).decode("latin1").strip(), _BLOCK_TYPE[m.group(2)[0]], ""))
    ev.sort(key=lambda e: e[0])
    return ev


def _number(mods, ev):
    all_starts = sorted(s for s, _k, _n, _o in mods)
    remote = {s: n for s, k, n, _o in mods if k == REMOTE_KIND}
    normal = sorted(s for s, k, _n, _o in mods if k == "module")
    rows: list[tuple[int, str, str, str | None, str]] = []  # remote modules appear with kind REMOTE_KIND
    warns: list[str] = []
    covered: set[int] = set()
    cur = all_starts[0]

    def skip_remotes(cur: int) -> int | None:
        """Remote/IR modules have no records: jump to the next normal module."""
        while cur in remote:
            nxt = [s for s in normal if s > cur]
            rows.append((cur, REMOTE_KIND, remote[cur], None, ""))
            end = nxt[0] if nxt else None
            covered.update(s for s in remote if cur <= s and (end is None or s < end))
            if end is None:
                return None
            cur = end
        return cur

    for _o, kind, name, hint, direction in ev:
        if cur in remote:
            new = skip_remotes(cur)
            if new is None:
                break
            cur = new
        rows.append((cur, kind, name, hint, direction))
        cur += 1
    if cur in remote:
        skip_remotes(cur)

    top = max(r[0] for r in rows)
    for s, k, n, _o in sorted(mods):
        if s <= top and k == REMOTE_KIND and s not in covered:
            warns.append(f'Count does not land on remote module "{n}" (start {s}).')
    ends = [s for s in all_starts if s > rows[-1][0]]
    if ends and rows[-1][1] != REMOTE_KIND and ends[0] != cur:
        warns.append(f"Count ends at {cur - 1}, but the next module boundary is {ends[0]}.")
    return rows, warns


def _suggest(kind: str, name: str, hint: str | None) -> str:
    if hint:
        return hint
    if kind == IR_KIND:
        return "relay"
    if _INPUTISH.match(name) or _SENSORISH.search(name):
        return "sensor"
    return "relay"


def parse_bin(data: bytes) -> BinImport:
    """Parse the file; raises BinParseError for unrecognised files. Pure function, run it in an executor."""
    mods = _read_modules(data)
    if not mods:
        raise BinParseError("bin_no_modules")
    ev = _read_records(data)
    mods = [m for m in mods if m[3] < ev[0][0]]  # only the module list before the slave records
    if not mods:
        raise BinParseError("bin_no_modules")
    srt = sorted(mods)
    # expected record count = sum of sizes of all normal modules with a known next start
    expected = sum(srt[n + 1][0] - s for n, (s, k, _nm, _o) in enumerate(srt[:-1]) if k == "module")
    tail_unknown = srt[-1][1] == "module"  # last module has unknown size
    for gap in (5000, 20000, 100000):  # too few records: widen the chain limit
        ev = _read_records(data, gap)
        if tail_unknown or len(ev) >= expected:
            break
    pre: list[str] = []
    if not tail_unknown and len(ev) > expected:
        ev = ev[:expected]  # drop extra (false) records at the end
    if not tail_unknown and len(ev) < expected:
        pre.append(
            f"Read {len(ev)} records but the module list expects {expected}: possibly an unknown record or module type."
        )
    rows, warns = _number(mods, ev)
    starts = [m[0] for m in srt]
    names = [m[2] for m in srt]

    def module_of(sid: int) -> str:
        i = bisect_right(starts, sid) - 1
        return names[i] if i >= 0 else ""

    slaves = [
        BinSlave(sid, kind, name, _suggest(kind, name, hint), module_of(sid), direction)
        for sid, kind, name, hint, direction in rows
        if kind != REMOTE_KIND
    ]
    return BinImport(slaves=slaves, warnings=pre + warns)
