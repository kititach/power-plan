#!/usr/bin/env python3
"""Generate scale-up tier diagram as SVG — presentation quality.
Layout: row-label column (left) + 3 tier columns.
Output: diagram-scale.svg
"""
import os
from xml.sax.saxutils import escape

W, H = 1640, 940
FONT = "DejaVu Sans, Arial, sans-serif"

# ── Tier palette ──────────────────────────────────────────────
TIERS = [
    {"label": "ระดับ 1",  "tag": "100 tag/s",    "peak": "Peak 300 tag/s",
     "budget": "0 บาท · 1 วัน",
     "hfill": "#455a64", "htext": "#ffffff", "colbg": "#eceff1", "border": "#607d8b"},
    {"label": "ระดับ 2",  "tag": "1,000 tag/s",  "peak": "Peak 3,000 tag/s",
     "budget": "~15k–30k บาท · 1–2 สัปดาห์",
     "hfill": "#2e7d32", "htext": "#ffffff", "colbg": "#f1f8e9", "border": "#43a047"},
    {"label": "ระดับ 3",  "tag": "10,000 tag/s", "peak": "Peak 30,000 tag/s",
     "budget": "~130k–260k บาท · 3–5 เดือน",
     "hfill": "#1565c0", "htext": "#ffffff", "colbg": "#e3f2fd", "border": "#1e88e5"},
]

# ── Cell status palette ───────────────────────────────────────
S = {
    "same":  {"fill": "#fafafa", "stroke": "#bdbdbd", "lbl": "#888"},
    "tune":  {"fill": "#fffde7", "stroke": "#f9a825", "lbl": "#e65100"},
    "new":   {"fill": "#f1f8e9", "stroke": "#43a047", "lbl": "#1b5e20"},
    "warn":  {"fill": "#fff3e0", "stroke": "#ef6c00", "lbl": "#bf360c"},
}

# ── Row data ──────────────────────────────────────────────────
# (row_label, section, [(value, status_key), ...])
ROWS = [
    # Section: Transport
    ("OPC Transport", "transport",
     [("Polling", "same"), ("Polling 1s", "same"), ("Subscription (push)", "new")]),
    ("Data rate · Normal", "transport",
     [("2.2 KB/s", "same"), ("22 KB/s", "tune"), ("220 KB/s", "new")]),
    ("Data rate · Peak (3×)", "transport",
     [("6.6 KB/s", "same"), ("66 KB/s", "tune"), ("660 KB/s", "new")]),

    # Section: Pipeline
    ("NiFi Edge JVM", "pipeline",
     [("2 GB", "same"), ("4 GB", "tune"), ("8 GB", "new")]),
    ("Kafka  Brokers / Partitions", "pipeline",
     [("1 / 3", "same"), ("1 / 6", "tune"), ("3 / 12", "new")]),
    ("Telegraf replicas", "pipeline",
     [("1", "same"), ("2", "tune"), ("3", "new")]),

    # Section: Hot storage
    ("InfluxDB  RAM / Disk (90 วัน)", "hot",
     [("2 GB / 17 GB", "same"), ("4 GB / 170 GB", "tune"), ("8 GB / 340 GB", "new")]),

    # Section: Cold storage
    ("MinIO / ปี  (format)", "cold",
     [("68 GB  (JSON)", "same"), ("680 GB  (JSON)", "tune"), ("850 GB  (Parquet)", "new")]),
    ("MinIO  5 ปี", "cold",
     [("~340 GB", "same"), ("~3.4 TB", "tune"), ("~4.25 TB  ✓", "new")]),
    ("MinIO  storage", "cold",
     [("NVMe  100 GB", "same"), ("NVMe  1 TB", "tune"), ("NAS/HDD  6 TB+", "new")]),

    # Section: Infra
    ("k3s  topology / Server RAM", "infra",
     [("Single-node / 16 GB", "same"), ("Single-node / 32 GB", "tune"), ("3 nodes HA / 64 GB", "new")]),
]

SECTION_LABELS = {
    "transport": "Transport",
    "pipeline":  "Message Pipeline",
    "hot":       "Hot Storage",
    "cold":      "Cold Storage  (MinIO)",
    "infra":     "Infrastructure",
}

# ── SVG builder ───────────────────────────────────────────────
class SVG:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def raw(self, s): self.parts.append(s)

    def rect(self, x, y, w, h, rx=6, fill="white", stroke="#ccc", sw=1, opacity=1):
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op}/>')

    def text(self, x, y, t, size=13, bold=False, fill="#222", anchor="middle",
             italic=False, opacity=1):
        w = "bold" if bold else "normal"
        st = "italic" if italic else "normal"
        op = f' opacity="{opacity}"' if opacity < 1 else ""
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{w}" font-style="{st}" fill="{fill}" '
            f'text-anchor="{anchor}" dominant-baseline="central"{op}>'
            f'{escape(str(t))}</text>')

    def line(self, x1, y1, x2, y2, stroke="#ddd", sw=1, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def save(self, path):
        defs = """<defs>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="116%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#00000022"/>
    </filter>
    <filter id="shadow-sm" x="-2%" y="-2%" width="104%" height="110%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#00000018"/>
    </filter>
  </defs>"""
        body = "\n  ".join(self.parts)
        svg = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'  <rect width="100%" height="100%" fill="#f8f9fa"/>\n'
            f'  {defs}\n'
            f'  {body}\n'
            f'</svg>\n')
        with open(path, "w") as f:
            f.write(svg)


# ── Layout ────────────────────────────────────────────────────
def render(out_path):
    s = SVG(W, H)
    PAD       = 28
    LABEL_W   = 210
    GAP       = 10
    tier_w    = (W - PAD*2 - LABEL_W - GAP*4) // 3

    TITLE_H   = 72
    HEADER_H  = 78
    ROW_H     = 62
    ROW_GAP   = 5
    SEC_GAP   = 14   # extra gap before section start
    LEGEND_H  = 40

    # group rows by section for divider placement
    sections = []
    cur_sec = None
    for row in ROWS:
        sec = row[1]
        if sec != cur_sec:
            sections.append(sec)
            cur_sec = sec

    # calculate Y positions for each row (with section gap before first row of each section)
    row_ys = []
    y = TITLE_H + HEADER_H + 6
    cur_sec = None
    for row in ROWS:
        sec = row[1]
        if sec != cur_sec and cur_sec is not None:
            y += SEC_GAP
        cur_sec = sec
        row_ys.append(y)
        y += ROW_H + ROW_GAP

    total_h = y + LEGEND_H + PAD
    # (H is fixed at 940 — rows should fit)

    col_xs = [
        PAD + LABEL_W + GAP,
        PAD + LABEL_W + GAP + tier_w + GAP,
        PAD + LABEL_W + GAP + (tier_w + GAP)*2,
    ]
    table_right = col_xs[2] + tier_w

    # ── Title ──────────────────────────────────────────────────
    s.rect(0, 0, W, TITLE_H, rx=0, fill="#263238", stroke="none")
    s.text(W//2, 26, "Scale-Up Plan — Industrial IoT Data Platform",
           size=21, bold=True, fill="#eceff1")
    s.text(W//2, 52, "100 tag/s  →  1,000 tag/s  →  10,000 tag/s   |   Normal load + Peak 3× burst",
           size=13, fill="#90a4ae")

    # ── Tier column backgrounds ────────────────────────────────
    table_top = TITLE_H
    table_bot = row_ys[-1] + ROW_H + 6
    for ti, tier in enumerate(TIERS):
        cx = col_xs[ti]
        s.rect(cx, table_top + HEADER_H, tier_w, table_bot - (table_top + HEADER_H),
               rx=0, fill=tier["colbg"], stroke="none")

    # ── Tier headers ───────────────────────────────────────────
    for ti, tier in enumerate(TIERS):
        cx = col_xs[ti]
        hy = TITLE_H
        rx = 10 if ti == 0 else (10 if ti == 2 else 0)
        # header card with shadow
        s.raw(f'<rect x="{cx}" y="{hy}" width="{tier_w}" height="{HEADER_H}" '
              f'rx="0" ry="0" fill="{tier["hfill"]}" filter="url(#shadow)"/>')
        s.text(cx + tier_w//2, hy + 22, tier["label"],
               size=18, bold=True, fill=tier["htext"])
        s.text(cx + tier_w//2, hy + 42, tier["tag"],
               size=15, bold=True, fill="#ffffffcc")
        s.text(cx + tier_w//2, hy + 60, tier["peak"],
               size=11, fill="#ffffff88")

    # ── Row label column header ────────────────────────────────
    s.rect(PAD, TITLE_H, LABEL_W, HEADER_H, rx=0, fill="#37474f", stroke="none")
    s.text(PAD + LABEL_W//2, TITLE_H + HEADER_H//2, "ตัวชี้วัด",
           size=14, bold=True, fill="#eceff1")

    # ── Rows ───────────────────────────────────────────────────
    cur_sec = None
    for ri, (row_label, sec, vals) in enumerate(ROWS):
        ry = row_ys[ri]

        # Section divider label
        if sec != cur_sec:
            cur_sec = sec
            sec_label = SECTION_LABELS.get(sec, sec)
            # light bar across full width
            s.rect(PAD, ry - SEC_GAP + 2 if ri > 0 else ry - 2,
                   table_right - PAD, SEC_GAP - 2 if ri > 0 else 0,
                   rx=0, fill="#cfd8dc", stroke="none")
            if ri > 0:
                s.text(PAD + 6, ry - SEC_GAP//2 + 2, sec_label,
                       size=10, bold=True, fill="#546e7a", anchor="start")

        # Row background (alternating)
        row_bg = "#ffffff" if ri % 2 == 0 else "#f5f7f8"
        s.rect(PAD, ry, LABEL_W, ROW_H, rx=0, fill=row_bg, stroke="#e0e0e0", sw=0.5)

        # Row label
        s.text(PAD + LABEL_W - 10, ry + ROW_H//2, row_label,
               size=12, fill="#37474f", anchor="end")

        # Cells
        for ti, (val, sk) in enumerate(vals):
            cx = col_xs[ti]
            cstyle = S[sk]
            cell_pad = 6
            s.raw(f'<rect x="{cx + cell_pad}" y="{ry + 4}" '
                  f'width="{tier_w - cell_pad*2}" height="{ROW_H - 8}" '
                  f'rx="7" ry="7" fill="{cstyle["fill"]}" '
                  f'stroke="{cstyle["stroke"]}" stroke-width="1.5" '
                  f'filter="url(#shadow-sm)"/>')
            s.text(cx + tier_w//2, ry + ROW_H//2, val,
                   size=13, bold=(sk != "same"), fill=cstyle["lbl"])

        # Horizontal divider
        s.line(PAD, ry + ROW_H, table_right, ry + ROW_H, stroke="#e0e0e0", sw=0.5)

    # ── Budget row ─────────────────────────────────────────────
    by = row_ys[-1] + ROW_H + ROW_GAP + SEC_GAP
    bh = 44
    s.rect(PAD, by, LABEL_W, bh, rx=0, fill="#263238", stroke="none")
    s.text(PAD + LABEL_W//2, by + bh//2, "งบ + เวลา",
           size=12, bold=True, fill="#eceff1")
    for ti, tier in enumerate(TIERS):
        cx = col_xs[ti]
        s.rect(cx, by, tier_w, bh, rx=0, fill=tier["hfill"], stroke="none", opacity=0.85)
        s.text(cx + tier_w//2, by + bh//2, tier["budget"],
               size=12, bold=True, fill="#ffffff")

    # ── Legend ─────────────────────────────────────────────────
    ly = by + bh + 14
    leg_items = [
        ("same", "ไม่เปลี่ยน"),
        ("tune", "ปรับ config / scale up"),
        ("new",  "ใหม่ / อัปเกรด hardware"),
    ]
    lx = PAD
    for sk, label in leg_items:
        cstyle = S[sk]
        s.rect(lx, ly, 20, 20, rx=5, fill=cstyle["fill"],
               stroke=cstyle["stroke"], sw=1.5)
        s.text(lx + 26, ly + 10, label, size=12, fill="#546e7a", anchor="start")
        lx += 220

    s.save(out_path)
    print(f"wrote {out_path}  ({W}x{H})")


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    render(os.path.join(out_dir, "diagram-scale.svg"))
