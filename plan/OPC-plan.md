# แผนรองรับ OPC รูปแบบ API และ Pub/Sub

**วันที่:** 2026-05-07  
**อ้างอิง:** ระบบปัจจุบันใช้ OPC UA TCP (`opc.tcp://`) + Eclipse Milo + NiFi Edge

---

## รูปแบบที่รองรับในอนาคต

| รูปแบบ | Protocol | ตัวอย่าง |
|---|---|---|
| **ปัจจุบัน** | OPC UA TCP | `opc.tcp://10.85.3.100:53530/...` |
| **Scenario A** | REST API (HTTP/HTTPS) | GET `/api/v1/tags`, OPC-UA REST Profile |
| **Scenario B** | Pub/Sub via MQTT | MQTT Broker ← OPC Server publish |
| **Scenario C** | Pub/Sub via OPC UA PubSub | OPC UA Part 14, MQTT transport |

---

## สิ่งที่ไม่ต้องเปลี่ยน (Downstream คงเดิม)

Kafka topic `opc-raw-data` เป็น "ชั้นกลาง" — ทุก scenario เปลี่ยนแค่ **ก่อน Kafka** เท่านั้น

```
[OPC Source]  ──►  [Adapter Layer]  ──►  Kafka: opc-raw-data  ──►  Telegraf → InfluxDB
                   (เปลี่ยนตรงนี้)                                   NiFi Core → MinIO
                                                                     Grafana ไม่ต้องแก้
```

**Format ที่ต้องส่งเข้า Kafka คงเดิมเสมอ:**
```json
{
  "timestamp": "2026-05-07T05:00:00.000Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "Temp_Boiler_01": 85.3,
  "Press_Line_01": 120.5,
  "CO2_Zone_01": 412.0
}
```

---

## Scenario A — REST API

### เมื่อไหรควรใช้
- OPC Server ฝั่ง OT มี REST Gateway (เช่น Kepware, Ignition, UA Cloud)
- ระบบ SCADA/MES มี API endpoint ให้ query
- ไม่ต้องการ Eclipse Milo / OPC UA library

### Architecture

```
OT Zone                    DMZ Zone              IT Zone
──────────────────────────────────────────────────────

OPC Server                 ┌──────────┐
หรือ REST Gateway          │  Kafka   │  ──►  (เหมือนเดิม)
     │                     │opc-raw-  │
     │ HTTP GET /tags       │  data    │
     ▼                      │          │
┌──────────────┐            └──────────┘
│  NiFi Edge   │                ▲
│ (InvokeHTTP) │────────────────┘
│ + JoltTransform│
└──────────────┘
```

### NiFi Edge — Processors ที่เปลี่ยน

| เดิม (TCP) | ใหม่ (API) |
|---|---|
| ExecuteScript (Groovy + Milo) | **InvokeHTTP** → JoltTransformJSON → PublishKafka |

**ตัวอย่าง InvokeHTTP config:**
```
HTTP Method    : GET
Remote URL     : http://10.85.3.100:8080/api/v1/tags?device=boiler1
Content-Type   : application/json
Scheduling     : Timer driven, 2 sec

# ถ้ามี auth
Add Header: Authorization = Bearer <token>
Add Header: X-API-Key = <key>
```

**ตัวอย่าง JoltTransformJSON — แปลงผลลัพธ์ให้ flat:**
```json
// Input (ตัวอย่าง API response format)
{
  "tags": [
    {"name": "Temp_Boiler_01", "value": 85.3, "ts": 1746597600000},
    {"name": "Press_Line_01",  "value": 120.5, "ts": 1746597600000}
  ]
}

// Jolt spec (shift array → flat object)
[{
  "operation": "shift",
  "spec": {
    "tags": {
      "*": {
        "value": "@(1,name)"
      }
    }
  }
}]
```

**ถ้า API ส่ง flat JSON อยู่แล้ว** — ไม่ต้อง Jolt ใช้ UpdateAttribute เพิ่ม `source_id` / `device_id` แล้วส่ง Kafka ได้เลย

### ข้อดี / ข้อเสีย

| | |
|---|---|
| ✅ ไม่ต้องใช้ Milo JARs | ❌ ยังเป็น polling (pull) — latency ตาม interval |
| ✅ NiFi processor มาตรฐาน | ❌ ขึ้นกับ uptime ของ API endpoint |
| ✅ รองรับ HTTPS + Auth ได้ง่าย | ❌ ถ้า API paginate ต้องจัดการ cursor |

---

## Scenario B — MQTT Pub/Sub

### เมื่อไหรควรใช้
- OPC Server หรือ Edge Gateway publish ข้อมูลไปยัง MQTT broker
- ต้องการ low latency แบบ event-driven (push แทน poll)
- ใช้งานกับ IoT edge devices ที่รองรับ MQTT

### Architecture

```
OT Zone              DMZ Zone                      IT Zone
──────────────────────────────────────────────────────────

OPC Server           ┌──────────┐   ┌──────────┐
(publish MQTT)  ──►  │  MQTT    │   │  Kafka   │  ──►  (เหมือนเดิม)
                     │ Broker   │   │opc-raw-  │
หรือ                  │(Mosquitto│──►│  data    │
                     │/EMQX)    │   │          │
NiFi Edge            └──────────┘   └──────────┘
(ConsumeMQTT) ────────────────────────────────────►
```

**2 ทางเลือก:**

#### Option B1 — NiFi Edge ConsumeMQTT (แนะนำถ้าต้องการ transform)

เปลี่ยน NiFi Edge flow:
```
ConsumeMQTT → ExecuteScript (flatten) → PublishKafka
```

Config ConsumeMQTT:
```
Broker URI   : tcp://mqtt-broker.dmz:1883
Topic Filter : opc/+/tags   (หรือ factory/line1/# ตาม topic tree)
QoS          : 1
Group ID     : nifi-edge-mqtt
```

#### Option B2 — Telegraf MQTT Consumer → Kafka (ง่ายที่สุด)

ถ้า MQTT payload ส่งมาเป็น flat JSON อยู่แล้ว ใช้ Telegraf แทน NiFi Edge ได้เลย — เพิ่ม input plugin:

```toml
# เพิ่มใน telegraf ConfigMap
[[inputs.mqtt_consumer]]
  servers = ["tcp://mqtt-broker.dmz:1883"]
  topics  = ["opc/+/tags"]
  qos     = 1
  data_format = "json_v2"
  
  [[inputs.mqtt_consumer.json_v2]]
    timestamp_path   = "timestamp"
    timestamp_format = "2006-01-02T15:04:05Z"
    
    [[inputs.mqtt_consumer.json_v2.field]]
      path = "Temp_Boiler_01"
    # ... 307 fields
```

#### Option B3 — Kafka Connect MQTT Source (สำหรับ production scale)

เพิ่ม Kafka Connect worker ใน DMZ:
```yaml
connector.class = io.confluent.connect.mqtt.MqttSourceConnector
mqtt.server.uri = tcp://mqtt-broker.dmz:1883
mqtt.topics     = opc/+/tags
kafka.topic     = opc-raw-data
```

### Components ที่ต้องเพิ่ม

| Component | Namespace | ทำไม |
|---|---|---|
| **MQTT Broker** (Mosquitto / EMQX) | dmz | รับ publish จาก OT, fan-out ให้ consumers |
| MQTT ← OPC bridge | ot/edge | ถ้า OPC Server ไม่รองรับ MQTT โดยตรง ใช้ Node-RED หรือ Unified Namespace gateway |

**MQTT Broker manifest ตัวอย่าง (Mosquitto):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mqtt-broker
  namespace: dmz
spec:
  template:
    spec:
      containers:
      - name: mosquitto
        image: eclipse-mosquitto:2.0
        ports:
        - containerPort: 1883   # MQTT
        - containerPort: 9001   # WebSocket
```

### MQTT Topic Design

```
factory/
  line1/
    boiler/
      Temp_Boiler_01
      Temp_Boiler_02
  coolant/
    Flow_Coolant_01
  ...

# หรือ flat per device
opc/mintserver-prosys/tags    ← publish ทุก 307 tags ใน message เดียว (แนะนำ)
```

### ข้อดี / ข้อเสีย

| | |
|---|---|
| ✅ Push model — latency ต่ำ (< 100ms) | ❌ ต้องเพิ่ม MQTT broker (component ใหม่) |
| ✅ OPC Server ส่งเฉพาะตอนค่าเปลี่ยน (on-change) | ❌ ต้องมี OPC→MQTT bridge ถ้า server ไม่รองรับ |
| ✅ QoS 1/2 การันตี delivery | ❌ topic design สำคัญ — ออกแบบผิดแก้ยาก |
| ✅ รองรับ device หลายพัน node | ❌ MQTT ไม่มี schema — format ต้อง enforce เอง |

---

## Scenario C — OPC UA PubSub (Part 14)

### เมื่อไหรควรใช้
- OPC Server รุ่นใหม่รองรับ OPC UA PubSub (Prosys, Kepware >= 6.14, Ignition >= 8.1)
- ต้องการ OPC standard ครบ — type system, security, address space
- MQTT transport ใต้ OPC UA protocol

### Architecture

```
OT Zone                        DMZ Zone
────────────────────────────────────────────────────

OPC UA Server           ┌─────────────┐
(PubSub enabled)  ──►   │ MQTT Broker │
MQTT Publisher          │  (EMQX)     │──► Kafka opc-raw-data
                        │             │    (via Kafka Connect
                        └─────────────┘     MQTT Source)
```

**OPC UA PubSub Message Format (UADP / JSON Network Message):**
```json
{
  "MessageId": "...",
  "PublisherId": "mintserver-prosys",
  "Messages": [{
    "DataSetWriterId": 1,
    "Payload": {
      "Temp_Boiler_01": {"Value": 85.3, "SourceTimestamp": "2026-05-07T05:00:00Z"},
      "Press_Line_01":  {"Value": 120.5, "SourceTimestamp": "2026-05-07T05:00:00Z"}
    }
  }]
}
```

**ต้องมี transform เพิ่ม** — แปลง OPC UA JSON Network Message → flat format ก่อนเข้า Kafka:

```groovy
// ExecuteScript ใน NiFi หรือ SMT ใน Kafka Connect
payload.Messages[0].Payload.each { tagName, tagData ->
    flat[tagName] = tagData.Value
}
flat.timestamp = payload.Messages[0].Payload.values()[0].SourceTimestamp
```

### ข้อดี / ข้อเสีย

| | |
|---|---|
| ✅ OPC UA standard ครบ — security, type | ❌ ซับซ้อนกว่า plain MQTT |
| ✅ ไม่ต้อง bridge — server publish โดยตรง | ❌ OPC Server ต้องรองรับ Part 14 |
| ✅ รองรับ Dataset / WriterGroup | ❌ JSON Network Message ต้อง parse ก่อน |

---

## สรุปเปรียบเทียบ 4 รูปแบบ

| | TCP (ปัจจุบัน) | REST API | MQTT Pub/Sub | OPC UA PubSub |
|---|---|---|---|---|
| **Model** | Pull (poll) | Pull (poll) | Push | Push |
| **Latency** | 2s (interval) | 2s+ | < 100ms | < 100ms |
| **OT ต้องเปลี่ยน** | ไม่ | ต้องมี REST GW | ต้องมี MQTT GW | Server ต้อง Part 14 |
| **Component เพิ่ม** | ไม่ | ไม่ | MQTT broker | MQTT broker |
| **NiFi แก้ไข** | ไม่ | InvokeHTTP | ConsumeMQTT | ConsumeMQTT + transform |
| **Downstream แก้** | ไม่ | ไม่ | ไม่ | ไม่ |
| **ความซับซ้อน** | กลาง | ต่ำ | กลาง | สูง |
| **แนะนำเมื่อ** | — | OT มี API แล้ว | Scale > 1 device | OPC Server รุ่นใหม่ |

---

## แผน Migration (ไม่กระทบระบบที่รันอยู่)

### ขั้นตอนสำหรับทุก Scenario

```
1. ทดสอบ adapter ใหม่ใน branch/test flow ก่อน
2. ส่งข้อมูลเข้า topic ทดสอบ: opc-raw-data-test
3. ตรวจ format ด้วย AKHQ ว่า flat JSON ถูกต้อง
4. Switch consumer groups ไป topic จริง
5. ปิด flow เดิม (ExecuteScript TCP) หลังยืนยัน
```

### สำหรับ Scenario B (MQTT) — ขั้นตอนเพิ่ม

```bash
# 1. Deploy MQTT broker ใน DMZ
kubectl apply -f manifests/mqtt/mosquitto.yaml

# 2. ทดสอบ subscribe ด้วย mosquitto_sub
kubectl exec -n dmz <mqtt-pod> -- \
  mosquitto_sub -h localhost -t "opc/+/tags" -v

# 3. เพิ่ม ConsumeMQTT processor ใน NiFi Edge
#    ผ่าน NiFi UI: https://localhost:31444/nifi

# 4. ตรวจ Kafka topic
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic opc-raw-data-test \
  --from-beginning --max-messages 3
```

---

## สิ่งที่ไม่ต้องแก้ไม่ว่า Scenario ไหน

- Kafka topic `opc-raw-data` และ retention
- Telegraf ConfigMap และ consumer group
- NiFi Core flows (MinIO, opc-datalake)
- InfluxDB bucket / org / measurement
- Grafana dashboard
- Trino external table
- OpenMAINT
