#!/usr/bin/env python3
"""Generate block diagrams as SVG (editable in Inkscape / draw.io / Illustrator).
Outputs:
  diagram-a-with-ot.svg  : OT zone outside Server, connected by arrow
  diagram-c-no-ot.svg    : Start from Server (DMZ + IT only)

Style mirrors concept/Server_design.pdf page 2: nested rounded rectangles,
title at top-left of each container, pods as inner rounded rectangles.
"""
import os
from xml.sax.saxutils import escape

# ---------- SVG primitives ----------
class SVG:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.parts = []

    def rrect(self, x, y, w, h, r=12, stroke="black", sw=2, fill="white", group_id=None):
        gid = f' id="{group_id}"' if group_id else ""
        self.parts.append(
            f'<rect{gid} x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def text(self, x, y, txt, size=14, bold=False, fill="black", anchor="start"):
        weight = "bold" if bold else "normal"
        # SVG text-anchor: start, middle, end
        anchor_map = {"lt": "start", "lm": "start", "mm": "middle", "mt": "middle", "rt": "end"}
        ta = anchor_map.get(anchor, anchor)
        # dominant-baseline central for vertical centering when anchor ends with 'm'
        dom = "central" if anchor in ("lm", "mm", "rm") else "alphabetic"
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="DejaVu Sans, Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{ta}" dominant-baseline="{dom}">{escape(txt)}</text>'
        )

    def line(self, x1, y1, x2, y2, stroke="black", sw=2):
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def polygon(self, pts, fill="black", stroke="none"):
        s = " ".join(f"{x},{y}" for x, y in pts)
        self.parts.append(f'<polygon points="{s}" fill="{fill}" stroke="{stroke}"/>')

    def save(self, path):
        body = "\n  ".join(self.parts)
        svg = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'  <rect width="100%" height="100%" fill="white"/>\n'
            f'  {body}\n'
            f'</svg>\n'
        )
        with open(path, "w") as f:
            f.write(svg)


# ---------- Helpers ----------
def pod(svg, x0, y0, x1, y1, name, sub=None):
    svg.rrect(x0, y0, x1 - x0, y1 - y0, r=10, sw=2)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    if sub:
        svg.text(cx, cy - 8, name, size=14, bold=True, anchor="mm")
        svg.text(cx, cy + 10, sub, size=11, fill="#555", anchor="mm")
    else:
        svg.text(cx, cy, name, size=14, bold=True, anchor="mm")


def draw_pods(svg, x0, y0, x1, y1, title, pods, cols=2):
    svg.rrect(x0, y0, x1 - x0, y1 - y0, r=14, sw=2)
    svg.text(x0 + 14, y0 + 18, title, size=16, bold=True)

    inner_top = y0 + 42
    inner_bot = y1 - 14
    inner_left = x0 + 16
    inner_right = x1 - 16
    rows = (len(pods) + cols - 1) // cols
    pod_w = (inner_right - inner_left - (cols - 1) * 14) // cols
    pod_h = 50
    gap_y = 12
    total_h = rows * pod_h + (rows - 1) * gap_y
    start_y = inner_top + max(0, ((inner_bot - inner_top) - total_h) // 2)

    for i, p in enumerate(pods):
        r = i // cols
        c = i % cols
        px = inner_left + c * (pod_w + 14)
        py = start_y + r * (pod_h + gap_y)
        name, sub = p if isinstance(p, tuple) else (p, None)
        pod(svg, px, py, px + pod_w, py + pod_h, name, sub)


# ---------- Component lists ----------
DMZ_PODS = [
    ("NiFi Edge", "OPC UA → Kafka"),
    ("Kafka", "Strimzi KRaft"),
    ("AKHQ", "Kafka UI"),
]

IT_PODS = [
    ("Telegraf", "Kafka → InfluxDB"),
    ("InfluxDB", "bucket: opc-data"),
    ("Grafana", "dashboards + alert"),
    ("NiFi Core", "Kafka → MinIO"),
    ("MinIO", "S3 data lake"),
    ("Trino", "SQL query"),
    ("OpenMAINT", "CMMS / work order"),
    ("PostgreSQL 15", "OpenMAINT DB"),
    # ("Mailhog", "mock SMTP"),
    # ("Traefik", "ingress"),
]

HOST_SVC = [
    ("openmaint-bridge", "systemd · Kafka→OpenMAINT"),
    ("k3s-backup.timer","Backup"),
    # ("k3s-backup.timer", "systemd · daily 02:00"),
]


def render(with_ot: bool, out_path: str):
    W, H = (1800, 1100) if with_ot else (1500, 1050)
    s = SVG(W, H)

    title = "Industrial IoT Data Platform — Block Diagram (Current)"
    # if with_ot:
    #     title += " · with OT Zone"
    s.text(W // 2, 32, title, size=20, bold=True, anchor="mm")

    if with_ot:
        ot_x0, ot_y0, ot_x1, ot_y1 = 40, 90, 360, 700
        s.rrect(ot_x0, ot_y0, ot_x1 - ot_x0, ot_y1 - ot_y0, r=14, sw=2)
        s.text(ot_x0 + 14, ot_y0 + 18, "OT Zone (external host)", size=16, bold=True)
        # s.text(ot_x0 + 14, ot_y0 + 42, "mintserver  10.85.3.100", size=12, fill="#555")
        pod(s, ot_x0 + 30, 380, ot_x1 - 30, 460, "Prosys OPC UA")
        # pod(s, ot_x0 + 30, 380, ot_x1 - 30, 460, "Prosys OPC UA", "307 tags · poll 2s")
        s.text((ot_x0 + ot_x1) // 2, 500, "systemd: prosys-opc", size=11, fill="#555", anchor="mm")

        ay = 420
        s.line(ot_x1 + 4, ay, ot_x1 + 60, ay, sw=3)
        s.polygon([(ot_x1 + 60, ay - 8), (ot_x1 + 78, ay), (ot_x1 + 60, ay + 8)])
        s.text(ot_x1 + 6, ay - 14, "opc.tcp", size=11, fill="#333")

        server_x0 = ot_x1 + 90
    else:
        server_x0 = 40

    sv_x0, sv_y0, sv_x1, sv_y1 = server_x0, 90, W - 400, H - 400
    s.rrect(sv_x0, sv_y0, sv_x1 - sv_x0, sv_y1 - sv_y0, r=16, sw=2)
    s.text(sv_x0 + 16, sv_y0 + 22, "Server", size=17, bold=True)

    lx0, ly0, lx1, ly1 = sv_x0 + 20, sv_y0 + 44, sv_x1 - 20, sv_y1 - 20
    s.rrect(lx0, ly0, lx1 - lx0, ly1 - ly0, r=14, sw=2)
    s.text(lx0 + 14, ly0 + 18, "Linux OS", size=16, bold=True)

    # k3s (top) 
    host_h = 92
    k_top = ly0 + 40                                                                                                                                                                    
    kx0, ky0, kx1, ky1 = lx0 + 16, k_top, lx1 - 16, ly1 - 14 - host_h - 14  
    s.rrect(kx0, ky0, kx1 - kx0, ky1 - ky0, r=14, sw=2)
    s.text(kx0 + 14, ky0 + 18, "K8s", size=16, bold=True)

    pad = 16
    inner_top = ky0 + 42
    inner_bot = ky1 - 14
    dmz_w = 360
    draw_pods(s, kx0 + pad, inner_top, kx0 + pad + dmz_w, inner_bot,
              "DMZ Zone", DMZ_PODS, cols=1)
    draw_pods(s, kx0 + pad + dmz_w + 18, inner_top, kx1 - pad, inner_bot,
              "IT Zone", IT_PODS, cols=2)

    # Host services (systemd) — bottom                                                                                                                                                  
    hx0, hy0, hx1, hy1 = lx0 + 16, ky1 + 14, lx1 - 16, ly1 - 14                                                                                                                         
    s.rrect(hx0, hy0, hx1 - hx0, hy1 - hy0, r=12, sw=2, stroke="#444")                                                                                                                  
    s.text(hx0 + 12, hy0 + 14, "Host services (systemd)", size=13, bold=True, fill="#444")                                                                                              
    pw = (hx1 - hx0 - 40) // 2                                                                                                                                                          
    for i, (n, sub) in enumerate(HOST_SVC):                                                                                                                                             
      px = hx0 + 12 + i * (pw + 16)                                                                                                                                                   
      pod(s, px, hy0 + 32, px + pw, hy1 - 10, n, sub)                                                                                                                                 

    s.save(out_path)
    print(f"wrote {out_path}  ({W}x{H})")


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    render(with_ot=True,  out_path=os.path.join(out_dir, "diagram-a-with-ot.svg"))
    # render(with_ot=False, out_path=os.path.join(out_dir, "diagram-c-no-ot.svg"))
