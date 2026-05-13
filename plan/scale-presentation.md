# Scale-Up Plan — Industrial IoT Data Platform
**Server Capacity Planning: 100 → 1,000 → 10,000 tag/s**

---

## ตัวเลข Throughput

> **tag/s** = จำนวน tag-value ที่ระบบรับได้ต่อวินาที  
> **Peak** = กรณี sensor ทุกตัวเปลี่ยนค่าพร้อมกัน (process upset, alarm cascade)  
> ระบบต้องรองรับ peak โดยไม่ drop data

| | **100 tag/s** | **1,000 tag/s** | **10,000 tag/s** |
|---|---|---|---|
| Normal throughput | 100 tag/s | 1,000 tag/s | 10,000 tag/s |
| **Peak throughput (3× burst)** | **300 tag/s** | **3,000 tag/s** | **30,000 tag/s** |
| ตัวอย่าง scenario | 100 tags × 1s | 1,000 tags × 1s | 10,000 tags × 1s |
| Message size (avg) | ~2.2 KB/msg | ~22 KB/msg | ~221 KB/msg |
| Data rate (normal) | ~2.2 KB/s | ~22 KB/s | ~220 KB/s |
| Data rate (peak) | ~6.6 KB/s | ~66 KB/s | ~660 KB/s |
| **InfluxDB/วัน** | ~190 MB | ~1.9 GB | ~19 GB |
| **InfluxDB / 90 วัน** | ~17 GB | ~170 GB | ~1.7 TB → ~340 GB* |
| **MinIO/ปี (JSON)** | ~68 GB | ~680 GB | ~6.8 TB |
| **MinIO/ปี (Parquet ZSTD)** | ~8.5 GB | ~85 GB | ~850 GB |

*InfluxDB TSM compression ~5:1

---

## ภาพรวม 3 ระดับ

| | **ระดับ 1 · 100 tag/s** | **ระดับ 2 · 1,000 tag/s** | **ระดับ 3 · 10,000 tag/s** |
|---|---|---|---|
| OPC Transport | Polling / REST | Polling 1s | Subscription (push on change) |
| NiFi Edge JVM | 2 GB | 4 GB | 8 GB |
| Kafka brokers | 1 | 1 | 3 |
| Kafka partitions | 3 | 6 | 12 |
| Kafka retention | 7 วัน | 7 วัน | 7 วัน |
| Telegraf replicas | 1 | 2 | 3 |
| InfluxDB RAM | 2 GB | 4 GB | 8 GB |
| InfluxDB storage | 50 GB | 200 GB | 400 GB |
| InfluxDB retention | 90 วัน | 90 วัน | 90 วัน |
| MinIO storage | NVMe 100 GB | NVMe 1 TB | NAS/HDD 6 TB+ |
| MinIO format | JSON | JSON | Parquet (ZSTD) |
| MinIO retention | 5 ปี | 5 ปี | 5 ปี |
| k3s topology | Single-node | Single-node | 3 nodes (HA) |
| Server RAM | 16 GB | 32 GB | 64 GB |
| **งบประมาณ** | **0 บาท** | **~15,000–30,000 บาท** | **~130,000–260,000 บาท** |
| **เวลา deploy** | **1 วัน** | **1–2 สัปดาห์** | **3–5 เดือน** |

---

## ระดับ 1 — 100 tag/s

### ลักษณะระบบ
- รับได้ 100 tag-value ต่อวินาที (normal), 300 tag/s (peak 3×)
- ตัวอย่าง: OPC server 100 tags poll ทุก 1s หรือ 200 tags poll ทุก 2s
- ทำงานบน single-node k3s ได้สบาย ไม่ต้องซื้อ hardware เพิ่ม

### Storage 5 ปี

| Layer | Size/ปี | รวม 5 ปี |
|---|---|---|
| InfluxDB (90 วัน หมุนเวียน) | ~17 GB | **17 GB** (คงที่) |
| MinIO JSON | ~68 GB | ~340 GB |
| MinIO Parquet | ~8.5 GB | **~42 GB** |

### Spec ที่แนะนำ

| ทรัพยากร | Minimum | แนะนำ |
|---|---|---|
| CPU | 4 cores | 8 cores |
| RAM | 16 GB | 16 GB |
| NVMe | 500 GB | 1 TB |
| Network | 100 Mbps | 1 Gbps |

### Peak Load Design
- Kafka 3 partitions รองรับ peak 300 tag/s (data rate ~6.6 KB/s) ได้สบาย
- InfluxDB write cache 512 MB รองรับ burst ~75 วินาที
- Telegraf flush 10s — ไม่ lag ที่ peak

### Config สำคัญ
```yaml
NiFi Edge JVM:     2 GB
Kafka partitions:  3
message.max.bytes: 1048576    # 1 MB
InfluxDB RAM:      2 GB
InfluxDB cache:    512 MB
Telegraf replicas: 1
```

---

## ระดับ 2 — 1,000 tag/s

### ลักษณะระบบ
- รับได้ 1,000 tag-value ต่อวินาที (normal), 3,000 tag/s (peak 3×)
- ตัวอย่าง: OPC server 1,000 tags poll ทุก 1s หรือ 500 tags poll ทุก 0.5s
- Data rate peak: ~66 KB/s → Kafka buffer ต้องใหญ่พอ

### Storage 5 ปี

| Layer | Size/ปี | รวม 5 ปี |
|---|---|---|
| InfluxDB (90 วัน หมุนเวียน) | ~170 GB | **170 GB** (คงที่) |
| MinIO JSON | ~680 GB | ~3.4 TB |
| MinIO Parquet | ~85 GB | **~425 GB** |

### Spec ที่แนะนำ

| ทรัพยากร | Minimum | แนะนำ |
|---|---|---|
| CPU | 8 cores | 16 cores |
| RAM | 24 GB | 32 GB |
| NVMe | 1 TB | 2 TB |
| Network | 1 Gbps | 1 Gbps |

### Peak Load Design
- Kafka 6 partitions ดูดซับ peak 3,000 tag/s ในคิว
- Telegraf 2 replicas: ถ้า 1 ตัวตาย consumer group rebalance ทันที
- InfluxDB write cache 1 GB รองรับ burst ~45 วินาที

### Config สำคัญ
```yaml
NiFi Edge JVM:     4 GB
Kafka partitions:  6
message.max.bytes: 5242880    # 5 MB
InfluxDB RAM:      4 GB
InfluxDB cache:    1 GB
Telegraf replicas: 2
```

### สิ่งที่ต้องซื้อเพิ่ม
| รายการ | Spec | ราคา (โดยประมาณ) |
|---|---|---|
| RAM upgrade | 16 GB DDR4 | 2,000–5,000 บาท |
| NVMe เพิ่ม | 1 TB | 2,000–4,000 บาท |

---

## ระดับ 3 — 10,000 tag/s

### ลักษณะระบบ
- รับได้ 10,000 tag-value ต่อวินาที (normal), 30,000 tag/s (peak 3×)
- Data rate peak: ~660 KB/s → ต้องการ OPC UA Subscription, Kafka 3 brokers, NAS แยก
- InfluxDB 90 วัน: ~340 GB (หลัง TSM compression 5:1)

### Storage 5 ปี

| Layer | Size/ปี | รวม 5 ปี |
|---|---|---|
| InfluxDB (90 วัน หมุนเวียน) | ~340 GB | **340 GB** (คงที่) |
| MinIO JSON | ~6.8 TB | ~34 TB ❌ |
| **MinIO Parquet ZSTD** | **~850 GB** | **~4.25 TB** ✅ |

→ **ต้องเปลี่ยนเป็น Parquet** มิฉะนั้น MinIO เต็มใน 1 ปี

### Spec ที่แนะนำ

| ทรัพยากร | Minimum | แนะนำ |
|---|---|---|
| CPU (รวม 3 nodes) | 24 cores | 48 cores |
| RAM (รวม 3 nodes) | 48 GB | 96 GB |
| NVMe ต่อ node | 1 TB | 2 TB |
| NAS (MinIO) | 6 TB | 10 TB |
| Network | 1 Gbps | 10 Gbps |

### Peak Load Design
- OPC Subscription: push เฉพาะ tag ที่เปลี่ยน → ลด traffic 60–80% ที่ normal load
- Worst case peak: ทุก tag เปลี่ยนพร้อมกัน = 30,000 tag/s = ~660 KB/s
- Kafka 3 brokers × 12 partitions + `min.insync.replicas=2` → ไม่สูญข้อมูลถ้า broker ตาย 1 ตัว
- InfluxDB write cache 2 GB + 4 concurrent compactions รองรับ burst
- Telegraf 3 replicas × 4 partitions = parallel consume

### เปลี่ยน OPC Polling → Subscription
```groovy
// tools/opc_reader_final.groovy
def subscription = client.getSubscriptionManager()
    .createSubscription(500.0)        // publishingInterval 500ms
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

### MinIO: JSON → Parquet ZSTD

| Format | MinIO/ปี | MinIO 5 ปี | Trino query 1 วัน |
|---|---|---|---|
| JSON | ~6.8 TB | ~34 TB ❌ | ช้า (full scan) |
| Parquet ZSTD | ~850 GB | ~4.25 TB ✅ | เร็ว (column pruning) |

ประหยัด storage **87%**

### Config สำคัญ
```yaml
NiFi Edge JVM:          8 GB
Kafka brokers:          3
Kafka partitions:       12
min.insync.replicas:    2
compression.type:       lz4
message.max.bytes:      5242880    # 5 MB
InfluxDB RAM:           8 GB
InfluxDB cache:         2 GB
InfluxDB compactions:   4
Telegraf replicas:      3
```

### งบประมาณ
| รายการ | Spec | ราคา (โดยประมาณ) |
|---|---|---|
| NAS | 6–8 TB usable, NFS v4.1 | 30,000–80,000 บาท |
| RAM upgrade | 32 GB ECC × 2 | 6,000–10,000 บาท |
| Worker nodes | i7/i9, 32 GB, 1 TB NVMe × 2 เครื่อง | 80,000–150,000 บาท |
| **รวม** | | **~116,000–240,000 บาท** |

---

## Roadmap

```
เดือน 1    ระดับ 1 (100 tag/s)    — deploy ทันที ไม่ใช้งบ
เดือน 2    จัดซื้อ RAM + NVMe
เดือน 3    ระดับ 2 (1,000 tag/s)  — scale config + hardware minor
เดือน 4    จัดซื้อ NAS + Worker nodes
เดือน 5    ระดับ 3 setup          — Kafka 3 brokers, NAS mount, Parquet
เดือน 6    ระดับ 3 (10,000 tag/s) — load test 30,000 tag/s peak + failover
```

---

## ความเสี่ยงและการป้องกัน

| ความเสี่ยง | ระดับ | ผลกระทบ | วิธีป้องกัน |
|---|---|---|---|
| Peak burst ทะลุ Kafka buffer | 1–2 | data drop | monitor consumer lag + alert |
| OPC Subscription overflow | 3 | NiFi crash | ทดสอบ batch ทีละ 1,000 tags |
| NAS network bottleneck | 3 | MinIO write ช้า | NVMe local cache + 10GbE |
| InfluxDB OOM ที่ peak | 2–3 | data loss | alert RAM > 80% |
| Kafka single-broker fail | 1–2 | data loss | upgrade 3 brokers (ระดับ 3) |
| MinIO เต็มใน < 1 ปี | 3 (JSON) | system crash | **บังคับใช้ Parquet** |
| Parquet schema change | 3 | NiFi flow หยุด | NiFi Schema Registry |
