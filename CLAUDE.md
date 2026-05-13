# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Industrial IoT Data Platform บน **k3s single-node** (Linux Mint 22.3) ทำงานในสภาพแวดล้อม **Airgap** (ไม่มีอินเทอร์เน็ต) รับข้อมูล OPC-UA จาก Prosys 307 tags แล้วส่งผ่าน Kafka ไปยัง 3 path พร้อมกัน

**อ่าน `STATUS.md` ก่อนทำงานทุกครั้ง** — มี component status, credentials, และ known issues ล่าสุด

---

## Architecture

```
OT Zone                  DMZ (ns: dmz)           IT Zone (ns: it)
─────────────────────────────────────────────────────────────────
Prosys OPC UA                                     Path 1: Real-time
(307 tags, 2s)  →  NiFi Edge  →  Kafka  →  Telegraf → InfluxDB → Grafana
                   (Groovy/       (opc-raw-data    Path 2: Data Lake
                    Milo 0.6)      topic)      →  NiFi Core → MinIO → Trino
                                               Path 3: Asset Management
                                               →  openmaint-bridge (systemd)
                                                  → OpenMAINT + PostgreSQL 15
```

**Kafka topic:** `opc-raw-data` เป็นเพียง topic เดียว (topics เก่า `opc-metrics`, `opc-datalake` ถูกลบแล้ว)

---

## Manifest Structure

```
manifests/
├── phase1/   # namespaces (dmz, it), StorageClass, PVs บน /mnt/nvme-storage/k8s-pv/
├── phase2/   # Strimzi Kafka (KRaft mode), AKHQ
├── phase3/   # InfluxDB, Telegraf, Grafana (with postStart token fix)
├── phase4/   # MinIO, NiFi Core, Trino + partition sync CronJob
├── phase5/   # NiFi Edge, OpenMAINT, PostgreSQL 15
└── phase6/   # Traefik ingress (*.mintpower.local)
```

Apply ทีละ phase ตามลำดับ — downstream components ขึ้นอยู่กับ Kafka ที่ต้อง ready ก่อน

---

## Common Commands

```bash
# ดู pod ทุกตัว
kubectl get pods -A --no-headers | awk '{print $1,$2,$3,$4,$5}'

# Kafka consumer lag
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --all-groups 2>/dev/null

# Restart ลำดับที่ถูกต้อง: Kafka → NiFi Edge → Consumers
kubectl rollout restart statefulset/kafka-cluster-broker -n dmz
kubectl wait pod -n dmz -l strimzi.io/name=kafka-cluster-kafka --for=condition=Ready --timeout=120s
kubectl rollout restart deployment/nifi-edge -n it
kubectl rollout restart deployment/telegraf deployment/nifi-core -n it

# OpenMAINT bridge (ทำงานบน mintpower host ไม่ใช่ใน k8s)
sudo systemctl status openmaint-bridge
sudo journalctl -u openmaint-bridge -f

# Prosys OPC UA (ต้อง SSH ไปที่ mintserver)
ssh demo@10.85.3.100    # password: ดู STATUS.md
sudo systemctl start|stop|status prosys-opc

# Re-deploy NiFi Edge Groovy script (ถ้า flow หาย)
python3 tools/deploy_opc_script.py

# OpenMAINT status
curl -s http://localhost:30885/cmdbuild/services/rest/v3/boot/status

# Load airgap images
sudo k3s ctr images import install/<image>.tar
```

---

## Key OPC-UA Data Format

JSON ที่ NiFi Edge ส่งเข้า Kafka (flat format — 307 fields ระดับ top-level):
```json
{
  "timestamp": "2026-05-07T05:00:00.000Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tag_count": 307,
  "bad_count": 0,
  "Temp_Boiler_01": 85.3,
  "Press_Line_01": 120.5,
  "Vibration_Pump_01": 0.023
}
```

Telegraf ใช้ `tag_keys` อ่าน field ทุกตัวเข้า InfluxDB measurement `opc_data` (org: `mintpower-org`, bucket: `opc-data`)

---

## Critical Gotchas

### Grafana Datasource Token
- `lifecycle.postStart` hook ใน `manifests/phase3/grafana.yaml` inject token อัตโนมัติทุกครั้งที่ pod start
- ถ้า account lock: แก้ที่ SQLite DB ลบ `login_attempt` table — **อย่า restart pod** เพิ่มเติม

### Grafana Timeseries Panel
- ใช้ `legend.displayMode = "list"` — ถ้าใช้ `"hidden"` graph จะไม่ render (Grafana 11 bug)

### OpenMAINT (CMDBuild 3.4.1-d)
- CMDBuild log ไม่แสดงใน `kubectl logs` — ต้องอ่านจากใน container: `kubectl exec -n it <pod> -- tail -f /usr/local/tomcat/logs/cmdbuild.log`
- ถ้า pod READY 1/1 แต่ RAM < 10Mi หมายความว่า Tomcat ตาย แก้ด้วย `kubectl rollout restart deployment/openmaint -n it`
- ถ้า CorrectiveMaint workflow ค้าง: ตรวจสอบ `_advance: true` ใน POST payload และ DMS disabled (`org.cmdbuild.dms.enabled = false` ใน `_SystemConfig`)
- PostGIS stub functions ต้องสร้างใหม่ทุกครั้งหลัง pg_restore (ดู README.md หัวข้อ Known Issues)

### NiFi Edge Eclipse Milo
- ต้องมี `guava-33.3.1-jre.jar` ใน `/opt/nifi/nifi-current/data/milo-jars/`
- `hostAliases` ใน nifi-edge deployment ต้องมี entry สำหรับ `mintserver` → IP ของ OPC server
- PublishKafka ต้องตั้ง `Transactions Enabled = false`

### Telegraf
- CPU limit: `1000m`, flush interval: `30s`, offset: `newest` (แก้ throttling แล้ว)

### OpenMAINT Bridge (systemd)
- ทำงานบน mintpower host (ไม่ใช่ pod) — อ่านจาก Kafka `opc-raw-data`, ส่ง Alarm + CorrectiveMaint เข้า OpenMAINT
- Cooldown 5 นาที/tag เพื่อป้องกัน spam
- Script: `tools/openmaint_bridge.py`

---

## Access Points

| Service | NodePort | Namespace |
|---|---|---|
| Grafana | `:30300` | it |
| InfluxDB | `:30086` | it |
| MinIO Console | `:30901` | it |
| NiFi Core | `:31443` (HTTPS) | it |
| NiFi Edge | `:31444` (HTTPS) | it |
| OpenMAINT | `:30885` | it |
| Trino | `:30800` | it |
| AKHQ | `:30880` | dmz |
| Kafka external | `:32092` | dmz |

Credentials อยู่ใน `STATUS.md`

---

## Tools

| ไฟล์ | หน้าที่ |
|---|---|
| `tools/opc_reader_final.groovy` | Groovy script ที่รันใน NiFi Edge (อย่าใช้ `opc_reader.groovy` — เวอร์ชันเก่า) |
| `tools/deploy_opc_script.py` | Deploy/update Groovy script ขึ้น NiFi Edge ผ่าน REST API |
| `tools/openmaint_bridge.py` | Kafka → OpenMAINT bridge (threshold rules, Alarm, CorrectiveMaint) |
| `tools/browse_opc.py` | Browser สำหรับ OPC UA node tree |
| `scripts/setup-nifi-core-flow.sh` | Recreate NiFi Core flows (ConsumeKafka → MergeRecord → PutS3Object) |
