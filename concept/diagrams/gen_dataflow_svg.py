#!/usr/bin/env python3
"""Data flow diagram — data format/shape at each pipeline block.
Output: diagram-dataflow.svg
"""
import os
from xml.sax.saxutils import escape

W, H = 1860, 940
FONT      = "DejaVu Sans, Arial, sans-serif"
FONT_MONO = "DejaVu Sans Mono, Courier New, monospace"

# ── Palette ───────────────────────────────────────────────────
ZONE = {
    "ot":     {"hfill": "#37474f", "htext": "#eceff1", "border": "#546e7a", "bg": "#f5f5f5"},
    "nifi":   {"hfill": "#6a1b9a", "htext": "#f3e5f5", "border": "#8e24aa", "bg": "#fce4ec"},
    "kafka":  {"hfill": "#e65100", "htext": "#fff8e1", "border": "#ef6c00", "bg": "#fff3e0"},
    "influx": {"hfill": "#1565c0", "htext": "#e3f2fd", "border": "#1e88e5", "bg": "#e3f2fd"},
    "grafana":{"hfill": "#e65100", "htext": "#fff8e1", "border": "#ef6c00", "bg": "#fff3e0"},
    "minio":  {"hfill": "#c62828", "htext": "#ffebee", "border": "#e53935", "bg": "#ffebee"},
    "trino":  {"hfill": "#1b5e20", "htext": "#e8f5e9", "border": "#43a047", "bg": "#e8f5e9"},
    "bridge": {"hfill": "#4a148c", "htext": "#ede7f6", "border": "#7b1fa2", "bg": "#ede7f6"},
    "maint":  {"hfill": "#bf360c", "htext": "#fbe9e7", "border": "#e64a19", "bg": "#fbe9e7"},
}

CARD_W = 255
CARD_H = 200
HEADER_H = 30

# ── Card content (lines shown in monospace code box) ──────────
CARDS = {
    "opc": {
        "title": "OPC UA (Prosys)",
        "sub":   "opc.tcp://mintserver:53530",
        "zone":  "ot",
        "lines": [
            "Protocol: OPC UA Binary",
            "NodeId: ns=3;i=2001",
            "─────────────────────",
            "DataValue {",
            "  value:  85.3  (Float)",
            "  status: Good",
            "  ts: 2026-05-13T14:00:00Z",
            "}",
            "× 307 nodes  poll 2s",
        ],
    },
    "nifi_edge": {
        "title": "NiFi Edge",
        "sub":   "Groovy / Eclipse Milo → FlowFile",
        "zone":  "nifi",
        "lines": [
            "FlowFile attributes:",
            "  mime.type = application/json",
            "  tag.count = 307",
            "─────────────────────",
            "Content (~6.8 KB JSON):",
            '{  "timestamp": "…Z",',
            '   "source_id": "mintserver-prosys",',
            '   "tag_count": 307, "bad_count": 0,',
            '   "Temp_Boiler_01": 85.3,',
            '   "Press_Line_01": 120.5, … }',
        ],
    },
    "kafka": {
        "title": "Kafka  opc-raw-data",
        "sub":   "Strimzi KRaft · 3 partitions",
        "zone":  "kafka",
        "lines": [
            "Topic:  opc-raw-data",
            "Partitions:  3  (active: 0,2)",
            "─────────────────────",
            "Message:",
            "  key:    null",
            "  value:  JSON ~6.8 KB",
            "  offset: 12 345 678",
            "  lag:    < 5 msg",
            "─────────────────────",
            "~500 msg/day  (every 2s)",
        ],
    },
    "telegraf": {
        "title": "Telegraf",
        "sub":   "Kafka consumer → Line Protocol",
        "zone":  "influx",
        "lines": [
            "consumer_group: telegraf-opc",
            "data_format:    json",
            "tag_keys: [source_id, device_id]",
            "name_override:  opc_data",
            "─────────────────────",
            "Line Protocol output:",
            "opc_data,source_id=mintserver,",
            "device_id=opc-prosys-300tags",
            "Temp_Boiler_01=85.3,… ",
            "1715608800000000000",
        ],
    },
    "influxdb": {
        "title": "InfluxDB",
        "sub":   "bucket: opc-data  org: mintpower-org",
        "zone":  "influx",
        "lines": [
            "measurement: opc_data",
            "─────────────────────",
            "tags:",
            "  source_id = mintserver-prosys",
            "  device_id = opc-prosys-300tags",
            "  host      = telegraf-mintpower",
            "fields: (float64)",
            "  Temp_Boiler_01: 85.3",
            "  Press_Line_01:  120.5",
            "  … (307 fields)",
        ],
    },
    "grafana": {
        "title": "Grafana",
        "sub":   "dashboard: mintpower-combined-v1",
        "zone":  "grafana",
        "lines": [
            "Flux query:",
            'from(bucket:"opc-data")',
            "  |> range(start: -1h)",
            '  |> filter(fn:(r) =>',
            '    r._measurement=="opc_data")',
            '  |> filter(fn:(r) =>',
            '    r._field=="Temp_Boiler_01")',
            "  |> aggregateWindow(",
            "       every:10s, fn:mean)",
            "→ Timeseries panel",
        ],
    },
    "nifi_core": {
        "title": "NiFi Core",
        "sub":   "ConsumeKafka → MergeRecord → PutS3",
        "zone":  "nifi",
        "lines": [
            "ConsumeKafka  opc-raw-data",
            "  ↓",
            "MergeRecord  (batch N msgs)",
            "  max.bin.age = 60s",
            "  ↓",
            "PutS3Object → MinIO",
            "─────────────────────",
            "Output: JSON array ~500KB",
            "[{…msg1…},{…msg2…},…]",
            "~132 files / day",
        ],
    },
    "minio": {
        "title": "MinIO",
        "sub":   "bucket: opc-raw  (S3-compatible)",
        "zone":  "minio",
        "lines": [
            "Path structure:",
            "opc-raw/data/",
            "  year=2026/month=05/day=13/",
            "    {uuid}.json",
            "─────────────────────",
            "File: JSON array",
            "Size: ~100–500 KB/file",
            "Files: ~132/day",
            "Retention: 5 ปี",
            "Storage: NVMe (current)",
        ],
    },
    "trino": {
        "title": "Trino",
        "sub":   "minio.opc.sensor_data",
        "zone":  "trino",
        "lines": [
            "Hive connector → MinIO",
            "Partition: year/month/day",
            "─────────────────────",
            "SQL query:",
            "SELECT timestamp,",
            "  Temp_Boiler_01,",
            "  Press_Line_01",
            "FROM minio.opc.sensor_data",
            "WHERE year='2026'",
            "  AND day='13'",
        ],
    },
    "bridge": {
        "title": "openmaint-bridge",
        "sub":   "systemd · Kafka → threshold check",
        "zone":  "bridge",
        "lines": [
            "Reads: opc-raw-data (same JSON)",
            "Checks 19 threshold rules:",
            "  Temp_Boiler_* > 95°C → CRIT",
            "  Press_Line_* > 8 bar → HIGH",
            "  Vibration_Pump_* > 10 → HIGH",
            "  … (19 rules total)",
            "─────────────────────",
            "Cooldown: 5 min / tag",
            "On violation →",
            "  POST Alarm + CorrectiveMaint",
        ],
    },
    "openmaint": {
        "title": "OpenMAINT",
        "sub":   "CMDBuild 3.4.1-d  CMMS",
        "zone":  "maint",
        "lines": [
            "Alarm record:",
            "  Tag:   Temp_Boiler_01",
            "  Value: 96.2 °C (> 95.0)",
            "  Sev:   Critical",
            "  Time:  2026-05-13T14:00Z",
            "─────────────────────",
            "CorrectiveMaint (work order):",
            "  Asset:  Boiler_01",
            "  Status: Assignment",
            "  Code:   CM-2026051301",
            "  → assigned to technician",
        ],
    },
}

# ── Positions: (card_key, x, y) ───────────────────────────────
LAYOUT = [
    # Entry pipeline (top row)
    ("opc",       30,  60),
    ("nifi_edge", 320, 60),
    ("kafka",     610, 60),
    # Path 1: Real-time monitoring
    ("telegraf",  900, 60),
    ("influxdb",  1190, 60),
    ("grafana",   1480, 60),
    # Path 2: Data lake
    ("nifi_core", 900, 340),
    ("minio",     1190, 340),
    ("trino",     1480, 340),
    # Path 3: Asset management
    ("bridge",    900, 620),
    ("openmaint", 1190, 620),
]

# ── Arrows: (from_key, to_key, label) ─────────────────────────
ARROWS = [
    ("opc",       "nifi_edge", "OPC UA\nBinary"),
    ("nifi_edge", "kafka",     "FlowFile\n→ PublishKafka"),
    ("kafka",     "telegraf",  "JSON\nmsg"),
    ("telegraf",  "influxdb",  "Line\nProtocol"),
    ("influxdb",  "grafana",   "Flux\nquery"),
    ("kafka",     "nifi_core", "JSON\nmsg"),
    ("nifi_core", "minio",     "JSON\narray file"),
    ("minio",     "trino",     "SQL\npartition"),
    ("kafka",     "bridge",    "JSON\nmsg"),
    ("bridge",    "openmaint", "REST\nPOST"),
]

PATH_LABELS = {
    "telegraf":  "Path 1 — Real-time Monitoring",
    "nifi_core": "Path 2 — Data Lake",
    "bridge":    "Path 3 — Asset Management",
}

# ── SVG class ─────────────────────────────────────────────────
class SVG:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def raw(self, s): self.parts.append(s)

    def rect(self, x, y, w, h, rx=6, fill="white", stroke="#ccc", sw=1.5, opacity=1, filt=""):
        op  = f' opacity="{opacity}"' if opacity < 1 else ""
        fil = f' filter="url(#{filt})"' if filt else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{op}{fil}/>')

    def text(self, x, y, t, size=12, bold=False, fill="#222", anchor="middle",
             mono=False, italic=False):
        fam  = FONT_MONO if mono else FONT
        wgt  = "bold" if bold else "normal"
        sty  = "italic" if italic else "normal"
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
            f'font-weight="{wgt}" font-style="{sty}" fill="{fill}" '
            f'text-anchor="{anchor}" dominant-baseline="central">'
            f'{escape(str(t))}</text>')

    def line(self, x1, y1, x2, y2, stroke="#888", sw=2, dash="", marker=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#{marker})"' if marker else ""
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}{m}/>')

    def path(self, d, stroke="#888", sw=2, fill="none", marker=""):
        m = f' marker-end="url(#{marker})"' if marker else ""
        self.parts.append(
            f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"{m}/>')

    def save(self, out_path):
        defs = """<defs>
    <filter id="shadow" x="-4%" y="-4%" width="110%" height="118%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#00000025"/>
    </filter>
    <marker id="arr" markerWidth="10" markerHeight="7"
            refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#607d8b"/>
    </marker>
    <marker id="arr-path" markerWidth="10" markerHeight="7"
            refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#607d8b"/>
    </marker>
  </defs>"""
        body = "\n  ".join(self.parts)
        svg = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'  <rect width="100%" height="100%" fill="#eceff1"/>\n'
            f'  {defs}\n  {body}\n</svg>\n')
        with open(out_path, "w") as f:
            f.write(svg)


def card_center(key):
    for k, x, y in LAYOUT:
        if k == key:
            return (x + CARD_W//2, y + CARD_H//2)
    return (0, 0)

def card_rect(key):
    for k, x, y in LAYOUT:
        if k == key:
            return (x, y, x + CARD_W, y + CARD_H)
    return None


def render(out_path):
    s = SVG(W, H)

    # Title bar
    s.rect(0, 0, W, 48, rx=0, fill="#263238", stroke="none")
    s.text(W//2, 16, "Data Flow Diagram — Industrial IoT Data Platform", size=18, bold=True, fill="#eceff1")
    s.text(W//2, 36, "Data format / shape at each pipeline block", size=12, fill="#78909c")

    # ── Path label banners ────────────────────────────────────
    path_colors = {
        "Path 1 — Real-time Monitoring": "#1565c0",
        "Path 2 — Data Lake":            "#b71c1c",
        "Path 3 — Asset Management":     "#4a148c",
    }
    path_y = {"telegraf": 60, "nifi_core": 340, "bridge": 620}
    for key, label in PATH_LABELS.items():
        py = path_y[key]
        color = path_colors[label]
        s.rect(892, py - 2, CARD_W * 3 + 310 + 8, CARD_H + 24,
               rx=10, fill="none", stroke=color, sw=1.5, opacity=0.35)
        s.text(1370, py - 14, label, size=11, bold=True, fill=color)

    # ── Draw arrows ───────────────────────────────────────────
    pos = {k: (x, y) for k, x, y in LAYOUT}

    for src, dst, label in ARROWS:
        sx, sy = pos[src]
        dx, dy = pos[dst]

        # Determine connection points
        src_cx = sx + CARD_W
        src_cy = sy + CARD_H // 2
        dst_cx = dx
        dst_cy = dy + CARD_H // 2

        if sy == dy:
            # Same row — straight horizontal
            mid_x = (sx + CARD_W + dx) // 2
            s.line(sx + CARD_W, src_cy, dx - 2, dst_cy,
                   stroke="#90a4ae", sw=2, marker="arr")
            # label
            for i, ln in enumerate(label.split("\n")):
                s.text(mid_x, src_cy - 14 + i * 13, ln, size=10, fill="#546e7a")
        else:
            # Different row — elbow: go right from Kafka's right edge, then down, then right to dst
            kafka_x, kafka_y = pos["kafka"]
            elbow_x = kafka_x + CARD_W + 16 + (CARD_W + 16) * 0 + 8  # just right of kafka right edge
            # vertical line on left of path blocks
            elbow_x = 882

            src_right = sx + CARD_W
            src_mid_y = sy + CARD_H // 2
            dst_left  = dx
            dst_mid_y = dy + CARD_H // 2

            d = (f"M {src_right} {src_mid_y} "
                 f"H {elbow_x} "
                 f"V {dst_mid_y} "
                 f"H {dst_left - 2}")
            s.path(d, stroke="#90a4ae", sw=2, marker="arr-path")
            # label near elbow
            lx = elbow_x + 6
            for i, ln in enumerate(label.split("\n")):
                s.text(lx + 14, dst_mid_y - 14 + i * 13, ln, size=10, fill="#546e7a", anchor="start")

    # ── Draw cards ────────────────────────────────────────────
    for key, cx, cy in LAYOUT:
        card = CARDS[key]
        z    = ZONE[card["zone"]]

        # Card shadow + body
        s.rect(cx, cy, CARD_W, CARD_H, rx=8,
               fill=z["bg"], stroke=z["border"], sw=1.5, filt="shadow")

        # Header bar
        s.rect(cx, cy, CARD_W, HEADER_H, rx=8,
               fill=z["hfill"], stroke="none")
        # square bottom corners of header
        s.rect(cx, cy + 14, CARD_W, HEADER_H - 14, rx=0,
               fill=z["hfill"], stroke="none")

        # Title
        s.text(cx + CARD_W//2, cy + HEADER_H//2, card["title"],
               size=13, bold=True, fill=z["htext"])

        # Sub-label
        s.text(cx + CARD_W//2, cy + HEADER_H + 11, card["sub"],
               size=9, fill="#78909c", italic=True)

        # Code divider
        s.line(cx + 8, cy + HEADER_H + 22, cx + CARD_W - 8,
               cy + HEADER_H + 22, stroke=z["border"], sw=0.8, dash="3,3")

        # Code lines (monospace)
        code_top = cy + HEADER_H + 32
        line_h   = 13.5
        for i, ln in enumerate(card["lines"]):
            lc = "#455a64" if ln.startswith("─") else "#263238"
            s.text(cx + 10, code_top + i * line_h, ln,
                   size=10, mono=True, fill=lc, anchor="start")

    # ── Legend ────────────────────────────────────────────────
    leg_y = H - 30
    items = [
        ("ot",     "OPC UA / Field"),
        ("nifi",   "NiFi (Edge/Core)"),
        ("kafka",  "Kafka"),
        ("influx", "InfluxDB / Telegraf"),
        ("grafana","Grafana"),
        ("minio",  "MinIO"),
        ("trino",  "Trino"),
        ("bridge", "openmaint-bridge"),
        ("maint",  "OpenMAINT"),
    ]
    lx = 30
    for zk, zlabel in items:
        z = ZONE[zk]
        s.rect(lx, leg_y - 8, 14, 14, rx=3,
               fill=z["hfill"], stroke=z["border"], sw=1)
        s.text(lx + 18, leg_y, zlabel, size=10, fill="#37474f", anchor="start")
        lx += len(zlabel) * 7 + 30

    s.save(out_path)
    print(f"wrote {out_path}  ({W}x{H})")


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    render(os.path.join(out_dir, "diagram-dataflow.svg"))
