# k3s Airgap Data Platform

ระบบ **Industrial IoT Data Platform** แบบ Single-node บน k3s ที่ทำงานในสภาพแวดล้อม **Airgap** (ไม่มีอินเทอร์เน็ต) รับข้อมูลจากอุปกรณ์ OT/OPC-UA แล้วส่งผ่าน pipeline ไปยัง Time-series Database, Data Lake, SQL Analytics และระบบ Asset Management

**สร้าง:** 2026-05-03 · **อัปเดตล่าสุด:** 2026-05-07  
**Platform:** Linux Mint 22.3 · k3s v1.31.4+k3s1 · Single-node

---

## สถาปัตยกรรม

ระบบแบ่งเป็น 3 Zone โดยมี Kafka เป็น message bus กลาง

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 OT ZONE              DMZ ZONE (ns: dmz)       IT ZONE (ns: it)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 Prosys OPC UA                                 ┌─────────────────────┐
 Simulation Server    ┌───────────┐            │ Path 1: Real-time   │
 (307 tags, 2s)       │           │  Telegraf ─►│ InfluxDB ──► Grafana│
        │             │   Kafka   │            └─────────────────────┘
        ▼             │ (KRaft,   │
 ┌────────────┐       │  3 topics)│  ┌──────────────────────────────┐
 │ NiFi Edge  │──────►│           │  │ Path 2: Data Lake            │
 │(Groovy +   │       │           │  │ NiFi Core ──► MinIO ──► Trino│
 │ Milo 0.6)  │       │           │  └──────────────────────────────┘
 └────────────┘       └───────────┘
        │                  │       ┌──────────────────────────────┐
        │              AKHQ│       │ Path 3: Asset Management     │
        │              (UI)│       │ OpenMAINT + PostgreSQL 15    │
        │                  │       └──────────────────────────────┘
        │
 opc.tcp://<OPC_SERVER_IP>:53530                   Traefik Ingress
                                               (*.mintpower.local)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Tech Stack

| Component | Version | บทบาท |
|---|---|---|
| **k3s** | v1.31.4 | Kubernetes distribution (single-node) |
| **Apache Kafka** | 3.x (Strimzi 0.43.0) | Message broker, KRaft mode (no Zookeeper) |
| **AKHQ** | latest | Kafka Web UI |
| **Apache NiFi Edge** | 2.0.0 | OPC UA → Kafka (Eclipse Milo 0.6.12) |
| **Apache NiFi Core** | 2.0.0 | Kafka → MinIO ETL |
| **Telegraf** | 1.32.3 | Kafka → InfluxDB metrics collector |
| **InfluxDB** | 2.7 | Time-series database |
| **Grafana** | 11.x | Real-time dashboard |
| **MinIO** | latest | S3-compatible object storage |
| **Trino** | 463 | Distributed SQL (query MinIO) |
| **OpenMAINT** | CMDBuild 3.4.1-d | CMMS / Asset management |
| **PostgreSQL** | 15-alpine | Database backend สำหรับ OpenMAINT |
| **Traefik** | v3 | Ingress controller |

---

## ข้อกำหนดระบบ

### Hardware
- CPU: 4+ cores
- RAM: 16+ GB
- Storage: NVMe 469 GB+ (mount ที่ `/mnt/nvme-storage/`)
- Network: เชื่อมต่อกับ OT Zone ได้ (หรือใช้ simulator)

### Software
- OS: Linux (Ubuntu 22.04 / Linux Mint 22.x)
- `k3s` (airgap install)
- `kubectl`, `helm` v3
- Container images (เตรียมเป็น `.tar` ไว้ล่วงหน้า)

### OPC UA Source
- Prosys OPC UA Simulation Server (หรือ OPC-UA server จริง)
- Endpoint: `opc.tcp://<host>:53530/OPCUA/SimulationServer`
- Tags: 307 tags (Temp, Press, Flow, CO2, Vibration, Power, ...)

---

## โครงสร้างโปรเจกต์

```
k3s/
├── manifests/
│   ├── phase1/          # Namespace, StorageClass, PersistentVolumes
│   ├── phase2/          # Kafka (Strimzi), AKHQ
│   ├── phase3/          # InfluxDB, Telegraf, Grafana
│   ├── phase4/          # MinIO, NiFi Core, Trino
│   ├── phase5/          # NiFi Edge, OpenMAINT, PostgreSQL
│   └── phase6/          # Traefik Ingress
├── tools/
│   ├── opc_reader_final.groovy   # Groovy script (Eclipse Milo, deploy ใน NiFi Edge)
│   ├── opc_reader.groovy         # ต้นฉบับ
│   ├── deploy_opc_script.py      # Deploy script ไปยัง NiFi Edge REST API
│   ├── gen_300tags.py            # Generator สำหรับ 307 tag definitions
│   └── browse_opc.py             # OPC UA browser tool
├── scripts/
│   ├── setup-nifi-core-flow.sh   # Configure NiFi Core flows via REST API
│   └── telegraf-cpu-analysis.md  # วิเคราะห์ CPU throttling
├── opc-sim/
│   ├── opc_server.py             # Python OPC UA simulator (12 tags, เดิม)
│   └── opc-simulator.service     # systemd service สำหรับ simulator
├── update/                       # บันทึกการอัปเดต phase ต่างๆ
├── plan/
│   ├── plan.md                   # Operational runbook
│   └── OPC-api.md                # แผนรองรับ OPC แบบ REST API / MQTT
├── SUMMARY.md                    # สรุปโปรเจกต์ฉบับสมบูรณ์
└── concept.png                   # ภาพ architecture
```

---

## การ Deploy

> ⚠️ **ก่อน Deploy:** แก้ไขค่า `CHANGE_ME` ใน secret YAML ทุกไฟล์ก่อน  
> (`manifests/phase3/influxdb-secret.yaml`, `manifests/phase4/minio-secret.yaml`, `manifests/phase5/openmaint-secret.yaml`)

### Phase 1 — Infrastructure

```bash
# สร้าง namespace, StorageClass, PersistentVolumes
kubectl apply -f manifests/phase1/
```

**PersistentVolumes บน** `/mnt/nvme-storage/k8s-pv/`:

| PV | ขนาด | ใช้โดย |
|---|---|---|
| pv-kafka | 50Gi | Kafka |
| pv-influxdb2 | 50Gi | InfluxDB |
| pv-minio | 100Gi | MinIO |
| pv-nifi-core | 20Gi | NiFi Core |
| pv-nifi-edge | 10Gi | NiFi Edge |
| pv-grafana | 10Gi | Grafana |
| pv-openmaint | 20Gi | PostgreSQL + OpenMAINT |
| pv-trino | 20Gi | Trino |

---

### Phase 2 — Message Broker (Kafka)

```bash
# Load Strimzi operator images (airgap)
sudo k3s ctr images import install/strimzi-images.tar

# Install Strimzi operator
kubectl apply -f install/strimzi-0.43.0/install/cluster-operator/ -n dmz

# Deploy Kafka cluster + topics + AKHQ
kubectl apply -f manifests/phase2/

# รอ Kafka ready (~2 นาที)
kubectl wait pod -n dmz -l strimzi.io/name=kafka-cluster-kafka \
  --for=condition=Ready --timeout=180s
```

**Kafka Topics:**

| Topic | Retention | Consumer |
|---|---|---|
| `opc-raw-data` | 7 วัน | Telegraf, NiFi Core |
| `opc-metrics` | 1 วัน | (legacy) |
| `opc-datalake` | 30 วัน | (legacy) |

---

### Phase 3 — Monitoring Stack

```bash
# Load images (airgap)
sudo k3s ctr images import install/influxdb-image.tar
sudo k3s ctr images import install/grafana-image.tar
sudo k3s ctr images import install/telegraf-image.tar

# Deploy InfluxDB, Telegraf, Grafana
kubectl apply -f manifests/phase3/
```

**Telegraf data flow:**
```
Kafka (opc-raw-data) ──► Telegraf ──► InfluxDB
                                       org: mintpower-org
                                       bucket: opc-data
                                       measurement: opc_data
                                       fields: 307 tags
```

---

### Phase 4 — Data Platform (MinIO + NiFi Core + Trino)

```bash
# Load images (airgap)
sudo k3s ctr images import install/minio-images.tar
sudo k3s ctr images import install/nifi-image.tar
sudo k3s ctr images import install/trino-image.tar

# Deploy
kubectl apply -f manifests/phase4/

# Configure NiFi Core flows (ConsumeKafka → MergeRecord → PutS3Object)
bash scripts/setup-nifi-core-flow.sh
```

**MinIO data path:**
```
Kafka (opc-raw-data) ──► NiFi Core ──► MinIO bucket: opc-raw
                         MergeRecord     path: data/year=YYYY/month=MM/day=DD/{uuid}.json
                         (batch 100)
```

**Trino partitioned table:**
```sql
-- ดู data ใน MinIO ผ่าน SQL
SELECT year, month, day, COUNT(*) AS records
FROM minio.opc.sensor_data
GROUP BY year, month, day
ORDER BY year, month, day;

-- sensor values ล่าสุด
SELECT timestamp, Temp_Boiler_01, Press_Line_01, Flow_Main_01
FROM minio.opc.sensor_data
ORDER BY timestamp DESC
LIMIT 10;
```

---

### Phase 5 — Edge Collector + Asset Management

```bash
# Load images (airgap)
sudo k3s ctr images import install/nifi-image.tar
sudo k3s ctr images import install/openmaint-images.tar
sudo k3s ctr images import install/postgres-image.tar

# Deploy NiFi Edge + OpenMAINT + PostgreSQL
kubectl apply -f manifests/phase5/
```

**NiFi Edge — OPC UA Groovy script:**

NiFi Edge ใช้ ExecuteGroovyScript + Eclipse Milo 0.6.12 อ่านข้อมูลจาก OPC-UA ทุก 2 วินาที

```groovy
// endpoint ใน tools/opc_reader_final.groovy
static final String OPC_ENDPOINT = "opc.tcp://<OPC_SERVER_IP>:53530/OPCUA/SimulationServer"
```

**Deploy script ไปยัง NiFi Edge:**
```bash
python3 tools/deploy_opc_script.py
```

**OpenMAINT setup (ดูหัวข้อ "Known Issues" สำหรับรายละเอียด):**
1. รอ PostgreSQL ready
2. รัน pg_restore โหลด demo.dump
3. สร้าง PostGIS stub functions ใน database
4. รอ OpenMAINT boot (~5 นาที)

```bash
# ตรวจสถานะ OpenMAINT
curl http://localhost:30885/cmdbuild/services/rest/v3/boot/status
# {"success":true,"status":"READY"}
```

---

### Phase 6 — Ingress & Routing

```bash
# ติดตั้ง Traefik ผ่าน Helm
helm upgrade --install traefik traefik/traefik \
  -f manifests/phase6/traefik-values.yaml \
  -n traefik --create-namespace

# Deploy Ingress rules
kubectl apply -f manifests/phase6/
```

**เพิ่ม DNS records ใน `/etc/hosts` (หรือ DNS server):**
```
<node-ip>   grafana.mintpower.local
<node-ip>   influxdb.mintpower.local
<node-ip>   minio.mintpower.local
<node-ip>   nifi-core.mintpower.local
<node-ip>   nifi-edge.mintpower.local
<node-ip>   openmaint.mintpower.local
<node-ip>   akhq.mintpower.local
<node-ip>   trino.mintpower.local
```

---

## Access Points

| Service | NodePort | Ingress | Namespace |
|---|---|---|---|
| **Grafana** | `:30300` | grafana.mintpower.local | it |
| **InfluxDB** | `:30086` | influxdb.mintpower.local | it |
| **MinIO Console** | `:30901` | minio.mintpower.local | it |
| **NiFi Core** | `:31443` (HTTPS) | nifi-core.mintpower.local | it |
| **NiFi Edge** | `:31444` (HTTPS) | nifi-edge.mintpower.local | it |
| **OpenMAINT** | `:30885` | openmaint.mintpower.local | it |
| **Trino** | `:30800` | trino.mintpower.local | it |
| **AKHQ** | `:30880` | akhq.mintpower.local | dmz |
| **Kafka (external)** | `:32092` | — | dmz |

> Credentials: ดูใน `SUMMARY.md` (lab environment) หรือตั้งค่าใน secret YAML files

---

## OPC UA Data Format

JSON ที่ NiFi Edge ส่งเข้า Kafka `opc-raw-data` (flat format):

```json
{
  "timestamp": "2026-05-07T05:00:00.000Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tag_count": 307,
  "bad_count": 0,
  "Temp_Boiler_01": 85.3,
  "Temp_Boiler_02": 87.1,
  "Press_Line_01": 120.5,
  "Flow_Main_01": 45.2,
  "CO2_Zone_01": 412.0,
  "Vibration_Pump_01": 0.023
}
```

**307 Tags ครอบคลุม:**

| กลุ่ม | Tags | จำนวน |
|---|---|---|
| Temperature | Boiler (×20), HeatEx (×10), Cooling, Oil, Ambient | 34 |
| Pressure | Line (×10), Hydraulic, Tank | 12 |
| Flow | Main, Branch (×5), Coolant | 7 |
| CO2 | Zone (×10) | 10 |
| Current | Drive (×20) | 20 |
| Power / Voltage / RPM | Motor (×5 each) | 15 |
| Vibration | Pump (×5) | 5 |
| Level | Tank (×5) | 5 |
| Humidity | Room (×5) | 5 |
| Misc | Counter, Random, Sawtooth, Constant, bad_count, tag_count | 6+ |

---

## Known Issues & Workarounds

### OpenMAINT (CMDBuild 3.4.1-d) — 7 ปัญหาที่แก้แล้ว

OpenMAINT เป็น component ที่ต้องใช้เวลา debug มากที่สุด บันทึกไว้เผื่อ redeploy

#### 1. POSTGRES_HOST ผิด → CrashLoopBackOff
```yaml
# manifests/phase5/openmaint.yaml
- name: POSTGRES_HOST
  value: "postgres-openmaint"   # ต้องเป็นชื่อ K8s service
```

#### 2. CMDBUILD_DUMP ไม่มีใน image → exit ทันที
```yaml
- name: CMDBUILD_DUMP
  value: "demo.dump.xz"   # ชื่อ dump จริงใน image
```

#### 3. PostgreSQL version ไม่เข้ากัน → pg_restore error
ต้องใช้ `postgres:15-alpine` — image เดิม `itmicus/cmdbuild:db-3.0` (PG10) ไม่รองรับ syntax ของ dump

#### 4. Data เก่า PG10 ค้างบน PVC → postgres ไม่ start
```bash
kubectl run cleanup --image=busybox -n it --restart=Never \
  --overrides='{"spec":{"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"pvc-openmaint"}}],"containers":[{"name":"c","image":"busybox","command":["sh","-c","rm -rf /data/postgres && mkdir -p /data/postgres"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}]}}'
```

#### 5. PostGIS ไม่มีใน postgres:15-alpine → restore error
สร้าง stub control file ชั่วคราวใน container filesystem:
```bash
PGPOD=$(kubectl get pods -n it -l app=postgres-openmaint -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n it $PGPOD -- sh -c "
  EXTDIR=\$(pg_config --sharedir)/extension
  printf 'default_version = '\''3.3.3'\''\nrelocatable = true\n' > \$EXTDIR/postgis.control
  printf '-- stub\n' > \$EXTDIR/postgis--3.3.3.sql
"
```

#### 6. โหลด Database — ใช้ pg_restore โดยตรง (ไม่ผ่าน Java)
```bash
# copy dump เข้า container แล้ว restore โดยตรง
kubectl exec -n it $PGPOD -- pg_restore \
  --host=localhost --username=postgres --dbname=openmaint \
  --no-exit-on-error --verbose /tmp/demo.dump
# ผลลัพธ์: 710+ tables loaded
```

#### 7. Container Restart Loop — Root Cause หลัก ⚠️
**สาเหตุ:** CMDBuild ทำ full Tomcat stop→start ตอน first boot (load JDBC driver)  
เมื่อ `exec catalina.sh run` เป็น PID 1 → Tomcat stop → container exit → K8s restart loop

**Fix:** override command ให้ bash เป็น PID 1 แทน (บันทึกใน `manifests/phase5/openmaint.yaml`):
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

**PostGIS stub functions (persistent — ต้องสร้างหลัง restore ทุกครั้ง):**
```bash
kubectl exec -n it $PGPOD -- psql -U postgres -d openmaint \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_lib_version() RETURNS text LANGUAGE sql AS \$\$ SELECT '3.3.3'::text; \$\$;" \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_version() RETURNS text LANGUAGE sql AS \$\$ SELECT '3.3.3 USE_GEOS=1 USE_PROJ=1 USE_STATS=1'::text; \$\$;" \
  -c "CREATE OR REPLACE FUNCTION gis.postgis_full_version() RETURNS text LANGUAGE sql AS \$\$ SELECT 'POSTGIS=\"3.3.3\" PGSQL=\"150\"'::text; \$\$;"
```

> **Note:** CMDBuild log ไม่แสดงผ่าน `kubectl logs` — ต้องอ่านจากใน container:
> ```bash
> kubectl exec -n it <openmaint-pod> -- tail -f /usr/local/tomcat/logs/cmdbuild.log
> ```

---

### NiFi Edge — Eclipse Milo Issues

| ปัญหา | สาเหตุ | วิธีแก้ |
|---|---|---|
| `NoClassDefFoundError: Preconditions` | Guava JAR หายไป | copy `guava-33.3.1-jre.jar` → `/opt/nifi/nifi-current/data/milo-jars/` |
| `UnknownHostException: mintserver` | Prosys advertise hostname ไม่ resolve ได้ | เพิ่ม `hostAliases` ใน nifi-edge deployment |
| Flow หาย หลัง pod restart | `flow.json.gz` อยู่นอก PVC mount path | ใช้ `scripts/setup-nifi-core-flow.sh` recreate ได้ |
| PublishKafka: transactions error | NiFi 2.0 default `Transactions Enabled=true` | ตั้ง `Transactions Enabled=false` |

---

### Telegraf CPU Throttling

Telegraf ใช้ CPU สูงเกินไปตอนแรก — แก้แล้วด้วย:
- CPU limit: `500m` → `1000m`
- Flush interval: `10s` → `30s`
- Kafka offset: `oldest` → `newest`

ดูรายละเอียด: `scripts/telegraf-cpu-analysis.md`

---

## Health Check

```bash
# 1. ทุก pod ควร Running, 0 restarts
kubectl get pods -A --no-headers | awk '{print $1,$2,$3,$4,$5}'

# 2. Kafka consumer lag
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --all-groups 2>/dev/null

# 3. InfluxDB รับข้อมูลอยู่ไหม
kubectl exec -n it $(kubectl get pods -n it -l app=influxdb -o jsonpath='{.items[0].metadata.name}') -- \
  sh -c 'influx query --token CHANGE_ME --org mintpower-org \
  "from(bucket:\"opc-data\") |> range(start:-5m) |> filter(fn:(r)=>r[\"_field\"]==\"Temp_Boiler_01\") |> count()"'

# 4. MinIO ไฟล์วันนี้
TODAY=$(date +%d); MONTH=$(date +%m)
kubectl exec -n it $(kubectl get pods -n it -l app=minio -o jsonpath='{.items[0].metadata.name}') -- \
  mc ls local/opc-raw/data/year=2026/month=${MONTH}/day=${TODAY}/ | wc -l

# 5. OpenMAINT
curl -s http://localhost:30885/cmdbuild/services/rest/v3/boot/status
```

**Kafka lag เกณฑ์ปกติ:**

| Consumer Group | ปกติ | ต้องตรวจสอบ |
|---|---|---|
| `telegraf-opc-consumer` | < 10 | > 1,000 |
| `nifi-core-consumer` | < 10 | > 1,000 |
| `nifi-edge-consumer` | stale (no active consumer) | ถ้ามี consumer + lag > 10,000 |

---

## Restart ลำดับที่ถูกต้อง

```bash
# 1. Kafka ก่อน
kubectl rollout restart statefulset/kafka-cluster-broker -n dmz
kubectl wait pod -n dmz -l strimzi.io/name=kafka-cluster-kafka \
  --for=condition=Ready --timeout=120s

# 2. Producer (NiFi Edge)
kubectl rollout restart deployment/nifi-edge -n it

# 3. Consumers (หลัง Kafka ready)
kubectl rollout restart deployment/telegraf -n it
kubectl rollout restart deployment/nifi-core -n it
```

---

## Prosys OPC UA Service (mintserver)

Prosys ใช้ install4j launcher ที่ fork Java แล้ว exit ทันที ทำ systemd ต้องใช้ wrapper script:

**`/usr/local/bin/prosys-start.sh`** บน mintserver:
```bash
#!/bin/bash
cd /home/demo/prosys-opc-ua-simulation-server
/usr/bin/xvfb-run -a ./UaSimulationServer &>/tmp/prosys.log &

for i in $(seq 1 30); do
    JAVA_PID=$(pgrep -f "prosys-opc-ua-simulation-server/jre/bin/java" | head -1)
    [ -n "$JAVA_PID" ] && break
    sleep 1
done

[ -z "$JAVA_PID" ] && exit 1
while kill -0 "$JAVA_PID" 2>/dev/null; do sleep 5; done
```

```bash
sudo systemctl start prosys-opc
sudo systemctl status prosys-opc
# port 53530 ต้องเปิดอยู่
```

---

## แผนอนาคต

- **OPC API / MQTT:** ดู `plan/OPC-api.md` — แผนรองรับ OPC แบบ REST API และ MQTT Pub/Sub
- **NiFi flow persistence:** mount PVC ให้ครอบ `conf/` เพื่อให้ `flow.json.gz` รอดจาก pod restart
- **MQTT Broker:** เพิ่ม Mosquitto/EMQX ใน DMZ สำหรับ IoT edge devices

---

## Security Notes

> ⚠️ ระบบนี้ออกแบบสำหรับ **Lab / Airgap environment** — ยังไม่เหมาะสำหรับ production โดยตรง

ก่อน deploy production:
- เปลี่ยน credentials ทุกตัวจาก default ใน secret YAML files
- เปิด TLS สำหรับ Kafka (ปัจจุบัน PLAINTEXT)
- เปิด authentication สำหรับ Trino และ AKHQ
- เปลี่ยน OpenMAINT default password (`admin/admin`)
- ลบ `pv-influxdb` (Available spare) ถ้าไม่ใช้

---

## ไฟล์อ้างอิง

| ไฟล์ | เนื้อหา |
|---|---|
| `SUMMARY.md` | สรุปโปรเจกต์ฉบับสมบูรณ์ + credentials (lab) + ประวัติการแก้ปัญหา |
| `plan/plan.md` | Operational runbook + incident management |
| `plan/OPC-api.md` | แผนรองรับ OPC รูปแบบ REST API และ MQTT Pub/Sub |
| `update/update-2026-05-06-phase4.md` | บันทึก Eclipse Milo + NiFi Edge issues |
| `update/update-2026-05-06-phase5.md` | บันทึก Prosys systemd + flatten format + Telegraf |
| `concept.png` | ภาพ Architecture overview |
