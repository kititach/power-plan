# สรุปโปรเจกต์ k3s — Airgap Data Platform

**วันที่สร้าง:** 2026-05-03  
**อัปเดตล่าสุด:** 2026-05-06 16:40 (UTC+7)  
**ผู้ดูแล:** mintpower  
**Node:** mintpower (Linux Mint 22.3, k3s v1.31.4+k3s1)

### ประวัติการอัปเดต

| วันที่ | เวลา | รายการ |
|--------|------|--------|
| 2026-05-03 | — | Deploy ระบบครั้งแรก, แก้ไข OpenMAINT ทั้ง 7 ปัญหา |
| 2026-05-04 | 13:00 | แก้ Telegraf timestamp format → InfluxDB ได้รับ OPC data ครบ 12 sensors |
| 2026-05-04 | 14:30 | สร้าง Grafana OPC Sensor Dashboard ครบทุก sensor, แก้ legend bug |
| 2026-05-04 | 22:30 | Configure NiFi Core flows — data ไหลเข้า MinIO แล้ว 76+ JSON files |
| 2026-05-04 | 23:35 | สร้าง Trino partitioned table `minio.opc.sensor_data` — end-to-end pipeline สมบูรณ์ |
| 2026-05-05 | 11:24 | ตรวจสอบสถานะระบบ — ทุก pod Running/Completed, OpenMAINT READY |
| 2026-05-05 | 12:55 | แก้ Telegraf CPU throttle: limit 500m→1000m, flush 10s→30s, offset→newest (analysis: `scripts/telegraf-cpu-analysis.md`) |
| 2026-05-06 | — | Prosys OPC UA systemd service บน mintserver, flatten JSON format (307 tags top-level), Telegraf→opc-raw-data |
| 2026-05-06 | 16:40 | NiFi Core ConsumeKafka→opc-raw-data, MinIO รับข้อมูลใหม่, Grafana dashboard 12 panels อัปเดต field names |

---

## ภาพรวมของระบบ

ระบบนี้คือ **Kubernetes cluster แบบ single-node** ที่ทำงานในสภาพแวดล้อม **Airgap** (ไม่มีการเชื่อมต่ออินเทอร์เน็ต) โดยใช้ k3s เป็น Kubernetes distribution และ load container images จาก `.tar` files ที่เตรียมไว้ล่วงหน้า

**วัตถุประสงค์:** รับข้อมูลจากอุปกรณ์ OT/OPC (Operational Technology) ผ่าน pipeline แล้วจัดเก็บ วิเคราะห์ และแสดงผล รวมถึงบริหารจัดการสินทรัพย์ด้วย OpenMAINT

---

## สถาปัตยกรรมโดยรวม

ระบบแบ่งเป็น **3 Zone** ตาม concept (`concept.png`) โดยมี Kafka เป็นจุดรับ-ส่งข้อมูลกลาง และมี 3 data path ออกจาก Kafka สู่ IT Zone

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 OT ZONE                DMZ ZONE              IT ZONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 OPC Server             ┌──────────┐    ┌──────────┐  ┌──────────┐  ┌─────────┐
 (10.85.3.100)          │          │    │ Telegraf │→│ InfluxDB │→│ Grafana │
      │                 │          │    └──────────┘  └──────────┘  └─────────┘
      ▼                 │          │
 ┌──────────┐           │  Kafka   │    ┌──────────┐  ┌──────────┐  ┌─────────┐
 │NiFi Edge │──────────▶│ (dmz ns) │───▶│NiFi Core │→│  MinIO   │→│  Trino  │
 └──────────┘           │          │    └──────────┘  └──────────┘  └─────────┘
                        │          │
                        └──────────┘    ┌────────────────────────┐
                                        │ OpenMAINT + PostgreSQL │
                                        └────────────────────────┘

                                        ┌────────────────────────┐
                                        │    Traefik Ingress     │
                                        └────────────────────────┘
```

---

## คำอธิบาย Concept แต่ละบล็อก

### OT Zone — Operational Technology

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **OPC Server** | แหล่งข้อมูล sensor | อุปกรณ์ OT/SCADA ที่เปิดข้อมูลผ่าน OPC-UA protocol เช่น PLC, DCS, RTU — ในระบบนี้ใช้ simulator ที่ `10.85.3.100` ส่งค่า 12 sensors ทุก 2 วินาที |
| **NiFi Edge** | Edge data collector | Apache NiFi ที่ deploy ใกล้กับ OT network ทำหน้าที่ poll ข้อมูลจาก OPC Server แปลงเป็น JSON แล้วส่งเข้า Kafka ใน DMZ — ออกแบบให้ทำงาน airgap ได้ ใช้ heap ขนาดเล็ก (1G–2G) |

---

### DMZ Zone — Demilitarized Zone

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **Kafka** | Message broker / Buffer | Apache Kafka ทำหน้าที่รับข้อมูลจาก OT zone และกระจายให้ consumers ใน IT zone — แยก topic ตามวัตถุประสงค์ 3 topic: `opc-raw-data` (ดิบ 7 วัน), `opc-metrics` (real-time 1 วัน), `opc-datalake` (historical 30 วัน) รัน KRaft mode ไม่ต้องใช้ Zookeeper |
| **AKHQ** | Kafka Web UI | UI สำหรับดู topics, offsets, consumer groups และ message content ใน Kafka — ใช้ monitor ว่าข้อมูลไหลอยู่หรือไม่ |

---

### IT Zone — Enterprise Analytics

#### Path 1: Real-time Monitoring

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **Telegraf** | Metrics collector | Subscribe topic `opc-metrics` จาก Kafka แปลง JSON เป็น line protocol แล้วเขียนลง InfluxDB — ทำงาน polling ทุก 10 วินาที, consumer group: `telegraf-opc-consumer` |
| **InfluxDB** | Time-series database | เก็บค่า sensor ทุกตัวในรูป time-series — org: `mintpower-org`, bucket: `opc-data`, measurement: `opc_data`, fields: `readings_<sensor>_value` (12 fields) |
| **Grafana** | Dashboard & Visualization | แสดงกราฟ sensor แบบ real-time ผ่าน Flux query จาก InfluxDB — refresh 5 วินาที, dashboard: "OPC Sensor Dashboard" (uid: `ffl0uchin1hxcc`), datasource: InfluxDB-OPC |

#### Path 2: Data Lake & SQL Analytics

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **NiFi Core** | ETL pipeline | Subscribe topic `opc-datalake` จาก Kafka แปลง JSON แล้วเขียนลง MinIO — flows configured แล้ว (2026-05-04), data ไหลเข้า bucket `opc-raw` ได้ 76+ JSON files |
| **MinIO** | Object storage (S3-compatible) | เก็บ Parquet files จาก NiFi Core — bucket: `opc-raw`, path: `/year=YYYY/month=MM/`, accessible ผ่าน S3 API ที่ port 9000 |
| **Trino** | Distributed SQL query engine | Query ข้อมูล Parquet ใน MinIO ผ่าน SQL มาตรฐาน — catalog: `minio`, connector: Hive, ไม่ต้อง load ข้อมูลเข้า database เพียงแค่สร้าง external table ชี้ไปที่ MinIO |

#### Path 3: Asset Management

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **OpenMAINT** | CMMS / Asset Management | ระบบบริหารจัดการสินทรัพย์และบำรุงรักษา (Computerized Maintenance Management System) ใช้สำหรับลงทะเบียนอุปกรณ์, จัดการ work order, ติดตาม maintenance — based on CMDBuild 3.4.1-d |
| **PostgreSQL 15** | Relational database | Database backend ของ OpenMAINT — ใช้ `postgres:15-alpine`, database: `openmaint`, มี PostGIS stub functions สำหรับ GIS schema |

#### Infrastructure

| บล็อก | บทบาท | รายละเอียด |
|-------|--------|-----------|
| **Traefik** | Ingress controller & Reverse proxy | รับ HTTP/HTTPS requests จาก client และ route ไปยัง service ที่ถูกต้องตาม hostname — ทุก service ใช้ subdomain `.mintpower.local` |

---

## Namespace

| Namespace | วัตถุประสงค์ |
|-----------|-------------|
| `dmz` | Kafka cluster, AKHQ — รับข้อมูลจาก OT network |
| `it` | ทุก service ที่เหลือ — analytics, storage, visualization |

---

## Storage

**StorageClass:** `local-nvme` (manual provisioner, `WaitForFirstConsumer`, `Retain`)

**PersistentVolumes บน `/mnt/nvme-storage/k8s-pv/`:**

| PV | ขนาด | ใช้โดย |
|----|------|--------|
| pv-kafka | 50Gi | Kafka broker |
| pv-influxdb2 | 50Gi | InfluxDB |
| pv-influxdb | 50Gi | — (Available · spare) |
| pv-minio | 100Gi | MinIO |
| pv-nifi-core | 20Gi | NiFi Core |
| pv-nifi-edge | 10Gi | NiFi Edge |
| pv-grafana | 10Gi | Grafana |
| pv-openmaint | 20Gi | PostgreSQL + OpenMAINT |
| pv-trino | 20Gi | Trino |

---

## Services และ Access Points

| Service | NodePort | Ingress (hostname) | Namespace |
|---------|----------|--------------------|-----------|
| Kafka (internal) | 9092 | — | dmz |
| Kafka (external) | 32092 | — | dmz |
| AKHQ | — | akhq.mintpower.local | dmz |
| InfluxDB | — | influxdb.mintpower.local | it |
| Grafana | — | grafana.mintpower.local | it |
| MinIO Console | — | minio.mintpower.local | it |
| NiFi Core | 31443 | nifi-core.mintpower.local | it |
| NiFi Edge | 31444 | nifi-edge.mintpower.local | it |
| Trino | — | trino.mintpower.local | it |
| **OpenMAINT** | **30885** | openmaint.mintpower.local | it |

---

## การ Deploy — แบ่งเป็น 6 Phase

---

### Phase 1 — Infrastructure

**ไฟล์:** `manifests/phase1/`

| ไฟล์ | สิ่งที่ทำ |
|------|----------|
| `namespaces.yaml` | สร้าง namespace `dmz` และ `it` |
| `storage-class.yaml` | สร้าง StorageClass `local-nvme` แบบ manual (no-provisioner) |
| `persistent-volumes.yaml` | สร้าง PV ทั้งหมด 8 รายการ บน NVMe local path |

**คำสั่ง:**
```bash
kubectl apply -f manifests/phase1/
```

---

### Phase 2 — Message Broker (Kafka)

**ไฟล์:** `manifests/phase2/`

**Components:**
- **Strimzi Operator** — Kafka operator สำหรับ k8s
- **Kafka Cluster** — KRaft mode (ไม่ใช้ Zookeeper), 1 broker node
- **AKHQ** — Kafka web UI

**Kafka Topics ที่สร้าง:**

| Topic | Retention | วัตถุประสงค์ |
|-------|-----------|-------------|
| `opc-raw-data` | 7 วัน | รับข้อมูล OPC ดิบจาก NiFi Edge |
| `opc-metrics` | 1 วัน | real-time metrics → Telegraf |
| `opc-datalake` | 30 วัน | historical data → NiFi Core → MinIO |

**คำสั่ง:**
```bash
# Install Strimzi operator ก่อน
kubectl apply -f install/strimzi-0.43.0/install/cluster-operator/ -n dmz
kubectl apply -f manifests/phase2/
```

---

### Phase 3 — Monitoring Stack

**ไฟล์:** `manifests/phase3/`

**Components:**
- **InfluxDB 2.7** — Time-series database, org: mintpower, bucket: opc-data
- **Telegraf** — Collect metrics จาก Kafka topic `opc-metrics` → ส่งไป InfluxDB
- **Grafana** — Dashboard, datasource = InfluxDB

**Telegraf Data Flow:**
```
Kafka (opc-metrics) → Telegraf → InfluxDB (bucket: opc-data)
System CPU/Mem ──────────────────▶ InfluxDB
```

**คำสั่ง:**
```bash
kubectl apply -f manifests/phase3/
```

---

### Phase 4 — Data Platform

**ไฟล์:** `manifests/phase4/`

**Components:**
- **MinIO** — Object storage (S3-compatible), bucket: `opc-raw`
- **NiFi Core** — Data pipeline ดึงจาก Kafka `opc-datalake` → MinIO (Parquet)
- **Trino 463** — SQL query engine เชื่อมกับ MinIO ผ่าน Hive connector

**Trino Catalogs:**
- `minio` connector → `s3://opc-raw/` ใน MinIO (path-style access)

**NiFi Core JVM:** heap 2G–4G

**คำสั่ง:**
```bash
kubectl apply -f manifests/phase4/
```

---

### Phase 5 — Edge Collector + Asset Management

**ไฟล์:** `manifests/phase5/`

**Components:**
- **NiFi Edge** — รับข้อมูลจาก OPC server `10.85.3.100`, ส่งไป Kafka (heap 1G–2G)
- **PostgreSQL 15** (`postgres:15-alpine`) — Database สำหรับ OpenMAINT
- **OpenMAINT 2.3** (`itmicus/cmdbuild:om-2.3-3.4.1-d`) — Asset/Facility Management

**คำสั่ง:**
```bash
kubectl apply -f manifests/phase5/
```

---

### Phase 6 — Ingress & Routing

**ไฟล์:** `manifests/phase6/`

**Components:**
- **Traefik** — Ingress controller (custom values)
- **Ingress DMZ** — route `akhq.mintpower.local`
- **Ingress IT** — route services ทั้งหมดในฝั่ง IT zone
- **NiFi TCP** — passthrough สำหรับ NiFi HTTPS ports
- **Trino Middleware** — header stripPrefix

**คำสั่ง:**
```bash
helm upgrade --install traefik traefik/traefik -f manifests/phase6/traefik-values.yaml
kubectl apply -f manifests/phase6/
```

---

## การแก้ไขปัญหา OpenMAINT (บันทึกสำคัญ)

OpenMAINT เป็น service ที่ต้องใช้เวลาแก้ปัญหามากที่สุด บันทึกนี้สำคัญมากสำหรับการ deploy ใหม่

### ปัญหาและวิธีแก้ตามลำดับ

---

#### ปัญหาที่ 1: POSTGRES_HOST ผิด

**อาการ:** CrashLoopBackOff, connection refused

**สาเหตุ:** ค่า `POSTGRES_HOST` ใน `openmaint.yaml` เป็น `openmaint_db` แต่ K8s service จริงชื่อ `postgres-openmaint`

**แก้ไข:** เปลี่ยนค่าใน env var:
```yaml
- name: POSTGRES_HOST
  value: "postgres-openmaint"   # ← แก้จาก openmaint_db
```

---

#### ปัญหาที่ 2: CMDBUILD_DUMP ไม่มีในไฟล์

**อาการ:** container exit ทันที

**สาเหตุ:** ระบุ `openmaint-2.3.dump.xz` แต่ใน image มีแค่ `demo.dump.xz` และ `empty.dump.xz`

**แก้ไข:**
```yaml
- name: CMDBUILD_DUMP
  value: "demo.dump.xz"   # ← แก้จาก openmaint-2.3.dump.xz
```

---

#### ปัญหาที่ 3: PostgreSQL version ไม่เข้ากัน

**อาการ:** pg_restore error — `SET default_table_access_method = 'heap'` ไม่รู้จัก

**สาเหตุ:** image เดิม `itmicus/cmdbuild:db-3.0` ใช้ PostgreSQL 10 แต่ dump file ใช้ syntax ของ PG12+

**แก้ไข:** เปลี่ยน image ใน `postgres.yaml`:
```yaml
image: postgres:15-alpine    # ← แก้จาก itmicus/cmdbuild:db-3.0
```

พร้อมเปลี่ยน env vars ให้ตรงกับ official postgres image:
```yaml
env:
  - name: POSTGRES_PASSWORD
    value: "postgres"
# ลบ POSTGRES_USER, POSTGRES_DB ออก (CMDBuild จะสร้างเอง)
```

---

#### ปัญหาที่ 4: Data เก่า PG10 ค้างอยู่บน PVC

**อาการ:** postgres pod ไม่ start เพราะ data directory version ไม่ตรง

**แก้ไข:** ใช้ busybox pod ล้าง data เก่า:
```bash
kubectl run cleanup --image=busybox -n it --restart=Never \
  --overrides='{"spec":{"volumes":[{"name":"data","persistentVolumeClaim":{"claimName":"pvc-openmaint"}}],"containers":[{"name":"cleanup","image":"busybox","command":["sh","-c","rm -rf /data/postgres && mkdir -p /data/postgres"],"volumeMounts":[{"name":"data","mountPath":"/data"}]}]}}'
```

---

#### ปัญหาที่ 5: PostGIS extension ไม่มีใน postgres:15-alpine

**อาการ:** `pg_restore` error — `type gis.geometry does not exist`

**สาเหตุ:** CMDBuild dump ต้องการ PostGIS แต่ `postgres:15-alpine` ไม่มี PostGIS และ image `postgis/postgis:15-alpine` ไม่ได้ load ไว้ใน airgap

**แก้ไข (2 ขั้นตอน):**

1. สร้าง fake PostGIS stub ใน postgres container filesystem (ชั่วคราว สำหรับ CREATE EXTENSION):
```bash
PGPOD=$(kubectl get pods -n it -l app=postgres-openmaint -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n it $PGPOD -- sh -c "
  EXTDIR=\$(pg_config --sharedir)/extension
  printf 'default_version = '\''3.3.3'\''\nrelocatable = true\n' > \$EXTDIR/postgis.control
  printf '-- stub\n' > \$EXTDIR/postgis--3.3.3.sql
"
```

2. สร้าง PostGIS stub functions โดยตรงใน database (ถาวร):
```bash
kubectl exec -n it $PGPOD -- psql -U postgres -d openmaint \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_lib_version() RETURNS text LANGUAGE sql AS \$\$ SELECT '3.3.3'::text; \$\$;" \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_version() RETURNS text LANGUAGE sql AS \$\$ SELECT '3.3.3 USE_GEOS=1 USE_PROJ=1 USE_STATS=1'::text; \$\$;" \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_full_version() RETURNS text LANGUAGE sql AS \$\$ SELECT 'POSTGIS=\"3.3.3\" PGSQL=\"150\"'::text; \$\$;"
```

---

#### ปัญหาที่ 6: โหลด database ด้วย CMDBuild Java ล้มเหลว

**อาการ:** `type gis.geometry does not exist` ระหว่าง Java-based db init

**แก้ไข:** โหลด dump โดยตรงด้วย `pg_restore` แทน ผ่าน postgres container:
```bash
# copy dump เข้า container แล้วรัน pg_restore โดยตรง
kubectl exec -n it $PGPOD -- pg_restore \
  --host=localhost --username=postgres --dbname=openmaint \
  --no-exit-on-error --verbose /tmp/demo.dump
```

ผลลัพธ์: โหลดสำเร็จ 710+ tables

---

#### ปัญหาที่ 7 (Root Cause): Container exit loop — CMDBuild restart Tomcat

**อาการ:** pod status = `Completed` (exit 0) ซ้ำๆ ทุก ~30 วินาที ไม่มี error จาก `kubectl logs`

**สาเหตุ (สำคัญมาก):**  
CMDBuild's `PostgresDriverAutoconfigureHelperServiceImpl` ทำ **full Tomcat stop + start** ทุกครั้งที่ boot ครั้งแรก เพื่อ copy postgres JDBC driver จาก `WEB-INF/lib_ext/` → `WEB-INF/lib/`

เมื่อใช้ `exec catalina.sh run` ทำให้ Tomcat เป็น PID 1 ของ container:
- Tomcat stop → PID 1 exit → container exit (code 0)
- K8s เห็นว่า container "Completed" → restart pod
- Tomcat ใหม่ที่ platform helper พยายามสร้างไม่มีโอกาสทำงาน

**แก้ไข:** override command ใน `openmaint.yaml` ให้ bash script เป็น PID 1 แทน:

```yaml
command: ["/bin/bash", "-c"]
args:
  - |
    trap 'pkill -f "org.apache.catalina" 2>/dev/null; exit 0' SIGTERM SIGINT
    /usr/local/bin/docker-entrypoint.sh &
    while true; do
      sleep 15
      pgrep -f "org.apache.catalina" > /dev/null && continue
      sleep 10
      pgrep -f "org.apache.catalina" > /dev/null || exit 1
    done
```

**ผลลัพธ์:**
- Tomcat start → CMDBuild restart (6 วินาที) → Tomcat start ใหม่ → READY
- bash script (PID 1) ยังทำงานอยู่ตลอดช่วง restart

---

### สรุปลำดับการแก้ไขทั้งหมด

```
1. แก้ POSTGRES_HOST: openmaint_db → postgres-openmaint
2. แก้ CMDBUILD_DUMP: openmaint-2.3.dump.xz → demo.dump.xz
3. เปลี่ยน image: itmicus/cmdbuild:db-3.0 → postgres:15-alpine
4. ล้าง PG10 data จาก PVC (busybox pod)
5. สร้าง fake PostGIS stub (control file)
6. โหลด database ด้วย pg_restore โดยตรง
7. สร้าง PostGIS stub functions ใน database (persistent)
8. Override command เพื่อแก้ Tomcat restart loop
```

---

## สถานะ Services ปัจจุบัน

> อัปเดต: 2026-05-04 15:12

```
NAMESPACE   NAME                   READY   STATUS
dmz         akhq                   1/1     Running
dmz         kafka-cluster-broker   1/1     Running
dmz         strimzi-operator       1/1     Running
it          grafana                1/1     Running  ✅ dashboard พร้อม
it          influxdb               1/1     Running  ✅ ได้รับ OPC data ครบ 12 sensors
it          minio                  1/1     Running
it          nifi-core              1/1     Running  ⚠ ยังไม่มี flow
it          nifi-edge              1/1     Running  ✅ fan-out ไป 2 topics
it          openmaint              1/1     Running  ✅ READY
it          postgres-openmaint     1/1     Running
it          telegraf               1/1     Running  ✅ consume opc-metrics LAG≈0
it          trino                  1/1     Running  ⚠ ไม่มี schema/data
```

**Kafka topic offsets (2026-05-04 15:00):**

| Topic | Messages | Retention | สถานะ |
|-------|----------|-----------|--------|
| `opc-raw-data` | 22,000+ | 7 วัน | ✅ ไหลอยู่ |
| `opc-metrics` | 4,800+ | 1 วัน | ✅ ไหลอยู่ |
| `opc-datalake` | 4,800+ | 30 วัน | ✅ ไหลอยู่ |

**Verify services:**
```bash
# OpenMAINT
curl http://localhost:30885/cmdbuild/services/rest/v3/boot/status
# → {"success":true,"status":"READY"}

# InfluxDB OPC data
kubectl exec -n it deploy/influxdb -- influx query \
  --token influx-super-secret-token-mintpower --org mintpower-org \
  'from(bucket:"opc-data") |> range(start:-1m) |> filter(fn:(r)=>r._measurement=="opc_data") |> count()'

# Grafana dashboard
# http://10.85.3.104:30300/d/ffl0uchin1hxcc/opc-sensor-dashboard
```

---

## Tips & ข้อควรระวัง

### Logs ของ CMDBuild
`kubectl logs` จะ**ไม่เห็น** application logs ของ CMDBuild  
ต้องอ่านจาก: `/usr/local/tomcat/logs/cmdbuild.log` ภายใน container

```bash
OPOD=$(kubectl get pods -n it -l app=openmaint -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n it $OPOD -- tail -f /usr/local/tomcat/logs/cmdbuild.log
```

### PostGIS stub ใน database (สำคัญ)
Functions `postgis_lib_version()`, `postgis_version()`, `postgis_full_version()` ถูกสร้างใน schema `gis` ของ database openmaint โดยตรง — functions เหล่านี้ **persistent** ข้าม pod restart แต่ถ้า database ถูกลบแล้วสร้างใหม่ต้องสร้างใหม่ทุกครั้ง

```bash
PGPOD=$(kubectl get pods -n it -l app=postgres-openmaint -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n it $PGPOD -- psql -U postgres -d openmaint -c "\df gis.postgis*"
```

### การ deploy OpenMAINT ใหม่
ถ้าต้อง deploy OpenMAINT ใหม่ทั้งหมด ให้ทำตามลำดับ:
1. Apply `postgres.yaml` → รอ postgres ready
2. ล้าง data เก่าถ้ามี (busybox)
3. สร้าง PostGIS stub control files ใน postgres container
4. รัน pg_restore โหลด demo.dump
5. สร้าง PostGIS stub functions ใน database
6. Apply `openmaint.yaml` (มี command override แล้ว)

### GeoServer
`GIS_ GeoServer client` จะแสดง error เสมอ — เป็นเรื่องปกติ ไม่มี GeoServer deploy ในระบบนี้ ไม่กระทบการทำงานหลัก

---

## ไฟล์สำคัญ

```
k3s/
├── install/                    # images (.tar), binaries
│   ├── openmaint-images.tar    # OpenMAINT + base images
│   ├── postgres-image.tar      # postgres:15-alpine
│   └── ...
├── manifests/
│   ├── phase1/                 # namespace, storage, PV
│   ├── phase2/                 # kafka, akhq
│   ├── phase3/                 # influxdb, grafana, telegraf
│   ├── phase4/                 # minio, nifi-core, trino
│   ├── phase5/                 # nifi-edge, openmaint, postgres  ← แก้ไขมากสุด
│   └── phase6/                 # traefik ingress
├── config/
│   └── k3s-config.yaml
└── bin/
    └── helm
```

---

<!-- ══════════════════════════════════════
     เพิ่ม 2026-05-04
     ══════════════════════════════════════ -->

## Credentials — User / Password ทุก Service

| Service | URL / Access | Username | Password / Token | หมายเหตุ |
|---------|-------------|----------|-----------------|---------|
| **Grafana** | `:30300` · grafana.mintpower.local | `admin` | `Grafana@mintpower2024` | |
| **InfluxDB** | `:30086` · influxdb.mintpower.local | `admin` | `Influx@mintpower2024` | Org: `mintpower-org` · Bucket: `opc-data` |
| **InfluxDB Token** | API / Telegraf | — | `influx-super-secret-token-mintpower` | ใช้ใน Telegraf config |
| **MinIO** | `:30901` · minio.mintpower.local | `minioadmin` | `Minio@mintpower2024` | Bucket: `opc-raw` |
| **NiFi Core** | `:31443` (HTTPS) · nifi-core.mintpower.local | `admin` | `Nifi@mintpower2024!` | |
| **NiFi Edge** | `:31444` (HTTPS) · nifi-edge.mintpower.local | `admin` | `Nifi@mintpower2024!` | |
| **OpenMAINT** | `:30885` · openmaint.mintpower.local | `admin` | `admin` | CMDBuild default — เปลี่ยนหลัง deploy จริง |
| **PostgreSQL** (superuser) | internal only | `postgres` | `postgres` | สำหรับ maintenance เท่านั้น |
| **PostgreSQL** (openmaint) | internal only | `openmaint` | `Openmaint@mintpower2024` | DB: `openmaint` |
| **AKHQ** | `:30880` · akhq.mintpower.local | — | — | ไม่มี auth (open) |
| **Kafka** | `:32092` (external) | — | — | PLAINTEXT · internal: `:9092` |
| **Trino** | `:30800` · trino.mintpower.local | — | — | ไม่มี auth · Catalog: `minio` |

> ⚠ **Lab credentials เท่านั้น** — เปลี่ยนก่อน deploy production โดยเฉพาะ `postgres/postgres` และ `admin/admin`

---

## สิ่งที่ต้องทำ — Remaining Tasks (อัปเดต 2026-05-04 15:12)

| # | งาน | สถานะ | หมายเหตุ |
|---|-----|--------|---------|
| 1 | **NiFi Edge flows** | ✅ เสร็จแล้ว (2026-05-04) | configure ผ่าน REST API — fan-out → opc-metrics + opc-datalake |
| 2 | **แก้ Telegraf timestamp format** | ✅ เสร็จแล้ว (2026-05-04 13:00) | `json_time_format` → RFC3339Nano — InfluxDB ได้รับ OPC data ครบ 12 sensors |
| 3 | **สร้าง Grafana OPC dashboard** | ✅ เสร็จแล้ว (2026-05-04 14:30) | 12 panels, refresh 5s, uid: `ffl0uchin1hxcc` |
| 4 | **NiFi Core flows** → MinIO JSON | ✅ เสร็จแล้ว (2026-05-04) | flow: ConsumeKafka(opc-datalake) → MergeRecord(100) → PutS3Object — 76+ files ใน MinIO |
| 5 | สร้าง Trino table schema | ✅ เสร็จแล้ว (2026-05-04) | partitioned table `minio.opc.sensor_data` — query ได้ทุก sensor field |
| 6 | ลบ `pvc-kafka` orphan (dmz) | ✅ เสร็จแล้ว | `kubectl delete pvc pvc-kafka -n dmz` |

### รายละเอียด Task 1 — NiFi Edge ✅ (configure แล้ว 2026-05-04)
```
URL:  https://10.85.3.104:31444/nifi  (admin / Nifi@mintpower2024!)
Flow: ConsumeKafka(opc-raw-data) → PublishKafka(opc-metrics)
                                 → PublishKafka(opc-datalake)
```

### รายละเอียด Task 2 — NiFi Core
```
URL:  https://10.85.3.104:31443/nifi  (admin / Nifi@mintpower2024!)
Flow: ConsumeKafka(opc-datalake) → ConvertRecord(JSON→Parquet)
                                 → PutS3Object(minio.it.svc:9000, bucket:opc-raw)
```

### รายละเอียด Task 5 — Trino schema
```sql
CREATE SCHEMA minio.opc;
CREATE TABLE minio.opc.raw_data (...)
  WITH (external_location = 's3a://opc-raw/', format = 'PARQUET');
```

---

## ขั้นตอนการทดลอง — End-to-End Pipeline Test

### สถานะปัจจุบัน (อัปเดต 2026-05-04 15:12)

| Component | สถานะ | หมายเหตุ |
|-----------|--------|---------|
| OPC Simulator | ✅ Running | 12 sensors ทุก 2s → `opc-raw-data` (22,000+ msg) |
| `opc-raw-data` Kafka | ✅ มีข้อมูล | 22,000+ messages และเพิ่มขึ้นเรื่อยๆ |
| NiFi Edge flows | ✅ Running | fan-out → `opc-metrics` + `opc-datalake` (4,800+ msg แต่ละ topic) |
| `opc-metrics` Kafka | ✅ ไหล | 4,800+ messages |
| `opc-datalake` Kafka | ✅ ไหล | 4,800+ messages |
| Telegraf → InfluxDB | ✅ ทำงานปกติ | LAG≈0, เขียน 12 sensor fields ทุก 2s — แก้ `json_time_format` RFC3339Nano แล้ว |
| InfluxDB | ✅ มีข้อมูล | measurement `opc_data`, 12 fields (`readings_*_value`), ได้รับข้อมูล real-time |
| Grafana OPC Dashboard | ✅ พร้อม | 12 panels, refresh 5s — `http://10.85.3.104:30300/d/ffl0uchin1hxcc` |
| NiFi Core → MinIO | ✅ ทำงานแล้ว | 76+ JSON files, 17MB+, เพิ่มขึ้นทุก 60s |
| Trino | ✅ query ได้แล้ว | table `minio.opc.sensor_data`, partition year/month/day |
| OpenMAINT | ✅ READY | `http://10.85.3.104:30885/cmdbuild` — admin/admin |
| `pvc-kafka` (dmz) | ✅ ลบแล้ว | orphan PVC ถูกลบแล้ว |

---

### Step 1 — ตรวจสอบ OPC Simulator

```bash
systemctl status opc-simulator

# ดู offset เพิ่มขึ้นทุก 2s
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server localhost:9092 --topic opc-raw-data

# ดูตัวอย่าง message (JSON ครบ 12 sensors)
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic opc-raw-data --max-messages 1 --timeout-ms 5000
```

---

### Step 2 — Configure NiFi Edge ✅ เสร็จแล้ว (2026-05-04)

```
URL:  https://10.85.3.104:31444/nifi
User: admin / Nifi@mintpower2024!
```

**Flow:** ConsumeKafka(`opc-raw-data`) → PublishKafka(`opc-metrics`) + PublishKafka(`opc-datalake`)

---

#### วิธีที่ 1 — REST API (ใช้ deploy ครั้งแรกหรือ redeploy)

```bash
# 1. Get token
TOKEN=$(curl -sk -X POST https://localhost:31444/nifi-api/access/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Nifi%40mintpower2024%21")

# 2. Get root process group ID
ROOT_PG=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  https://localhost:31444/nifi-api/flow/process-groups/root | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['processGroupFlow']['id'])")

# 3. Create Kafka3ConnectionService (NiFi 2.0 ต้องใช้ Controller Service)
CS=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/controller-services" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.service.Kafka3ConnectionService\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-3-service-nar\",\"version\":\"2.0.0\"},
      \"name\": \"KafkaConnectionService\",
      \"properties\": {
        \"bootstrap.servers\": \"kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092\"
      }
    }
  }")
CS_ID=$(echo $CS | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
CS_VER=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://localhost:31444/nifi-api/controller-services/$CS_ID" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['revision']['version'])")

# 4. Enable controller service
curl -sk -X PUT \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/controller-services/$CS_ID/run-status" \
  -d "{\"revision\":{\"version\":$CS_VER},\"state\":\"ENABLED\"}" > /dev/null

# 5. Create ConsumeKafka
CONSUME_ID=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.processors.ConsumeKafka\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-nar\",\"version\":\"2.0.0\"},
      \"name\": \"ConsumeKafka — opc-raw-data\",
      \"position\": {\"x\": 300, \"y\": 100},
      \"config\": {
        \"properties\": {
          \"Kafka Connection Service\": \"$CS_ID\",
          \"Topics\": \"opc-raw-data\",
          \"Group ID\": \"nifi-edge-consumer\",
          \"auto.offset.reset\": \"latest\"
        },
        \"autoTerminatedRelationships\": [\"parse.failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 6. Create PublishKafka — opc-metrics
PUB_METRICS_ID=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.processors.PublishKafka\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-nar\",\"version\":\"2.0.0\"},
      \"name\": \"PublishKafka — opc-metrics\",
      \"position\": {\"x\": 0, \"y\": 400},
      \"config\": {
        \"properties\": {
          \"Kafka Connection Service\": \"$CS_ID\",
          \"Topic Name\": \"opc-metrics\"
        },
        \"autoTerminatedRelationships\": [\"success\", \"failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 7. Create PublishKafka — opc-datalake
PUB_DATALAKE_ID=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.processors.PublishKafka\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-nar\",\"version\":\"2.0.0\"},
      \"name\": \"PublishKafka — opc-datalake\",
      \"position\": {\"x\": 600, \"y\": 400},
      \"config\": {
        \"properties\": {
          \"Kafka Connection Service\": \"$CS_ID\",
          \"Topic Name\": \"opc-datalake\"
        },
        \"autoTerminatedRelationships\": [\"success\", \"failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 8. Connect ConsumeKafka → PublishKafka (opc-metrics)
curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/connections" \
  -d "{\"revision\":{\"version\":0},\"component\":{
    \"source\":{\"id\":\"$CONSUME_ID\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"destination\":{\"id\":\"$PUB_METRICS_ID\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"selectedRelationships\":[\"success\"]}}" > /dev/null

# 9. Connect ConsumeKafka → PublishKafka (opc-datalake)
curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/process-groups/$ROOT_PG/connections" \
  -d "{\"revision\":{\"version\":0},\"component\":{
    \"source\":{\"id\":\"$CONSUME_ID\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"destination\":{\"id\":\"$PUB_DATALAKE_ID\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"selectedRelationships\":[\"success\"]}}" > /dev/null

# 10. Start all processors
curl -sk -X PUT \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://localhost:31444/nifi-api/flow/process-groups/$ROOT_PG" \
  -d "{\"id\":\"$ROOT_PG\",\"state\":\"RUNNING\"}" > /dev/null

echo "Done — verifying offsets..."
sleep 10
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server localhost:9092 --topic opc-metrics,opc-datalake
```

---

#### วิธีที่ 2 — NiFi UI (step-by-step)

**สิ่งที่ต้องสร้างใน NiFi 2.0:**
NiFi 2.0 ไม่มี bootstrap.servers ตรงๆ ใน processor ต้องสร้าง **Controller Service** ก่อน

**ขั้นตอน:**

**A. สร้าง Controller Service (Kafka Connection)**

1. เปิด `https://10.85.3.104:31444/nifi` → login `admin / Nifi@mintpower2024!`
2. คลิกไอคอน **≡ (hamburger)** มุมบนซ้าย → **Controller Settings**
3. แท็บ **Controller Services** → กด **+** (Add)
4. ค้นหา `Kafka3ConnectionService` → **Add**
5. คลิกไอคอน **✏ (edit)** ของ service ที่สร้าง
6. แท็บ **Properties** → กรอก:
   - `Bootstrap Servers` = `kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092`
7. กด **Apply** → คลิกไอคอน **▶ (enable)** → **Enable**
8. รอจนสถานะเป็น **Enabled** (สีเขียว)

> ⚠ ถ้าต้องการสร้าง service ระดับ Process Group แทน: คลิกขวา canvas → **Configure** → **Controller Services** → **+**

**B. สร้าง ConsumeKafka Processor**

1. ลาก Processor จาก toolbar มาวาง canvas → ค้นหา `ConsumeKafka` → **Add**
2. Double-click processor → แท็บ **Properties** → กรอก:
   - `Kafka Connection Service` = เลือก service ที่สร้างในขั้น A
   - `Topics` = `opc-raw-data`
   - `Group ID` = `nifi-edge-consumer`
   - `auto.offset.reset` = `latest`
3. แท็บ **Relationships** → tick **Auto-terminate** ที่ `parse.failure`
4. กด **Apply**

**C. สร้าง PublishKafka สองตัว**

สร้าง PublishKafka ตัวที่ 1 (`opc-metrics`):
1. ลาก Processor → ค้นหา `PublishKafka` → **Add**
2. Double-click → **Properties** → กรอก:
   - `Kafka Connection Service` = service เดิม
   - `Topic Name` = `opc-metrics`
3. **Relationships** → tick **Auto-terminate** ทั้ง `success` และ `failure`
4. กด **Apply**

สร้าง PublishKafka ตัวที่ 2 (`opc-datalake`) — ทำเหมือนกัน:
- `Topic Name` = `opc-datalake`

**D. เชื่อม Connection**

1. วางเมาส์เหนือ `ConsumeKafka` จนเห็นลูกศรตรงกลาง
2. ลาก arrow ไปยัง `PublishKafka — opc-metrics` → เลือก relationship **success** → **Add**
3. ทำซ้ำ: ลาก arrow จาก `ConsumeKafka` ไปยัง `PublishKafka — opc-datalake` → **success** → **Add**

**E. Start**

1. กด **Ctrl+A** เลือก processor ทั้งหมด
2. คลิกขวา → **Start**
3. หรือกด **▶** ที่ toolbar

**F. ตรวจสอบ**

```bash
# รอ ~15 วินาที แล้วตรวจ offset
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server localhost:9092 --topic opc-metrics,opc-datalake
```

**ผ่านเมื่อ:** offset เพิ่มขึ้น (ควรเห็นใน 15–30 วินาที)

---

### Step 3 — ตรวจสอบ Telegraf → InfluxDB

```bash
# Consumer lag (ควร LAG = 0)
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group telegraf-opc-consumer

kubectl logs -n it -l app=telegraf --tail=30
```

InfluxDB UI: `http://10.85.3.104:30086`
```flux
from(bucket: "opc-data")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "opc_metrics")
  |> limit(n: 10)
```

---

### Step 4 — ตรวจสอบ Grafana

```
URL:  http://10.85.3.104:30300
User: admin / Grafana@mintpower2024
```
- Datasource → InfluxDB → Save & Test → green
- Dashboard → เห็น sensor values realtime

---

### Step 5 — Configure NiFi Core → MinIO

```
URL:  https://10.85.3.104:31443/nifi
User: admin / Nifi@mintpower2024!
```

**Flow:** ConsumeKafka(`opc-datalake`) → MergeRecord(batch 100) → PutS3Object(MinIO)

> **หมายเหตุ:** NiFi 2.0.0 standard NARs ไม่มี Parquet writer ในสภาพ airgap — ใช้ **JSON format** แทน Trino อ่านได้เหมือนกัน

**Path ใน MinIO:** `opc-raw/YYYY/MM/DD/<uuid>.json`

---

#### วิธีที่ 1 — REST API Script (แนะนำ)

```bash
bash scripts/setup-nifi-core-flow.sh
```

รอ ~70 วินาที แล้วตรวจสอบ:
```bash
# ไฟล์ใน MinIO
kubectl exec -n it deploy/minio -- mc ls local/opc-raw/ --recursive | head -20

# Consumer lag (ควร LAG ลดลงเรื่อยๆ)
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group nifi-core-consumer
```

---

#### วิธีที่ 2 — NiFi UI (step-by-step)

เปิด `https://10.85.3.104:31443/nifi` → login `admin / Nifi@mintpower2024!`

**A. สร้าง Controller Services (ต้องสร้างก่อน 4 ตัว)**

เปิด Controller Services ระดับ Process Group:
คลิกขวาบน canvas → **Configure** → แท็บ **Controller Services** → กด **+**

| # | ประเภท | ชื่อ | Properties สำคัญ |
|---|--------|------|-----------------|
| 1 | `Kafka3ConnectionService` | KafkaConnectionService-Core | `bootstrap.servers` = `kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092` |
| 2 | `JsonTreeReader` | JsonTreeReader | `schema-access-strategy` = `infer-schema` |
| 3 | `JsonRecordSetWriter` | JsonRecordSetWriter | `schema-access-strategy` = `inherit-record-schema`, `output-grouping` = `output-array` |
| 4 | `AWSCredentialsProviderControllerService` | MinIO-Credentials | `Access Key` = `minioadmin`, `Secret Key` = `Minio@mintpower2024` |

หลังสร้างครบ 4 ตัว → คลิกไอคอน **▶ (enable)** ทีละตัวจนสถานะเป็น **Enabled**

**B. สร้าง Processor: ConsumeKafka**

1. ลาก Processor ลง canvas → ค้นหา `ConsumeKafka` → **Add**
2. Double-click → **Properties**:
   - `Kafka Connection Service` = `KafkaConnectionService-Core`
   - `Topics` = `opc-datalake`
   - `Group ID` = `nifi-core-consumer`
   - `auto.offset.reset` = `earliest`
   - `Output Strategy` = `USE_VALUE`
3. **Relationships** → Auto-terminate `parse.failure` → **Apply**

**C. สร้าง Processor: MergeRecord**

1. ลาก Processor → ค้นหา `MergeRecord` → **Add**
2. Double-click → **Properties**:
   - `Record Reader` = `JsonTreeReader`
   - `Record Writer` = `JsonRecordSetWriter`
   - `merge-strategy` = `Bin-Packing Algorithm`
   - `min-records` = `100`
   - `max-records` = `1000`
   - `max-bin-age` = `60 sec`
3. **Relationships** → Auto-terminate `original` และ `failure` → **Apply**

**D. สร้าง Processor: PutS3Object**

1. ลาก Processor → ค้นหา `PutS3Object` → **Add**
2. Double-click → **Properties**:
   - `AWS Credentials Provider service` = `MinIO-Credentials`
   - `Bucket` = `opc-raw`
   - `Object Key` = `${now():format('yyyy')}/${now():format('MM')}/${now():format('dd')}/${uuid}.json`
   - `Region` = `us-east-1`
   - `Endpoint Override URL` = `http://minio.it.svc.cluster.local:9000`
   - `use-path-style-access` = `true`
   - `Content Type` = `application/json`
3. **Relationships** → Auto-terminate `success` และ `failure` → **Apply**

**E. เชื่อม Connection**

1. วางเมาส์เหนือ `ConsumeKafka` → ลาก arrow ไป `MergeRecord` → เลือก `success` → **Add**
2. วางเมาส์เหนือ `MergeRecord` → ลาก arrow ไป `PutS3Object` → เลือก `merged` → **Add**

**F. Start**

กด **Ctrl+A** → คลิกขวา → **Start**

**G. ตรวจสอบ**

```bash
# รอ ~70 วินาที แล้วดูไฟล์ใน MinIO
kubectl exec -n it deploy/minio -- mc ls local/opc-raw/ --recursive | head -20
```

---

### Step 6 — ตรวจสอบ Trino ✅

```
URL: http://10.85.3.104:30800  (ไม่มี auth)
```

**Setup ที่ทำแล้ว:**
- Schema: `minio.opc`
- Table: `minio.opc.sensor_data` (partitioned by year/month/day)
- Format: NDJSON, path: `s3://opc-raw/data/year=YYYY/month=MM/day=DD/`

**เพิ่ม partition เมื่อขึ้นวันใหม่:**
```bash
kubectl exec -n it deploy/trino -- trino --execute "
CALL minio.system.sync_partition_metadata(
  schema_name => 'opc',
  table_name  => 'sensor_data',
  mode        => 'ADD'
);
"
```

**Query ตัวอย่าง:**
```sql
-- นับ records ต่อวัน
SELECT year, month, day, COUNT(*) AS records
FROM minio.opc.sensor_data
GROUP BY year, month, day;

-- sensor values ล่าสุด
SELECT "timestamp",
  ROUND(readings."Temp_Boiler1"."value", 2)  AS temp_boiler1_c,
  ROUND(readings."Press_Line1"."value", 3)   AS press_bar,
  ROUND(readings."Flow_Main"."value", 1)     AS flow_lpm,
  ROUND(readings."RPM_Motor1"."value", 0)    AS rpm
FROM minio.opc.sensor_data
ORDER BY "timestamp" DESC
LIMIT 10;

-- aggregate stats
SELECT
  ROUND(AVG(readings."Temp_Boiler1"."value"), 2) AS avg_temp1_c,
  ROUND(MAX(readings."Temp_Boiler1"."value"), 2) AS max_temp1_c,
  ROUND(AVG(readings."Flow_Main"."value"), 1)    AS avg_flow_lpm,
  ROUND(AVG(readings."Power_Motor1"."value"), 2) AS avg_power_kw
FROM minio.opc.sensor_data
WHERE year='2026' AND month='05';
```

---

### Step 7 — ตรวจสอบ OpenMAINT ✅ พร้อมแล้ว

```bash
curl http://localhost:30885/cmdbuild/services/rest/v3/boot/status
# → {"success":true,"status":"READY"}
```

```
URL:  http://10.85.3.104:30885/cmdbuild
User: admin / admin
```

---

### ลำดับความสำคัญ

```
1. Step 2 (NiFi Edge flows)        ← ✅ เสร็จแล้ว
2. Step 3+4 (Telegraf/InfluxDB/Grafana) ← ทำได้เดี๋ยวนี้ (opc-metrics ไหลแล้ว)
3. Step 5+6 (NiFi Core/MinIO/Trino) ← configure แยกต่างหาก
4. Step 7 (OpenMAINT)               ← ✅ พร้อมแล้ว
```
