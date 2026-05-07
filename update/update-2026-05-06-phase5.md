# Phase 5 Update — systemd + Format Flatten + Telegraf
**Date:** 2026-05-06  
**Status:** ✅ COMPLETE — InfluxDB รับข้อมูลแล้ว (307 fields), NiFi Core→MinIO ✅, Grafana dashboard ✅

---

## สิ่งที่ทำในวันนี้

### 1. systemd service สำหรับ Prosys OPC UA Server (mintserver)

**ปัญหาเดิม:** Prosys ใช้ install4j launcher ที่ fork Java แล้ว exit ทันที ทำให้ `Type=simple` คิดว่า service จบแล้ว

**วิธีแก้:** สร้าง wrapper script ที่ start xvfb-run แบบ background แล้วใช้ `kill -0` loop รอ Java process แทน `wait` (เพราะ Java เป็น grandchild ไม่ใช่ child โดยตรง)

**ไฟล์ที่สร้าง:**

`/etc/systemd/system/prosys-opc.service` (บน mintserver):
```ini
[Unit]
Description=Prosys OPC UA Simulation Server
After=network.target

[Service]
Type=simple
User=demo
WorkingDirectory=/home/demo/prosys-opc-ua-simulation-server
ExecStart=/usr/local/bin/prosys-start.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`/usr/local/bin/prosys-start.sh` (บน mintserver):
```bash
#!/bin/bash
cd /home/demo/prosys-opc-ua-simulation-server
/usr/bin/xvfb-run -a ./UaSimulationServer &>/tmp/prosys.log &

for i in $(seq 1 30); do
    JAVA_PID=$(pgrep -f "prosys-opc-ua-simulation-server/jre/bin/java" 2>/dev/null | head -1)
    [ -n "$JAVA_PID" ] && break
    sleep 1
done

if [ -z "$JAVA_PID" ]; then
    echo "ERROR: Java process did not start within 30s" >&2
    exit 1
fi

echo "Prosys Java PID: $JAVA_PID"
while kill -0 "$JAVA_PID" 2>/dev/null; do
    sleep 5
done
echo "Prosys Java exited"
```

**คำสั่ง:**
```bash
sudo systemctl start prosys-opc     # เริ่ม
sudo systemctl stop prosys-opc      # หยุด
sudo systemctl restart prosys-opc   # restart
sudo systemctl status prosys-opc    # ตรวจสอบ
```

**สถานะ:** enabled, active (running), port 53530 เปิดอยู่

---

### 2. แก้ไข Architecture — ตัวเลือก A (ให้ consumer อ่าน opc-raw-data โดยตรง)

**ปัญหาเดิม:**
- Telegraf อ่านจาก `opc-metrics` (ข้อมูลเก่าจาก Python simulator)
- NiFi Core อ่านจาก `opc-datalake` (ข้อมูลเก่า)
- ไม่มีใคร route ข้อมูลใหม่จาก `opc-raw-data`

**แนวคิด:** Kafka ทำ fan-out ได้เองอยู่แล้ว ไม่ต้องสร้าง routing processor เพิ่ม แค่ให้ consumer แต่ละตัว subscribe `opc-raw-data` โดยตรง

---

### 3. แก้ Groovy Script — Flatten format

**ไฟล์:** `/home/mintpower/lab/k3s/tools/opc_reader_final.groovy`

**ก่อน:**
```json
{
  "timestamp": 1778059011.277,
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tags": { "Counter": 9, "Temp_Boiler_01": 90.0, ...307 fields },
  "tag_count": 307,
  "bad_count": 0
}
```

**หลัง:**
```json
{
  "timestamp": "2026-05-06T09:29:19.113336942Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tag_count": 307,
  "bad_count": 0,
  "Counter": 9,
  "Temp_Boiler_01": 90.0,
  ...307 fields at top level
}
```

**โค้ดที่เปลี่ยน (บรรทัด 375-382):**
```groovy
// ก่อน
def payload = [
    timestamp : System.currentTimeMillis() / 1000.0,
    source_id : SOURCE_ID,
    device_id : DEVICE_ID,
    tags      : tags,
    tag_count : tags.size(),
    bad_count : tags.values().count { it == null }
]

// หลัง
def badCount = tags.values().count { it == null }
def payload = [
    timestamp : java.time.Instant.now().toString(),
    source_id : SOURCE_ID,
    device_id : DEVICE_ID,
    tag_count : tags.size(),
    bad_count : badCount
] + tags
```

Deploy ผ่าน: `python3 /home/mintpower/lab/k3s/tools/deploy_opc_script.py`

---

### 4. แก้ Telegraf ConfigMap

**namespace:** `it`, **configmap:** `telegraf-config`

**เปลี่ยน:**
- `topics = ["opc-metrics"]` → `["opc-raw-data"]`
- เพิ่ม `tag_keys = ["source_id", "device_id"]`
- `json_time_format` คงเดิม (RFC3339 ตรงกับ ISO8601 ที่ script ส่งมา)

**ผลใน InfluxDB (bucket: opc-data):**
```
measurement : opc_data
tags        : device_id=opc-prosys-300tags
              host=telegraf-mintpower
              source_id=mintserver-prosys
fields      : Counter, Random, Temp_Boiler_01, ... (307 fields)
              tag_count, bad_count
time        : จาก OPC UA timestamp
```

---

## Flow ปัจจุบัน

```
Prosys OPC UA (mintserver:53530)
  └─ opc.tcp ──► NiFi Edge — ExecuteGroovyScript (Eclipse Milo)
                   └─ PublishKafka ──► Kafka: opc-raw-data
                                         ├─ Telegraf ──► InfluxDB (bucket: opc-data) ✅
                                         └─ NiFi Core ──► MinIO   ❌ (ยังอ่านจาก opc-datalake)
```

---

## TODO — งานที่ยังค้าง

- [x] **ขั้น 3:** แก้ NiFi Core ConsumeKafka topic: `opc-datalake` → `opc-raw-data` (processor ID: `f34df3ea-019d-1000-56f9-8392070b9184`)
- [x] **ขั้น 4:** ตรวจสอบ MinIO bucket `opc-raw` รับข้อมูลใหม่ — 303+ files ใน `data/year=2026/month=05/day=06/`
- [x] **ขั้น 5:** แก้ Grafana dashboard (uid: `ffl0uchin1hxcc`) — อัปเดต 12 panels ให้ query field ชุดใหม่ (v12)

---

## Key IDs (ณ 2026-05-06)

| Component | ID / ค่า |
|-----------|---------|
| NiFi Edge ExecuteGroovyScript | `fb9e2d81-019d-1000-f255-9b25076647d6` |
| NiFi Edge PublishKafka | `fb9e5838-019d-1000-1592-de95686c8a58` |
| NiFi Core ConsumeKafka | อ่านจาก `opc-datalake` (ต้องแก้เป็น `opc-raw-data`) |
| InfluxDB bucket | `opc-data` |
| InfluxDB org | `mintpower-org` |
| InfluxDB token | `CHANGE_ME` |
| Kafka bootstrap | `kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092` |
