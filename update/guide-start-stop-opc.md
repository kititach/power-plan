# คู่มือ: เริ่ม / หยุด OPC UA Pipeline

**วันที่:** 2026-05-06  
**ใช้กับ:** Prosys OPC UA Simulation Server (mintserver) + NiFi Edge (mintpower)

---

## ภาพรวมระบบ

```
mintserver (<OPC_SERVER_IP>)               mintpower (<K3S_NODE_IP> / k3s)
┌────────────────────────────┐         ┌──────────────────────────────┐
│  Prosys OPC UA Sim Server  │──TCP──► │  NiFi Edge                   │
│  port 53530                │         │  → ExecuteGroovyScript       │
│  307 tags (ns=3)           │         │  → PublishKafka              │
│  systemd: prosys-opc       │         │  → Kafka: opc-raw-data       │
│  user: demo                │         └──────────────────────────────┘
└────────────────────────────┘
```

**หมายเหตุ:**
- Prosys รันผ่าน **systemd service `prosys-opc`** — ใช้ `sudo systemctl` เพื่อ start/stop
- NiFi **reconnect อัตโนมัติ** เมื่อ Prosys กลับมา ไม่ต้องทำอะไรเพิ่ม
- Wrapper script: `/usr/local/bin/prosys-start.sh`

---

## เริ่ม Prosys OPC UA Server

### SSH เข้า mintserver

```bash
ssh demo@<OPC_SERVER_IP>
# password: <SSH_PASSWORD>
```

### เริ่ม Prosys ผ่าน systemd

```bash
sudo systemctl start prosys-opc
```

### ตรวจว่าขึ้นแล้ว

```bash
# เช็ค service status
sudo systemctl status prosys-opc

# เช็ค port (ใช้เวลา ~15-30 วินาทีหลัง start)
ss -tlnp | grep 53530
```

ผลที่ถูกต้อง:
```
● prosys-opc.service - Prosys OPC UA Simulation Server
     Active: active (running) since ...
   Main PID: XXXXX (prosys-start.sh)
...
LISTEN 0  50  *:53530  *:*  users:(("java",pid=XXXXX,fd=78))
```

### ตรวจว่า NiFi reconnect แล้ว (จาก mintpower)

```bash
# รอ ~30 วินาที แล้วเช็ค Kafka
sleep 30
kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- bash -c \
  "bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic opc-raw-data 2>/dev/null"
# รัน 2 ครั้ง ห่างกัน 5 วิ — partition 0 และ 2 ต้องเพิ่มขึ้น
```

---

## หยุด Prosys OPC UA Server

### SSH เข้า mintserver

```bash
ssh demo@<OPC_SERVER_IP>
# password: <SSH_PASSWORD>
```

### หยุด Prosys ผ่าน systemd

```bash
sudo systemctl stop prosys-opc
```

### ตรวจว่าหยุดแล้ว

```bash
sudo systemctl status prosys-opc
# ต้องแสดง: Active: inactive (dead)

ss -tlnp | grep 53530
# ต้องไม่มีผล = หยุดแล้ว
```

---

## คำสั่ง systemd อื่นๆ

```bash
# เปิดให้ start อัตโนมัติตอน boot (ตั้งแล้ว)
sudo systemctl enable prosys-opc

# ปิดไม่ให้ start อัตโนมัติ
sudo systemctl disable prosys-opc

# restart (หยุดแล้วเริ่มใหม่)
sudo systemctl restart prosys-opc

# ดู log realtime
sudo journalctl -u prosys-opc -f

# ดู log ล่าสุด 50 บรรทัด
sudo journalctl -u prosys-opc -n 50 --no-pager
```

---

## ตรวจสอบสถานะ (จาก mintpower)

### เช็คด่วน — ทุกส่วนในคำสั่งเดียว

```bash
python3 - << 'EOF'
import json, subprocess, urllib.request, ssl

def nifi_req(token, path):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(f"https://<K3S_NODE_IP>:31444/nifi-api{path}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, context=ctx) as r: return json.load(r)

token = subprocess.run(
    ["curl","-sk","-X","POST","https://<K3S_NODE_IP>:31444/nifi-api/access/token",
     "-H","Content-Type: application/x-www-form-urlencoded",
     "-d","username=admin&password=CHANGE_ME"],
    capture_output=True, text=True).stdout.strip().strip('"')

GROOVY_ID = "fb9e2d81-019d-1000-f255-9b25076647d6"
d = nifi_req(token, f"/flow/processors/{GROOVY_ID}/status")
s = d["processorStatus"]["aggregateSnapshot"]
print(f"NiFi OPC Reader : {d['processorStatus']['runStatus']}")
print(f"  Tasks={s['taskCount']} | Out={s['flowFilesOut']} | Written={s['written']}")
EOF
```

### เช็ค Kafka offset

```bash
kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- bash -c \
  "bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic opc-raw-data 2>/dev/null"
```

| partition | แหล่งข้อมูล | ปกติต้องเพิ่ม |
|-----------|------------|--------------|
| 0, 2 | NiFi → Prosys (mintserver) | ทุก 2 วินาที |
| 1 | Python simulator เก่า (mintpower) | ถ้ายังรันอยู่ |

### ดู NiFi log

```bash
NIFI_POD=$(kubectl get pods -n it -l app=nifi-edge -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n it $NIFI_POD --since=1m | grep "\[OPC\]"
```

| log ที่เห็น | ความหมาย |
|------------|---------|
| `[OPC] Connected ✓` | เชื่อมต่อสำเร็จ |
| `Connection refused: /<OPC_SERVER_IP>:53530` | Prosys ไม่ได้รัน |
| `[OPC] Read failed: timeout` | Prosys รันแต่ช้า/หนัก |

---

## Prosys: ดู log

```bash
# บน mintserver — ดู log จาก xvfb-run output
sudo journalctl -u prosys-opc -f

# หรือ log file โดยตรง
tail -f /tmp/prosys.log
```

---

## สรุปคำสั่งสำคัญ

| งาน | คำสั่ง | รันบน |
|-----|--------|-------|
| เริ่ม Prosys | `sudo systemctl start prosys-opc` | mintserver (demo) |
| หยุด Prosys | `sudo systemctl stop prosys-opc` | mintserver (demo) |
| restart Prosys | `sudo systemctl restart prosys-opc` | mintserver (demo) |
| เช็ค Prosys | `sudo systemctl status prosys-opc` | mintserver |
| เช็ค port | `ss -tlnp \| grep 53530` | mintserver |
| เช็ค Kafka | `kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- bash -c "bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic opc-raw-data 2>/dev/null"` | mintpower |
| ดู NiFi log | `kubectl logs -n it $(kubectl get pods -n it -l app=nifi-edge -o jsonpath='{.items[0].metadata.name}') --since=1m \| grep "\[OPC\]"` | mintpower |
