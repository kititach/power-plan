# แผนดูแลระบบ k3s Data Platform

**อัปเดตล่าสุด:** 2026-05-07  
**Node:** mintpower — Linux Mint 22.3, k3s v1.31.4+k3s1 (single-node)  
**สภาพแวดล้อม:** Airgap (ไม่มีอินเทอร์เน็ต)

---

## สถานะระบบ ณ 2026-05-07

| Component | Namespace | Status | หมายเหตุ |
|---|---|---|---|
| k3s node | — | Ready | อายุ 6 วัน |
| Kafka (Strimzi KRaft) | dmz | Running | 3 topics, 154k+ messages |
| AKHQ | dmz | Running | Kafka UI |
| NiFi Edge | it | Running | OPC → Kafka producer |
| NiFi Core | it | Running | Kafka → MinIO consumer |
| Telegraf | it | Running | Kafka → InfluxDB consumer |
| InfluxDB | it | Running | 35k records/24h per field |
| Grafana | it | Running | dashboard uid: ffl0uchin1hxcc |
| MinIO | it | Running | 2,856+ files (4 วันล่าสุด) |
| Trino | it | Running | SQL query บน MinIO |
| OpenMAINT | it | Running / READY | CMMS asset management |
| PostgreSQL | it | Running | backend OpenMAINT |

**NVMe disk:** 1.5 GB used / 469 GB (1%) — ยังเหลือเยอะมาก

---

## Access Points

| Service | URL / Port | Credentials |
|---|---|---|
| Grafana | http://localhost:30300 | admin / CHANGE_ME |
| InfluxDB | http://localhost:30086 | token: `CHANGE_ME` |
| MinIO Console | http://localhost:30901 | ดู secret `minio-secret` |
| NiFi Core | https://localhost:31443/nifi | — |
| NiFi Edge | https://localhost:31444/nifi | — |
| OpenMAINT | http://localhost:30885/cmdbuild | — |
| AKHQ | http://localhost:30880 | Kafka UI |
| Trino | http://localhost:30800/ui | — |
| Kafka External | localhost:32092 | bootstrap สำหรับ external client |

**Ingress (Traefik):** `*.mintpower.local` — ต้องมี `/etc/hosts` หรือ DNS

---

## Data Pipeline

```
OT ZONE                   DMZ ZONE              IT ZONE
──────────────────────────────────────────────────────────

Prosys OPC UA             ┌──────────┐    Telegraf → InfluxDB → Grafana
(mintserver)              │          │    (real-time, lag < 10)
     │                    │  Kafka   │
     ▼                    │opc-raw-  │    NiFi Core → MinIO → Trino
NiFi Edge ───────────────▶│  data    │    (datalake, lag < 10)
(Groovy flatten           │          │
 307 tags top-level)      └──────────┘    OpenMAINT + PostgreSQL
                                          (asset management)
```

**Kafka Topics:**

| Topic | Retention | Consumer |
|---|---|---|
| `opc-raw-data` | 7 วัน | telegraf-opc-consumer, nifi-core-consumer |
| `opc-metrics` | 1 วัน | (stale — ไม่ใช้แล้วใน Phase 5) |
| `opc-datalake` | 30 วัน | (stale — ไม่ใช้แล้วใน Phase 5) |

**InfluxDB:**
- Org: `mintpower-org`
- Bucket: `opc-data`
- Measurement: `opc_data`
- Tags: `source_id=mintserver-prosys`, `device_id=opc-prosys-300tags`
- Fields: 307 tags (Temp_Boiler_01, Press_Line_01, CO2_Zone_01-10, ...)

**MinIO:**
- Bucket: `opc-raw`
- Path: `data/year=YYYY/month=MM/day=DD/{uuid}.json`
- Batch size: 100 messages ต่อไฟล์

---

## Quick Health Check

```bash
# 1. ดูทุก pod
kubectl get pods -A --no-headers | awk '{print $1,$2,$3,$4,$5}'

# 2. Kafka consumer lag
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --all-groups 2>/dev/null

# 3. InfluxDB รับข้อมูลอยู่ไหม (ดู 5 นาทีล่าสุด)
kubectl exec -n it influxdb-657785f5b4-jhpfv -- \
  sh -c 'influx query --token CHANGE_ME --org mintpower-org \
  "from(bucket:\"opc-data\") |> range(start:-5m) \
  |> filter(fn:(r)=>r[\"_field\"]==\"Temp_Boiler_01\") |> count()"'

# 4. MinIO ไฟล์วันนี้
TODAY=$(date +%d); MONTH=$(date +%m)
kubectl exec -n it minio-f44478c76-7b2t9 -- \
  mc ls local/opc-raw/data/year=2026/month=${MONTH}/day=${TODAY}/ | wc -l

# 5. OpenMAINT status
curl -s http://localhost:30885/cmdbuild/services/rest/v3/boot/status
```

**Lag เกณฑ์ปกติ:**

| Consumer Group | ปกติ | ต้องตรวจสอบ |
|---|---|---|
| telegraf-opc-consumer | < 10 | > 1,000 |
| nifi-core-consumer | < 10 | > 1,000 |
| nifi-edge-consumer | stale (no active consumer) | ถ้ามี consumer กลับมา + lag > 10,000 |

---

## แผนรับมือปัญหา

### 🔴 OpenMAINT ไม่ขึ้น READY / restart loop

**สาเหตุที่รู้:** CMDBuild restart Tomcat ใน boot ครั้งแรก — command override ใน `manifests/phase5/openmaint.yaml` จัดการแล้ว

```bash
# ดู log จริง (kubectl logs ไม่แสดง cmdbuild.log)
kubectl exec -n it <openmaint-pod> -- \
  tail -100 /usr/local/tomcat/logs/cmdbuild.log

# รอ ~5 นาที แล้วตรวจ
curl -s http://localhost:30885/cmdbuild/services/rest/v3/boot/status
# ต้องได้: {"success":true,"status":"READY"}

# ถ้ายังไม่ READY ให้ restart pod
kubectl rollout restart deployment/openmaint -n it
```

---

### 🔴 OPC data หยุดไหลเข้า Kafka

```bash
# ตรวจ Prosys OPC UA บน mintserver
systemctl status <prosys-service-name> --no-pager

# ตรวจ NiFi Edge
kubectl logs -n it <nifi-edge-pod> --tail=30

# ดู disk NiFi Edge (ปัจจุบัน 62GB/218GB — ถ้าเต็มจะหยุด)
kubectl exec -n it <nifi-edge-pod> -- df -h /opt/nifi/nifi-current/

# Restart NiFi Edge
kubectl rollout restart deployment/nifi-edge -n it
```

---

### 🔴 InfluxDB ไม่รับข้อมูล

```bash
# ดู Telegraf error
kubectl logs -n it <telegraf-pod> --tail=30

# ตรวจ org/bucket (org ต้องเป็น "mintpower-org" ไม่ใช่ "mintpower")
kubectl exec -n it <influxdb-pod> -- \
  sh -c 'influx org list --token CHANGE_ME'

# Restart Telegraf
kubectl rollout restart deployment/telegraf -n it
```

---

### 🔴 MinIO ไม่รับไฟล์

```bash
# ดู NiFi Core log
kubectl logs -n it <nifi-core-pod> --tail=30

# ตรวจ nifi-core-consumer lag
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group nifi-core-consumer 2>/dev/null

# Restart NiFi Core
kubectl rollout restart deployment/nifi-core -n it
```

---

### 🟡 Kafka lag พุ่งสูง (consumer ตามไม่ทัน)

```bash
# Reset offset ไปที่ latest (ข้อมูลที่ lag จะหาย)
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group telegraf-opc-consumer \
  --topic opc-raw-data \
  --reset-offsets --to-latest --execute
```

---

### 🟡 Grafana password ใช้ไม่ได้

```bash
kubectl exec -n it <grafana-pod> -- \
  grafana cli admin reset-admin-password 'CHANGE_ME'
```

---

### 🟡 PostGIS error ใน OpenMAINT

PostGIS stub functions ถูก inject ลงใน database โดยตรง (`gis` schema) — ไม่ต้องติดตั้ง extension จริง ควร persist ข้ามการ restart pod แต่ถ้าหาย:

```bash
# ดู log หา "postgis" error
kubectl exec -n it <openmaint-pod> -- \
  grep -i postgis /usr/local/tomcat/logs/cmdbuild.log | tail -10
```

---

## ลำดับ Restart ที่ถูกต้อง

```bash
# 1. Kafka ก่อน (ถ้าจำเป็น)
kubectl rollout restart statefulset/kafka-cluster-broker -n dmz
# รอจนเป็น Running
kubectl wait pod -n dmz -l strimzi.io/name=kafka-cluster-kafka \
  --for=condition=Ready --timeout=120s

# 2. Producer (NiFi Edge)
kubectl rollout restart deployment/nifi-edge -n it

# 3. Consumers (หลัง Kafka ready)
kubectl rollout restart deployment/telegraf -n it
kubectl rollout restart deployment/nifi-core -n it
```

---

## Storage

**PersistentVolumes บน** `/mnt/nvme-storage/k8s-pv/` (NVMe 469 GB, ใช้ 1%):

| PV | ขนาด | ใช้โดย | Status |
|---|---|---|---|
| pv-kafka | 50Gi | Kafka broker | Bound |
| pv-influxdb2 | 50Gi | InfluxDB | Bound |
| pv-influxdb | 50Gi | — | Available (spare) |
| pv-minio | 100Gi | MinIO | Bound |
| pv-nifi-core | 20Gi | NiFi Core | Bound |
| pv-nifi-edge | 10Gi | NiFi Edge | Bound |
| pv-grafana | 10Gi | Grafana | Bound |
| pv-openmaint | 20Gi | PostgreSQL + OpenMAINT | Bound |
| pv-trino | 20Gi | Trino | Bound |

```bash
# เช็ค disk ทั้งหมด
df -h /mnt/nvme-storage/k8s-pv/

# ดูขนาดแต่ละ PV
du -sh /mnt/nvme-storage/k8s-pv/*/
```

**เกณฑ์เตือน:** ถ้า NVMe ใช้เกิน 80% ให้ลบ Kafka archive เก่า หรือ MinIO partition เก่าออก

---

## การ Redeploy ระบบใหม่

ถ้าต้อง rebuild cluster ทำตามลำดับ Phase:

```bash
kubectl apply -f manifests/phase1/   # Namespace + Storage
kubectl apply -f install/strimzi-*/install/cluster-operator/ -n dmz
kubectl apply -f manifests/phase2/   # Kafka
kubectl apply -f manifests/phase3/   # InfluxDB + Grafana
kubectl apply -f manifests/phase4/   # MinIO + Trino + NiFi Core
kubectl apply -f manifests/phase5/   # NiFi Edge + OpenMAINT
kubectl apply -f manifests/phase6/   # (ถ้ามี)
```

**หลัง redeploy สิ่งที่ต้องทำเพิ่ม:**
1. Restore OpenMAINT database: `pg_restore` จาก dump ใน postgres image
2. Import NiFi Core flow ผ่าน UI หรือ `scripts/setup-nifi-core-flow.sh`
3. ตรวจ Grafana dashboard uid `ffl0uchin1hxcc` — import ใหม่ถ้าหาย

---

## Known Issues

| ปัญหา | สถานะ | หมายเหตุ |
|---|---|---|
| `nifi-edge-consumer` lag ~49k | ไม่กระทบ | Stale consumer group, ไม่มี active consumer — ไม่ใช่ bug ของ pipeline |
| InfluxDB org name | แก้แล้ว | ต้องใช้ `mintpower-org` ไม่ใช่ `mintpower` |
| OpenMAINT restart loop on first boot | แก้แล้ว | command override ใน openmaint.yaml |
| PostGIS ไม่มีใน image | แก้แล้ว | stub functions ใน `gis` schema ของ database |
