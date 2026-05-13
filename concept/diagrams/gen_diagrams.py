#!/usr/bin/env python3
"""Generate block diagrams (PNG) in the style of concept/Server_design.pdf page 2.
Outputs:
  diagram-a-with-ot.png  : OT zone outside Server, connected by arrow
  diagram-c-no-ot.png    : Start from Server (DMZ + IT only)
"""
from PIL import Image, ImageDraw, ImageFont

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)

def rrect(draw, box, radius=12, outline="black", width=2, fill="white"):
    draw.rounded_rectangle(box, radius=radius, outline=outline, width=width, fill=fill)

def label(draw, xy, text, f, fill="black", anchor="lt"):
    draw.text(xy, text, font=f, fill=fill, anchor=anchor)

def pod(draw, box, name, sub=None):
    rrect(draw, box, radius=10, width=2)
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    if sub:
        label(draw, (cx, cy - 10), name, font(14, bold=True), anchor="mm")
        label(draw, (cx, cy + 10), sub, font(11), fill="#555", anchor="mm")
    else:
        label(draw, (cx, cy), name, font(14, bold=True), anchor="mm")


def draw_pods(draw, zone_box, title, pods, cols=2):
    """Draw a zone box with pod grid inside. pods = list of (name, sub) tuples."""
    x0, y0, x1, y1 = zone_box
    rrect(draw, zone_box, radius=14, width=2)
    label(draw, (x0 + 14, y0 + 8), title, font(16, bold=True))

    # Footer label (bottom)
    # leave 30px header, 30px footer
    inner_top = y0 + 38
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
        pod(draw, (px, py, px + pod_w, py + pod_h), name, sub)


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
    ("Mailhog", "mock SMTP"),
    ("Traefik", "ingress"),
]

HOST_SVC = [
    ("openmaint-bridge", "systemd · Kafka→OpenMAINT"),
    ("k3s-backup.timer", "systemd · daily 02:00"),
]


def render(with_ot: bool, out_path: str):
    W, H = (1500, 800) if with_ot else (1500, 1050)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    title = "Industrial IoT Data Platform — Block Diagram (Current)"
    if with_ot:
        title += " · with OT Zone"
    label(d, (W // 2, 28), title, font(20, bold=True), anchor="mm")

    if with_ot:
        # OT zone (external, left)
        ot_box = (40, 110, 360, 720)
        rrect(d, ot_box, radius=14, width=2)
        label(d, (ot_box[0] + 14, ot_box[1] + 8), "OT Zone (external host)", font(16, bold=True))
        label(d, (ot_box[0] + 14, ot_box[1] + 32), "mintserver  10.85.3.100", font(12), fill="#555")
        pod(d, (ot_box[0] + 30, 380, ot_box[2] - 30, 460),
            "Prosys OPC UA", "307 tags · poll 2s")
        label(d, ((ot_box[0] + ot_box[2]) // 2, 500),
              "systemd: prosys-opc", font(11), fill="#555", anchor="mm")

        # Arrow OT → Server
        ay = 420
        d.line([(ot_box[2] + 4, ay), (ot_box[2] + 60, ay)], fill="black", width=3)
        # arrowhead
        d.polygon([(ot_box[2] + 60, ay - 8), (ot_box[2] + 78, ay), (ot_box[2] + 60, ay + 8)], fill="black")
        label(d, (ot_box[2] + 6, ay - 24), "opc.tcp", font(11), fill="#333")

        server_x0 = ot_box[2] + 90
    else:
        server_x0 = 40

    # Server outer
    server_box = (server_x0, 90, W - 40, H - 60)
    rrect(d, server_box, radius=16, width=2)
    label(d, (server_box[0] + 16, server_box[1] + 10), "Server  (mintpower  10.85.3.104)", font(17, bold=True))

    # Linux OS
    linux_box = (server_box[0] + 20, server_box[1] + 44, server_box[2] - 20, server_box[3] - 20)
    rrect(d, linux_box, radius=14, width=2)
    label(d, (linux_box[0] + 14, linux_box[1] + 8), "Linux Mint 22.3", font(16, bold=True))

    # Host services (above k3s) — small row
    host_top = linux_box[1] + 40
    host_h = 92
    host_box = (linux_box[0] + 16, host_top, linux_box[2] - 16, host_top + host_h)
    rrect(d, host_box, radius=12, width=2, outline="#444")
    label(d, (host_box[0] + 12, host_box[1] + 6), "Host services (systemd)", font(13, bold=True), fill="#444")
    pw = (host_box[2] - host_box[0] - 40) // 2
    for i, (n, s) in enumerate(HOST_SVC):
        px = host_box[0] + 12 + i * (pw + 16)
        pod(d, (px, host_box[1] + 32, px + pw, host_box[3] - 10), n, s)

    # K8s box (below host services)
    k8s_top = host_box[3] + 14
    k8s_box = (linux_box[0] + 16, k8s_top, linux_box[2] - 16, linux_box[3] - 14)
    rrect(d, k8s_box, radius=14, width=2)
    label(d, (k8s_box[0] + 14, k8s_box[1] + 8), "k3s (Kubernetes single-node)", font(16, bold=True))

    # Two zones inside k8s: DMZ + IT
    pad = 16
    inner_top = k8s_box[1] + 40
    inner_bot = k8s_box[3] - 14
    dmz_w = 360
    dmz_box = (k8s_box[0] + pad, inner_top, k8s_box[0] + pad + dmz_w, inner_bot)
    it_box = (dmz_box[2] + 18, inner_top, k8s_box[2] - pad, inner_bot)

    draw_pods(d, dmz_box, "DMZ Zone  (ns: dmz)", DMZ_PODS, cols=1)
    draw_pods(d, it_box, "IT Zone  (ns: it)", IT_PODS, cols=2)

    img.save(out_path, "PNG")
    print(f"wrote {out_path}  ({W}x{H})")


if __name__ == "__main__":
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    render(with_ot=True,  out_path=os.path.join(out_dir, "diagram-a-with-ot.png"))
    render(with_ot=False, out_path=os.path.join(out_dir, "diagram-c-no-ot.png"))
