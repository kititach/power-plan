# แผนรองรับ 10,000 tags/s — k3s Data Platform

**วันที่:** 2026-05-08
**เป้าหมาย:** scale ระบบจาก 307 tags/2s → **10,000 tags/s** (65x)
**Retention:** InfluxDB 3 เดือน, MinIO 5 ปี
**Storage:** InfluxDB บน NVMe (system), MinIO บน NAS/SAN/HDD (แยก)

---

## 1. ตัวเลขสำคัญ

### Throughput

| | ปัจจุบัน | เป้าหมาย |
|---|---|---|
| Tags | 307 / 2s | **10,000 / 1s** |
| Tag-values/s | 154 | **10,000** |
| Message size | 6.8 KB | **221 KB** |
| Messages/วัน | 43,200 | **86,400** |

### Storage Requirements

| Layer | Format | Retention | Total |
|---|---|---|---|
| **MinIO** (cold) | JSON | 5 ปี | **32.5 TB** ❌ ใหญ่เกิน |
| **MinIO** (cold) | Parquet (8:1) | 5 ปี | **4.1 TB** ✅ แนะนำ |
| **InfluxDB** (hot) | TSM compressed | 3 เดือน | **246 GB** |
| **Kafka** (buffer) | LZ4 compressed | 7 วัน | **127.5 GB** |

### Hardware Recommendation

| Disk | Capacity | Type | ใช้กับ |
|---|---|---|---|
| **System NVMe** | 1 TB | SSD | k3s + InfluxDB (320GB) + Kafka (200GB) |
| **NAS / SAN** | 6 TB+ | HDD | MinIO (Parquet, 5 ปี) |
| **RAM** | 64 GB | DDR4/5 | จาก 31GB ปัจจุบัน |

---

## 2. Architecture Diagram

```
OT ZONE                    DMZ ZONE                    IT ZONE
────────────────────────────────────────────────────────────────────

OPC UA Server              Kafka Cluster (3 brokers)
10,000 tags                12 partitions, LZ4
  │                              │
  │ OPC UA Subscription          ├──► Telegraf ×3 ──► InfluxDB
  ▼  (push on change)            │    (parallel)      320GB NVMe
NiFi Edge                        │                    Retention: 90d
JVM: 8GB                         │                    (auto-expire)
                                 │
                                 └──► NiFi Core ──► MinIO (Parquet)
                                      JVM: 8GB     NAS 6TB HDD
                                                   Retention: 5yr
                                                   (mc ilm auto-expire)
                                      └──► Trino (partition sync FULL)
```

---

## 3. Component Changes — รายละเอียดทุก Layer

### 3.1 OPC UA Layer — Polling → Subscription

**ปัญหา:** อ่าน 10,000 tags แบบ sequential ใช้เวลา ~15 วินาที — ไม่ทัน 1s interval

**แก้:** เปลี่ยน Groovy script ใช้ OPC UA Subscription (server push)

```groovy
// ใน /home/mintpower/lab/k3s/tools/opc_reader_final.groovy
// แทน readValues() loop
def subscription = client.getSubscriptionManager()
    .createSubscription(500.0)   // publishingInterval 500ms
    .get()

tags.each { nodeId ->
    subscription.createMonitoredItems(
        TimestampsToReturn.Both,
        [new MonitoredItemCreateRequest(
            new ReadValueId(nodeId, AttributeId.Value, null, null),
            MonitoringMode.Reporting,
            new MonitoringParameters(id++, 1000.0, null, 10, true)
        )]
    )
}
```

**ปรับ NiFi Edge JVM:**
```yaml
# manifests/phase5/nifi-edge.yaml
env:
  - name: NIFI_JVM_HEAP_INIT
    value: "4g"
  - name: NIFI_JVM_HEAP_MAX
    value: "8g"   # จาก 2g
```

**ผล:**
- Server push เฉพาะ tag ที่ค่าเปลี่ยน → ลด traffic 60-80%
- รองรับ tags ได้ไม่จำกัด (ไม่ block จาก polling)

---

### 3.2 Kafka — Scale to 3 Brokers

```yaml
# manifests/phase2/kafka-cluster.yaml
spec:
  kafka:
    replicas: 3                # จาก 1
    storage:
      type: persistent-claim
      size: 200Gi              # ต่อ broker
    config:
      num.partitions: "12"
      message.max.bytes: "5242880"      # 5MB (รองรับ 221KB msg + buffer)
      replica.fetch.max.bytes: "5242880"
      log.retention.hours: "168"        # 7 วัน
      log.segment.bytes: "1073741824"   # 1GB
      compression.type: "lz4"
```

**Topic config:**
```yaml
# manifests/phase2/kafka-topics.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: opc-raw-data
spec:
  partitions: 12               # จาก 3
  replicas: 3                  # จาก 1
  config:
    retention.ms: 604800000
    compression.type: lz4
    max.message.bytes: 5242880
```

**NiFi PublishKafka tuning:**
```
Acks                     = 1     # leader ack เพียงพอ (HA จาก replicas)
Batch Size               = 65536 # 64KB
Linger                   = 100ms
Compression Type         = LZ4
Max Request Size         = 5MB
```

---

### 3.3 InfluxDB — 90-Day Retention + Tuning

**ตั้ง Retention Policy 3 เดือน (ลบเก่าอัตโนมัติ):**

```bash
# รันครั้งเดียว
INFLUX_TOKEN=$(kubectl get secret -n it influxdb-secret -o jsonpath='{.data.admin-token}' | base64 -d)

kubectl exec -n it deployment/influxdb -- \
  influx bucket update \
    --token "$INFLUX_TOKEN" \
    --org mintpower-org \
    --name opc-data \
    --retention 2160h    # 90 days × 24h = 2160h
```

InfluxDB จะลบ shard เก่ากว่า 90 วันโดยอัตโนมัติ — **ไม่ต้องใช้ cron**

**เพิ่ม PV size:**
```yaml
# manifests/phase3/influxdb-pvc.yaml
spec:
  resources:
    requests:
      storage: 320Gi    # จาก 50Gi
```

**InfluxDB tuning สำหรับ throughput สูง:**
```yaml
# manifests/phase3/influxdb-config.yaml
data:
  config.yml: |
    storage-cache-max-memory-size: 2147483648   # 2GB write cache
    storage-max-concurrent-compactions: 4
    storage-compact-throughput-burst: 67108864  # 64MB/s
    storage-shard-precreator-check-interval: 10m
    storage-shard-precreator-advance-period: 30m
```

**RAM:** เพิ่มจาก 127MB → **8GB**

```yaml
# manifests/phase3/influxdb.yaml
resources:
  requests:
    memory: 4Gi
    cpu: "2"
  limits:
    memory: 8Gi
    cpu: "4"
```

**Telegraf — เพิ่ม consumers:**
```yaml
# manifests/phase3/telegraf.yaml
spec:
  replicas: 3   # จาก 1
  # Kafka จะ auto-assign 4 partitions/consumer (12 partitions / 3 consumers)
```

---

### 3.4 MinIO + NAS/SAN — Parquet, 5 ปี

**3.4.1 เปลี่ยน NiFi Core: JSON → Parquet**

```
ปัจจุบัน:  ConsumeKafka → MergeContent → PutS3Object (JSON)
เปลี่ยนเป็น: ConsumeKafka → JsonTreeReader → ParquetRecordSetWriter → PutS3Object
```

**Parquet writer config:**
```
Schema Access Strategy   = Use 'Schema Text' Property
Compression Type         = ZSTD     # ดีกว่า SNAPPY 30%
Block Size               = 134217728  # 128MB
Page Size                = 1048576    # 1MB
Dictionary Page Size     = 1048576
Enable Dictionary Encoding = true
```

**Schema (รองรับ 10,000 tags):**
```json
{
  "type": "record",
  "name": "OpcReading",
  "fields": [
    {"name": "timestamp", "type": "string"},
    {"name": "source_id", "type": "string"},
    {"name": "device_id", "type": "string"},
    {"name": "tag_count", "type": "int"},
    {"name": "bad_count", "type": "int"},
    {"name": "tags", "type": {
      "type": "map",
      "values": "double"
    }}
  ]
}
```

**Path partition (เพิ่ม hour):**
```
data/year=YYYY/month=MM/day=DD/hour=HH/{uuid}.parquet
```

**3.4.2 Mount NAS เป็น NFS PV**

```yaml
# manifests/phase4/minio-nas-pv.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-minio-nas
spec:
  capacity:
    storage: 6Ti
  volumeMode: Filesystem
  accessModes: [ReadWriteMany]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-nas
  nfs:
    server: 192.168.1.100        # NAS IP — เปลี่ยนตามจริง
    path: /export/minio-opc
  mountOptions:
    - hard
    - nfsvers=4.1
    - rsize=1048576              # 1MB read buffer
    - wsize=1048576              # 1MB write buffer
    - timeo=600
    - retrans=2
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-minio
  namespace: it
spec:
  accessModes: [ReadWriteMany]
  storageClassName: nfs-nas
  resources:
    requests:
      storage: 6Ti
```

**ทางเลือก SAN (iSCSI):**
```yaml
spec:
  iscsi:
    targetPortal: 192.168.1.100:3260
    iqn: iqn.2024.local.san:minio
    lun: 0
    fsType: ext4
```

**3.4.3 MinIO config tuning:**
```yaml
# manifests/phase4/minio.yaml
env:
  - name: MINIO_API_REQUESTS_MAX
    value: "1000"
  - name: MINIO_CACHE
    value: "on"
  - name: MINIO_CACHE_DRIVES
    value: "/cache"               # local NVMe cache
  - name: MINIO_CACHE_QUOTA
    value: "80"
volumeMounts:
  - name: data
    mountPath: /data              # NAS
  - name: cache
    mountPath: /cache             # local NVMe
```

---

### 3.5 จัดการไฟล์หมดอายุ — Automated Lifecycle

#### 3.5.1 InfluxDB (3 เดือน)

✅ **Built-in retention** — ตั้งครั้งเดียว ลบอัตโนมัติ

```bash
influx bucket update --name opc-data --retention 2160h
```

ตรวจสอบ:
```bash
influx bucket list --org mintpower-org
# ดู Retention column = 2160h
```

#### 3.5.2 MinIO (5 ปี) — Object Lifecycle Policy

**สร้าง policy file:**
```bash
cat > /tmp/lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "ID": "expire-opc-data-5years",
      "Status": "Enabled",
      "Filter": { "Prefix": "data/" },
      "Expiration": {
        "Days": 1825
      }
    },
    {
      "ID": "delete-incomplete-uploads",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
EOF

# Apply
kubectl cp /tmp/lifecycle.json it/$(kubectl get pod -n it -l app=minio -o jsonpath='{.items[0].metadata.name}'):/tmp/lifecycle.json
kubectl exec -n it deployment/minio -- mc ilm import local/opc-raw < /tmp/lifecycle.json

# ตรวจสอบ
kubectl exec -n it deployment/minio -- mc ilm ls local/opc-raw
```

**MinIO Scanner** จะรันทุกวันและลบ object เก่ากว่า 1,825 วันอัตโนมัติ

#### 3.5.3 Trino — Sync หลัง MinIO ลบ partition

```yaml
# manifests/phase4/trino-partition-sync-cronjob.yaml
spec:
  schedule: "5 0,12 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - command:
                - trino
                - --execute
                - |
                  CALL minio.system.sync_partition_metadata(
                    schema_name => 'opc',
                    table_name  => 'sensor_data',
                    mode        => 'FULL'   -- จาก 'ADD' → 'FULL'
                  );
                  -- FULL = sync ทั้ง add และ remove (ลบ partition ที่ไม่มีไฟล์แล้ว)
```

#### 3.5.4 Kafka — Built-in Retention

✅ ตั้งใน topic config แล้ว — ลบอัตโนมัติทุก 7 วัน

---

### 3.6 OpenMAINT Bridge — ปรับสำหรับ scale

```python
# /home/mintpower/lab/k3s/tools/openmaint_bridge.py

# เปลี่ยนจาก
COOLDOWN_SECONDS = 300       # 5 นาที/tag

# เป็น
COOLDOWN_SECONDS = 900       # 15 นาที/tag (ลด spam)
BATCH_PER_DEVICE = True      # รวม violations ของ device เดียว เป็น work order เดียว
MAX_WO_PER_HOUR = 50         # cap ป้องกัน OpenMAINT overload
```

---

## 4. ขั้นตอนการ Implementation (Phased)

### Phase 1 — ไม่ต้องซื้อ Hardware (ทำได้ทันที)

**เป้าหมาย:** รองรับ 3,000-5,000 tags/s + lifecycle management

| ลำดับ | งาน | Effort |
|---|---|---|
| 1 | ตั้ง InfluxDB retention 90 วัน | 5 นาที |
| 2 | ตั้ง MinIO lifecycle policy 5 ปี | 10 นาที |
| 3 | เปลี่ยน Trino sync `ADD` → `FULL` | 5 นาที |
| 4 | เพิ่ม Kafka partitions 3 → 12 | 30 นาที |
| 5 | เพิ่ม NiFi Edge JVM heap 2g → 8g | 15 นาที |
| 6 | เพิ่ม InfluxDB RAM 1g → 8g | 15 นาที |
| 7 | เพิ่ม Telegraf replicas 1 → 3 | 10 นาที |
| 8 | เปลี่ยน OPC polling → OPC UA Subscription | 4-8 ชม. |

**ผลลัพธ์:** รองรับ ~3,000-5,000 tags/s

---

### Phase 2 — ซื้อ NAS/HDD (ประมาณ 1 เดือน)

**เป้าหมาย:** รองรับ MinIO 5 ปี + Parquet format

| ลำดับ | งาน | Effort |
|---|---|---|
| 9 | จัดหา NAS 6TB+ (NFS หรือ SAN iSCSI) | 1-2 สัปดาห์ |
| 10 | สร้าง NFS PV + migrate MinIO data | 1-2 วัน |
| 11 | เปลี่ยน NiFi Core: JSON → Parquet writer | 1 วัน |
| 12 | ทดสอบ Trino query บน Parquet | 0.5 วัน |
| 13 | ตั้ง MinIO local NVMe cache | 0.5 วัน |

---

### Phase 3 — ซื้อ RAM + Multi-node (ประมาณ 3 เดือน)

**เป้าหมาย:** รองรับ 10,000 tags/s เต็มระบบ + HA

| ลำดับ | งาน | Effort |
|---|---|---|
| 14 | RAM upgrade: 31GB → 64GB | 0.5 วัน |
| 15 | Kafka: 1 broker → 3 brokers | 1-2 วัน |
| 16 | k3s: single-node → multi-node (3 nodes) | 1 สัปดาห์ |
| 17 | ทดสอบ failover scenarios | 2-3 วัน |

---

## 5. Hardware Procurement List

| รายการ | spec | จำนวน | งบประมาณ (โดยประมาณ) |
|---|---|---|---|
| NAS/SAN | 6-8TB usable, NFS v4.1 / iSCSI | 1 unit | 30-80k บาท |
| HDD (ถ้าทำเอง) | 2TB Enterprise × 4 (RAID 10) | 4 ลูก | 16-24k บาท |
| RAM upgrade | DDR4/5 ECC 32GB × 2 | 2 module | 6-10k บาท |
| Worker node (Phase 3) | i7/i9, 32GB RAM, 1TB NVMe | 2 เครื่อง | 80-150k บาท |

---

## 6. Risk & Mitigation

| Risk | ผลกระทบ | Mitigation |
|---|---|---|
| OPC Subscription overflow | server crash ถ้า monitored items มาก | ทดสอบ batch 1,000 ก่อน scale |
| NAS network bottleneck | MinIO write ช้า | ใช้ MinIO local NVMe cache + 10GbE |
| InfluxDB OOM ที่ 90 วัน | data loss | retention policy + alerting disk usage |
| Parquet schema change | NiFi flow break | versioned schema in NiFi registry |
| Kafka split-brain | ข้อมูลซ้ำ/หาย | min.insync.replicas=2 |

---

## 7. Monitoring ที่ต้องเพิ่ม

```yaml
# Grafana dashboards เพิ่มเติม
- Kafka Producer Lag (ต่อ partition)
- InfluxDB Cardinality (ต้อง < 1M)
- MinIO Disk Usage Trend (NAS)
- NiFi Edge OPC Subscription Health
- Trino Query Latency (P95, P99)
```

**Alert rules แนะนำ:**
- InfluxDB disk > 80% → expand PV
- MinIO NAS disk > 80% → ตรวจ lifecycle ทำงาน
- Kafka lag > 100,000 → consumer scale up
- OPC Subscription disconnect → restart NiFi Edge

---

## 8. สรุป

| Aspect | ปัจจุบัน | เป้าหมาย |
|---|---|---|
| Throughput | 154 tag-values/s | **10,000 tag-values/s** (65x) |
| InfluxDB retention | ไม่จำกัด (manual) | **90 วัน auto-expire** |
| MinIO retention | ไม่จำกัด (manual) | **5 ปี auto-expire (Parquet)** |
| Storage strategy | NVMe (system) ทั้งหมด | NVMe (hot) + NAS/SAN (cold) |
| HA | single-node | 3 nodes + Kafka 3 brokers |
| Cost (ประมาณ) | 0 (ใช้เครื่องเดิม) | 130-260k บาท |

**Key insight:**
- **Phase 1** ทำได้ทันทีไม่ใช้งบ → รองรับได้ ~5,000 tags/s + auto-expire
- **Phase 2** ลงทุน NAS → รองรับ retention 5 ปีตามต้องการ
- **Phase 3** scale out จริง → รองรับ 10,000 tags/s + HA

---

## ภาคผนวก — คำสั่งสำคัญ

### Apply changes ตามลำดับ
```bash
# Phase 1
cd /home/mintpower/lab/k3s
kubectl apply -f manifests/phase2/kafka-topics.yaml
kubectl apply -f manifests/phase3/influxdb.yaml
kubectl apply -f manifests/phase5/nifi-edge.yaml

# InfluxDB retention
INFLUX_TOKEN=$(kubectl get secret -n it influxdb-secret -o jsonpath='{.data.admin-token}' | base64 -d)
kubectl exec -n it deployment/influxdb -- \
  influx bucket update --token "$INFLUX_TOKEN" --org mintpower-org \
  --name opc-data --retention 2160h

# MinIO lifecycle
kubectl exec -n it deployment/minio -- mc ilm import local/opc-raw < /tmp/lifecycle.json
```

### ตรวจสอบหลัง deploy
```bash
# Kafka partitions
kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- \
  bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic opc-raw-data

# InfluxDB retention
kubectl exec -n it deployment/influxdb -- influx bucket list --org mintpower-org

# MinIO lifecycle
kubectl exec -n it deployment/minio -- mc ilm ls local/opc-raw

# Trino partition count
kubectl exec -n it deployment/trino -c trino -- trino --server=http://localhost:8080 \
  --execute "SELECT COUNT(DISTINCT (year,month,day)) FROM minio.opc.sensor_data;"
```
