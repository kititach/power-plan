# การวิเคราะห์ปัญหา Telegraf CPU 500m

**วันที่วิเคราะห์:** 2026-05-05 11:30 (UTC+7)  
**อัปเดต:** 2026-05-05 12:55 (UTC+7)  
**สถานะ:** แก้ไขแล้ว — Step 1+2 applied, Step 3 ไม่รองรับใน Telegraf v1.32

---

## อาการ

- Pod `telegraf-765779fd4-x2fzq` ใช้ CPU 500m อย่างต่อเนื่อง (= ติด limit)
- Pod ทำงานมาแล้ว ~29h (started 2026-05-04 06:23 UTC)
- Kafka consumer lag ≈ 1–5 messages ต่อ partition (caught up แล้ว)

---

## ข้อมูลที่เก็บได้

| รายการ | ค่า |
|--------|-----|
| Topic | `opc-metrics` |
| Partitions | 3 |
| Retention | 86400000ms (24h) |
| Consumer group | `telegraf-opc-consumer` |
| Kafka message rate (วัดจริง) | **~14 msg/s รวม 3 partitions** (4.6 msg/s ต่อ partition) |
| Message structure | JSON nested 3 ระดับ: 12 sensors × 3 keys = **36 fields ต่อ message** |
| `offset` setting เดิม | `oldest` |
| `flush_interval` เดิม | 10s |
| `metric_batch_size` เดิม | 1000 |
| CPU limit เดิม | 500m |

---

## Root Cause (อัปเดตจากผลวิเคราะห์จริง)

### ปัญหาหลัก 1: CPU limit ต่ำเกินไป

CPU limit = 500m แต่ workload จริงต้องการ ~500–750m:
- JSON parse nested structure 36 fields × 14 msg/s
- InfluxDB batch writes ทุก 10s
- Pod ถูก throttle → Golang GC pause สะสม → CPU ดูสูงตลอดเวลา

### ปัญหาหลัก 2: flush_interval ถี่เกินไป

- เขียน InfluxDB ทุก 10s = write overhead สูง
- เพิ่ม CPU spike บ่อย

### หมายเหตุ: `offset = "oldest"` ไม่ใช่ root cause จริง

เนื่องจาก consumer group มี committed offsets อยู่แล้ว Kafka client จะใช้ committed offset ไม่ใช่ oldest — การเปลี่ยนเป็น `newest` ดีสำหรับการป้องกันในอนาคต (เมื่อสร้าง group ใหม่) แต่ไม่ได้แก้ CPU ในกรณีนี้

---

## แผนแก้ไข

| Step | การเปลี่ยนแปลง | สถานะ | ผล |
|------|--------------|-------|-----|
| 1 | `offset = "oldest"` → `"newest"` | ✅ Done | ป้องกันอนาคต (ไม่ใช่ root cause) |
| 2a | CPU limit 500m → 1000m | ✅ Done | หยุด throttling |
| 2b | `flush_interval` 10s → 30s, `metric_batch_size` 1000 → 5000 | ✅ Done | ลด write frequency 3x |
| 3 | `max_processing_goroutines = 8` | ❌ N/A | ไม่มีใน Telegraf 1.32 |

---

## การเปลี่ยนแปลงที่ apply แล้ว

### telegraf-config.yaml

```toml
[agent]
  interval = "10s"
  metric_batch_size = 5000    # เพิ่มจาก 1000
  metric_buffer_limit = 50000 # เพิ่มจาก 10000
  flush_interval = "30s"      # เพิ่มจาก "10s"

[[inputs.kafka_consumer]]
  offset = "newest"           # เปลี่ยนจาก "oldest"
```

### telegraf.yaml (Deployment resources)

```yaml
limits:
  cpu: "1.0"   # เพิ่มจาก "0.5"
```

---

## ผลที่วัดได้

| เวลา | CPU | Limit | สถานะ | หมายเหตุ |
|------|-----|-------|-------|---------|
| ก่อนแก้ | 470m | 500m | Throttled | ติด ceiling ตลอดเวลา |
| หลัง Step 1 เท่านั้น | 470m | 500m | Throttled | ไม่เปลี่ยน (root cause ไม่ใช่ offset) |
| หลัง Step 2 (idle) | 514m | 1000m | ✅ ปกติ | ไม่ throttle แล้ว |
| หลัง Step 2 (flush spike) | 757m | 1000m | ✅ ปกติ | spike ระหว่าง batch write 30s |

CPU steady-state จริงอยู่ที่ ~500–760m ซึ่งเป็นผลของ workload 14 msg/s + nested JSON parse

---

## ผลกระทบต่อระบบ

- **Grafana dashboard:** ข้อมูลยังแสดงปกติ — delay เพิ่มจาก 10s → 30s (ยอมรับได้)
- **InfluxDB:** historical data เดิมอยู่ครบ ไม่สูญหาย
- **เมื่อ restart ในอนาคต:** จะขาด data ช่วง downtime แต่ catch real-time ทันทีหลัง pod ขึ้น

---

## การปรับปรุงเพิ่มเติม (future)

**ลด fields ที่ไม่จำเป็น** — ตอนนี้ Telegraf parse ทุก field รวมถึง `_unit` และ `_name` ซึ่ง Grafana ไม่ได้ใช้:

```toml
[[inputs.kafka_consumer]]
  fieldpass = ["readings_*_value"]  # เก็บแค่ _value, ตัด _unit, _name ออก
```

คาดว่าจะลด CPU ได้ ~30–40% เพราะลด fields จาก 36 → 12 ต่อ message
