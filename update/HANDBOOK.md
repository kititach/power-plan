# คู่มือฉบับสมบูรณ์: K3s Airgap Industrial Data Platform

> **สำหรับผู้อ่านที่เริ่มต้นจากศูนย์** — ไม่ต้องมีความรู้ด้าน Kubernetes, Docker, หรือ Industrial IoT มาก่อน  
> อ่านตามลำดับตั้งแต่หัวข้อแรก แต่ละส่วนจะอธิบายพื้นฐานก่อนเสมอ

---

## สารบัญ

1. [ภาพรวม: Project นี้คืออะไร?](#1-ภาพรวม)
2. [พื้นฐาน Container และ Kubernetes](#2-พื้นฐาน-container-และ-kubernetes)
3. [K3s และ Airgap คืออะไร?](#3-k3s-และ-airgap)
4. [สถาปัตยกรรมระบบ (Architecture)](#4-สถาปัตยกรรมระบบ)
5. [OPC UA: ภาษากลางของโรงงาน](#5-opc-ua)
6. [Apache Kafka: ระบบส่งข้อความความเร็วสูง](#6-apache-kafka)
7. [Apache NiFi: ท่อส่งข้อมูล](#7-apache-nifi)
8. [Telegraf: ตัวรับข้อมูลแบบ Agent](#8-telegraf)
9. [InfluxDB: ฐานข้อมูล Time-Series](#9-influxdb)
10. [Grafana: Dashboard และ Visualization](#10-grafana)
11. [MinIO: Object Storage (คลังเก็บไฟล์)](#11-minio)
12. [Trino: SQL Query Engine](#12-trino)
13. [OpenMAINT: ระบบจัดการ Asset (CMDB)](#13-openmaint)
14. [การไหลของข้อมูลตั้งแต่ต้นจนจบ](#14-data-flow)
15. [โครงสร้างไฟล์ Project](#15-โครงสร้างไฟล์)
16. [การ Deploy ทีละ Phase](#16-การ-deploy)
17. [URL และ Port ทั้งหมด](#17-url-และ-port)
18. [การ Troubleshoot ปัญหาพื้นฐาน](#18-troubleshoot)
19. [Storage และ Persistence](#19-storage)
20. [Security และ Zone Architecture](#20-security)

---

## 1. ภาพรวม

### Project นี้คืออะไร?

Project นี้คือ **แพลตฟอร์มรับและวิเคราะห์ข้อมูลจากเครื่องจักรในโรงงาน** ที่ทำงานได้ **โดยไม่ต้องต่ออินเทอร์เน็ต** (Airgap)

ลองนึกภาพโรงงานที่มีเครื่องจักรหลายร้อยเครื่อง แต่ละเครื่องมีเซ็นเซอร์วัดอุณหภูมิ ความดัน การสั่นสะเทือน ฯลฯ ทุก ๆ 2 วินาที เราต้องการ:

- **เก็บข้อมูล** จากเซ็นเซอร์ทุกตัวแบบ real-time
- **แสดงผล** เป็น Dashboard ให้วิศวกรดู
- **เก็บไว้ระยะยาว** เพื่อวิเคราะห์ย้อนหลัง
- **จัดการ Asset** ว่าเครื่องไหนอยู่ตรงไหน รับผิดชอบโดยใคร
- **ทำได้ทั้งหมดในเครื่อง Server เดียว** โดยไม่ต้องพึ่ง Cloud

```
เครื่องจักรโรงงาน
(OPC UA Simulator)
        │
        │ ส่งข้อมูล 307 Tags ทุก 2 วินาที
        ▼
  [NiFi Edge]  ← อ่านข้อมูล แปลงรูปแบบ
        │
        │ ส่งเข้า Message Bus
        ▼
    [Kafka]    ← รับข้อมูลชั่วคราว กระจายต่อ
       / \
      /   \
     ▼     ▼
[Telegraf] [NiFi Core]
     │           │
     ▼           ▼
[InfluxDB]   [MinIO]  ← เก็บระยะยาว
     │           │
     ▼           ▼
[Grafana]    [Trino]  ← SQL Query
```

### ตัวเลขหลักของระบบ

| รายการ | ค่า |
|--------|-----|
| จำนวน Tag/เซ็นเซอร์ | 307 tags |
| ความถี่การส่งข้อมูล | ทุก 2 วินาที |
| Server | 1 เครื่อง (mintpower) |
| Storage | NVMe 280 GB รวมทุก service |
| Environment | Airgap (ไม่มีอินเทอร์เน็ต) |

---

## 2. พื้นฐาน Container และ Kubernetes

### Container คืออะไร?

**Container** คือกล่องที่บรรจุโปรแกรมพร้อมทุกอย่างที่จำเป็น (library, config) เพื่อให้ทำงานได้เองโดยไม่กระทบโปรแกรมอื่นในเครื่อง

เปรียบเทียบ:
- **โปรแกรมปกติ** = ปลูกต้นไม้ลงดินโดยตรง ถ้าดินไม่ดีก็ตาย
- **Container** = ปลูกต้นไม้ในกระถาง เอาไปวางที่ไหนก็ได้ มีดินของตัวเอง

Docker สร้าง Container จาก **Image** (เหมือน template) แต่ละ Container แยกกันทำงาน

### Kubernetes คืออะไร?

**Kubernetes (K8s)** คือระบบ **จัดการ Container หลายตัว** พร้อมกัน

สิ่งที่ Kubernetes ทำแทนเรา:
- **รีสตาร์ท Container** ที่ crash อัตโนมัติ
- **จัดสรร Resource** (CPU/Memory) ให้แต่ละ Container
- **สร้าง Network** ให้ Container คุยกันได้
- **จัดการ Storage** เก็บข้อมูลถาวรแม้ Container ดับ

### Kubernetes Objects ที่ต้องรู้

| Object | คืออะไร | เปรียบได้กับ |
|--------|---------|-------------|
| **Pod** | Container 1 ชุดที่ทำงานอยู่ | กระถางต้นไม้ |
| **Deployment** | สูตรสำหรับสร้าง Pod | พิมพ์เขียวกระถาง |
| **Service** | ช่องทางเข้าถึง Pod จากภายนอก | ที่อยู่ไปรษณีย์ |
| **ConfigMap** | ไฟล์ config ที่แยกออกจาก Image | คู่มือการใช้งาน |
| **Secret** | Config ที่เป็นความลับ (password) | ตู้นิรภัย |
| **PersistentVolume (PV)** | พื้นที่เก็บข้อมูลถาวร | ฮาร์ดดิสก์ |
| **PersistentVolumeClaim (PVC)** | การจองพื้นที่เก็บข้อมูล | สัญญาเช่า |
| **Namespace** | กลุ่ม/โซน สำหรับแยก Service | ชั้น/แผนกในอาคาร |
| **CronJob** | งานที่รันตามตาราง | Task Scheduler |
| **Ingress** | ตัวแจกงาน HTTP จาก domain ต่าง ๆ | Front desk / Receptionist |

### ตัวอย่าง YAML

ไฟล์ YAML ใน Kubernetes บอก "ฉันต้องการ" (Desired State) ตัวอย่าง:

```yaml
apiVersion: apps/v1
kind: Deployment          # ประเภท Object
metadata:
  name: grafana           # ชื่อ
  namespace: it           # อยู่ใน namespace ชื่อ it
spec:
  replicas: 1             # ต้องการ 1 Pod
  template:
    spec:
      containers:
        - name: grafana
          image: grafana/grafana:11.0.0  # ใช้ Image นี้
          ports:
            - containerPort: 3000        # เปิด Port 3000
```

---

## 3. K3s และ Airgap

### K3s คืออะไร?

**K3s** คือ Kubernetes เวอร์ชันเบา (Lightweight) ที่ Rancher Labs สร้าง ออกแบบมาเพื่อ:
- ทำงานบนเครื่องเดียว (Single Node)
- ใช้ RAM น้อยกว่า Kubernetes ปกติ 50%+
- ติดตั้งง่ายกว่า: ไฟล์เดียว binary เดียว
- เหมาะกับ Edge Computing / โรงงาน

### Airgap คืออะไร?

**Airgap** = ระบบที่ **ไม่มีการเชื่อมต่ออินเทอร์เน็ต** โดยสิ้นเชิง

ทำไมโรงงานถึง Airgap?
- ป้องกัน Hacker เข้ามาควบคุมเครื่องจักร
- ข้อกำหนดด้านความปลอดภัยอุตสาหกรรม (IEC 62443)
- ข้อมูล Production ไม่ควรออกสู่ภายนอก

ผลที่ตามมาคือ: **ต้องเอา Docker Image ทุกตัวมาจากภายนอกก่อน** แล้วบรรจุใส่เครื่องล่วงหน้า

```
ภายนอก (Online) → บันทึก Image ลง .tar → ถ่าย File เข้าเครื่อง → โหลด Image → Deploy
```

ไฟล์ Image ที่เตรียมไว้อยู่ที่ `/home/mintpower/lab/k3s/install/`:
```
grafana-image.tar        ← Grafana
influxdb-image.tar       ← InfluxDB
minio-images.tar         ← MinIO
nifi-image.tar           ← Apache NiFi
akhq-image.tar           ← Kafka UI
postgres-image.tar       ← PostgreSQL
openmaint-images.tar     ← OpenMAINT
k3s-airgap-images-amd64.tar.gz  ← K3s system images
```

---

## 4. สถาปัตยกรรมระบบ

### Single Node Cluster

ระบบนี้ทำงานบน **เครื่องเดียว** ชื่อ `mintpower` แต่ Kubernetes ยังคงทำงานปกติ (ต่างจาก Production cluster ที่มีหลายเครื่อง)

```
┌─────────────────────────────────────────┐
│           mintpower (Server)            │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │         k3s (Kubernetes)         │   │
│  │                                  │   │
│  │  ┌──────────┐  ┌──────────────┐  │   │
│  │  │Namespace │  │  Namespace   │  │   │
│  │  │   dmz    │  │     it       │  │   │
│  │  │          │  │              │  │   │
│  │  │  Kafka   │  │  NiFi Edge   │  │   │
│  │  │  AKHQ    │  │  NiFi Core   │  │   │
│  │  │  Strimzi │  │  Telegraf    │  │   │
│  │  └──────────┘  │  InfluxDB    │  │   │
│  │                │  Grafana     │  │   │
│  │                │  MinIO       │  │   │
│  │                │  Trino       │  │   │
│  │                │  OpenMAINT   │  │   │
│  │                └──────────────┘  │   │
│  └──────────────────────────────────┘   │
│                                         │
│  /mnt/nvme-storage/k8s-pv/  (280 GB)   │
└─────────────────────────────────────────┘
```

### Zone Architecture: DMZ vs IT

ระบบแบ่งออกเป็น **2 Zone** ตามหลักความปลอดภัย:

| Zone | Namespace | มีอะไร | เข้าถึงจาก |
|------|-----------|--------|-----------|
| **DMZ** (Demilitarized Zone) | `dmz` | Kafka, AKHQ, Strimzi | OPC Devices ภายนอกผ่านได้ |
| **IT Zone** | `it` | ทุกอย่างที่เหลือ | เฉพาะ Internal |

**ทำไมต้องแยก?**  
DMZ เปรียบเสมือน "ล็อบบี้" ที่อุปกรณ์ภายนอก (OPC UA) เข้ามาส่งข้อมูลได้ แต่เข้าถึง IT Zone ซึ่งมีฐานข้อมูลและระบบหลักไม่ได้โดยตรง

---

## 5. OPC UA

### OPC UA คืออะไร?

**OPC Unified Architecture (OPC UA)** คือ **มาตรฐานการสื่อสาร** ระหว่างเครื่องจักรในโรงงาน (IEC 62541) เหมือน HTTP ของ Web แต่ใช้ในโลก Industrial

ก่อนมี OPC UA: เครื่องจักรแต่ละยี่ห้อ (Siemens, Rockwell, Mitsubishi) ใช้ Protocol ที่ต่างกัน วุ่นวายมาก

หลังมี OPC UA: เครื่องทุกยี่ห้อที่รองรับ OPC UA คุยกันได้ด้วยภาษาเดียวกัน

### แนวคิด Node และ Tag

ใน OPC UA ข้อมูลจัดเรียงเป็น **Address Space** (เหมือนแผนผังโฟลเดอร์)

```
Server
└── Objects
    └── Simulation (Namespace 3)
        ├── Counter      [NodeId: ns=3;i=1001]  ← ค่านับ
        ├── Temperature
        │   ├── Temp_Boiler_01  [ns=3;i=2001]  ← อุณหภูมิหม้อต้ม 1
        │   ├── Temp_Boiler_02  [ns=3;i=2002]
        │   └── ...
        └── Pressure
            ├── Press_Line_01   [ns=3;i=2031]
            └── ...
```

แต่ละ Node มี:
- **NodeId** = ที่อยู่ (ns=3 คือ Namespace 3, i=2001 คือ Index 2001)
- **Value** = ค่าปัจจุบัน (เช่น 85.3 องศา)
- **StatusCode** = บอกว่าค่านี้น่าเชื่อถือไหม (Good/Bad)
- **Timestamp** = เวลาที่อ่านค่า

### Prosys OPC UA Simulator

ในระบบนี้ใช้ **Prosys OPC UA Simulation Server** บนเครื่อง `mintserver` เพื่อจำลองข้อมูลโรงงาน 307 Tags:

| กลุ่ม | Tags | ตัวอย่าง |
|-------|------|---------|
| Temp_Boiler | 20 | อุณหภูมิหม้อต้ม |
| Temp_HeatEx | 10 | อุณหภูมิ Heat Exchanger |
| Temp_Ambient | 10 | อุณหภูมิห้อง |
| Temp_Oil | 10 | อุณหภูมิน้ำมัน |
| Temp_Cooling | 10 | อุณหภูมิน้ำหล่อเย็น |
| Press_Line | 20 | ความดันท่อ |
| Press_Tank | 10 | ความดันถัง |
| Press_Hydraulic | 10 | ความดันไฮดรอลิก |
| Flow_Main | 15 | อัตราการไหลหลัก |
| Flow_Branch | 15 | อัตราการไหลสาขา |
| Flow_Coolant | 10 | อัตราการไหลน้ำหล่อเย็น |
| Level_Tank | 20 | ระดับในถัง |
| Vibration_Pump | 20 | การสั่นสะเทือนปั๊ม |
| Power_Motor | 20 | กำลังไฟมอเตอร์ |
| RPM_Motor | 20 | รอบต่อนาทีมอเตอร์ |
| Current_Drive | 20 | กระแสไฟ Drive |
| Voltage_Bus | 10 | แรงดันบัส |
| Torque_Motor | 20 | แรงบิดมอเตอร์ |
| Humidity_Room | 10 | ความชื้นในห้อง |
| Noise_Floor | 10 | Noise พื้น |
| CO2_Zone | 10 | ปริมาณ CO₂ |
| Control tags | 7 | Counter, Random, Sinusoid, ... |

### Protocol: opc.tcp://

การเชื่อมต่อ OPC UA ใช้ TCP port 53530:
```
opc.tcp://<mintserver_IP>:53530/OPCUA/SimulationServer
```

โปรแกรมที่อ่านค่าคือ Groovy Script ใน NiFi Edge (`tools/opc_reader_final.groovy`) ใช้ Library **Eclipse Milo** ซึ่งเป็น Java OPC UA Client ยอดนิยม

---

## 6. Apache Kafka

### Kafka คืออะไร?

**Apache Kafka** คือ **ระบบส่งข้อความแบบ Publish-Subscribe** ความเร็วสูง

ลองนึกภาพ **กระดานหนังสือพิมพ์**:
- **Producer** = คนเขียนข่าว (NiFi Edge ส่งข้อมูล OPC)
- **Topic** = หมวดข่าว (เช่น หน้าเศรษฐกิจ, หน้าการเมือง)
- **Consumer** = ผู้อ่านที่สมัคร subscribe (Telegraf, NiFi Core)
- **Broker** = กองบรรณาธิการที่เก็บและแจกหนังสือพิมพ์

ข้อดีของ Kafka:
1. **Decoupling** = Producer ไม่ต้องรู้ว่าใคร consume ข้อมูล
2. **Buffer** = ถ้า Consumer ช้า ข้อมูลไม่หาย (เก็บไว้ใน Topic)
3. **Multiple Consumers** = Consumer หลายตัวอ่าน Topic เดียวกันได้
4. **Replay** = อ่านข้อมูลย้อนหลังได้ (Topic เก็บไว้ตาม retention)

### Kafka Topics ในระบบนี้

| Topic | ใครส่ง (Producer) | ใครรับ (Consumer) | เก็บนานแค่ไหน |
|-------|--------|--------|--------------|
| `opc-raw-data` | NiFi Edge | Telegraf, NiFi Core | 7 วัน |
| `opc-metrics` | (legacy ไม่ใช้แล้ว) | - | 1 วัน |
| `opc-datalake` | (legacy ไม่ใช้แล้ว) | - | 30 วัน |

> ตั้งแต่ Phase 5 ทั้ง Telegraf และ NiFi Core consume จาก `opc-raw-data` topic เดียวกัน

### Consumer Groups ในระบบ

**Consumer Group** คือชื่อกลุ่ม (string) ที่ Consumer ลงทะเบียนกับ Kafka เพื่อแบ่งงานกัน ชื่อนี้ไม่ได้ผูกกับ Pod ใด ๆ — ใครก็ได้ที่ตั้ง `group.id` ตรงกันคือกลุ่มเดียวกัน

| Consumer Group | Consumer | Destination | สถานะ |
|----------------|----------|-------------|-------|
| `nifi-core-consumer` | NiFi Core | MinIO (Data Lake) | ✅ Active |
| `telegraf-opc-consumer` | Telegraf | InfluxDB | ✅ Active |

> **บทเรียน (2026-05-07):** พบ consumer group ชื่อ `nifi-edge-consumer` ที่มี lag 65,694 messages แต่ไม่มี active member เลย — ตรวจสอบพบว่าถูกสร้างโดย ConsumeKafka processor ใน NiFi Edge deployment เก่า (2026-05-04) ก่อนที่จะ redeploy เมื่อ 2026-05-06 โดย flow ใหม่ไม่มี processor นั้น ทำให้กลายเป็น **orphan consumer group** ที่ค้างอยู่ใน Kafka ได้ถูกลบออกแล้ว

### Partition คืออะไร?

แต่ละ Topic แบ่งเป็น **Partition** (ช่องทาง) เพื่อให้ Consumer หลายตัวอ่านพร้อมกันได้

```
Topic: opc-raw-data (3 Partitions)
┌─────────────────────────────────────────┐
│ Partition 0: [msg1][msg4][msg7]...       │
│ Partition 1: [msg2][msg5][msg8]...       │
│ Partition 2: [msg3][msg6][msg9]...       │
└─────────────────────────────────────────┘
```

### Strimzi Operator

**Strimzi** คือ Kubernetes Operator ที่ช่วยจัดการ Kafka บน Kubernetes

แทนที่จะต้องตั้งค่า Kafka ด้วยตัวเอง เราแค่เขียน YAML:
```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: kafka-cluster
```
แล้ว Strimzi จะสร้าง Kafka Cluster ให้อัตโนมัติ

### KRaft Mode (ไม่มี Zookeeper)

Kafka เดิมต้องใช้ **ZooKeeper** เป็น Coordinator แยกต่างหาก Kafka 3.7+ ใช้ **KRaft** (Kafka Raft) แทน ซึ่ง Broker จัดการ Metadata เองได้ ลด Component ที่ต้องดูแล

### AKHQ

**AKHQ** (Akhq Kafka HQ) คือ Web UI สำหรับดูสถานะ Kafka:
- ดู Topics ทั้งหมด
- ดู Messages ใน Topic
- ดู Consumer Groups (ใครกำลัง consume อยู่บ้าง)
- ดู Lag (Consumer ตามไม่ทันแค่ไหน)

---

## 7. Apache NiFi

### NiFi คืออะไร?

**Apache NiFi** คือ **ระบบ Data Flow แบบ Visual** สร้างท่อส่งข้อมูลโดยลาก-วาง (Drag and Drop) บน Web UI

เปรียบเทียบ: NiFi เหมือน **LEGO ท่อน้ำ** — มีชิ้นส่วน (Processor) สำหรับ:
- **อ่านข้อมูล** (ExecuteScript, ConsumeKafka)
- **แปลงข้อมูล** (JoltTransformJSON, UpdateAttribute)
- **ส่งข้อมูล** (PublishKafka, PutS3Object)
- **แยกข้อมูล** (RouteOnAttribute)

### FlowFile คืออะไร?

ข้อมูลที่ไหลผ่าน NiFi เรียกว่า **FlowFile** ซึ่งประกอบด้วย:
- **Content** = ข้อมูลจริง (JSON string)
- **Attributes** = Metadata (เช่น `mime.type=application/json`, `filename=data.json`)

### NiFi Edge vs NiFi Core

ในระบบนี้มี NiFi **สองตัว** ทำหน้าที่ต่างกัน:

| | NiFi Edge | NiFi Core |
|---|---|---|
| **ชื่อ Pod** | `nifi-edge` | `nifi-core` |
| **NodePort** | 31444 | 31443 |
| **บทบาท Kafka** | **Producer เท่านั้น** — ส่งข้อมูลเข้า Kafka | **Consumer** — รับจาก Kafka แล้วเก็บลง MinIO |
| **หน้าที่** | อ่าน OPC UA → PublishKafka (`opc-raw-data`) | ConsumeKafka → MergeRecord → PutS3Object |
| **Groovy Script** | `opc_reader_final.groovy` | - |
| **Kafka Group ID** | ไม่มี (producer ไม่มี group) | `nifi-core-consumer` |
| **Memory** | 2GB | 4GB |

> **สำคัญ:** NiFi Edge เป็น **producer เท่านั้น** — ไม่มี ConsumeKafka processor ในระบบปัจจุบัน ชื่อ "nifi-edge" ในชื่อ consumer group ไม่ได้หมายความว่า NiFi Edge pod เป็นผู้ consume

**ทำไมต้องแยก 2 ตัว?**  
Edge Layer ควรเบาและอยู่ใกล้แหล่งข้อมูล Core Layer ทำงานหนักกว่า (batch, write to storage) แยกกันเพื่อ Scale อิสระและ Fault Isolation

### Flow ใน NiFi Edge

```
[ExecuteGroovyScript]
  opc_reader_final.groovy
  → อ่าน 307 tags จาก OPC UA Server ทุก 2 วินาที
  → สร้าง JSON FlowFile
        │
        ▼
[PublishKafka]
  topic: opc-raw-data
  → ส่งเข้า Kafka
```

### Flow ใน NiFi Core

```
[ConsumeKafka]
  topic: opc-raw-data
  → รับ message ทีละ batch
        │
        ▼
[MergeRecord]
  batch size: 100 records
  → รวม 100 messages เป็นไฟล์เดียว
        │
        ▼
[PutS3Object]
  bucket: opc-raw
  path: data/year={YYYY}/month={MM}/day={DD}/{uuid}.json
  → อัปโหลดไปยัง MinIO
```

### รูปแบบ JSON ที่ส่งเข้า Kafka

ข้อมูลที่ NiFi Edge ส่งเข้า Kafka มีรูปแบบ **Flat JSON**:

```json
{
  "timestamp": "2026-05-07T10:30:00.123456789Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tag_count": 307,
  "bad_count": 0,
  "Temp_Boiler_01": 85.3,
  "Temp_Boiler_02": 86.1,
  "Press_Line_01": 4.2,
  "Press_Line_02": 4.1,
  "Vibration_Pump_01": 0.023,
  "RPM_Motor_01": 1450.0,
  ...ทุก tag อยู่ที่ระดับ top-level...
}
```

> **Flat vs Nested:** ข้อมูลถูก "แผ่" (flatten) ให้ tag ทุกตัวอยู่ที่ระดับเดียวกัน ไม่ใช่ซ้อนกันใน object ทำให้ Telegraf parse ง่ายกว่า

---

## 8. Telegraf

### Telegraf คืออะไร?

**Telegraf** คือ **Agent เก็บ Metrics** จาก InfluxData ทำงานแบบ Input → Process → Output

```
[Input Plugin]              [Output Plugin]
kafka_consumer  ──────────►  influxdb_v2
cpu             ──────────►
mem             ──────────►
```

### ทำไมต้องมี Telegraf? ทำไมไม่ส่งตรงจาก NiFi → InfluxDB?

Telegraf ถนัดกับ **time-series metric** โดยเฉพาะ มี:
- Plugin พร้อมใช้สำหรับ Kafka, CPU, Memory ฯลฯ
- แปลง JSON เป็น Line Protocol ของ InfluxDB อัตโนมัติ
- Buffer ป้องกัน data loss ถ้า InfluxDB ชั่วคราวไม่ตอบสนอง

### Config Telegraf ในระบบนี้

```toml
[agent]
  interval = "10s"
  flush_interval = "30s"
  hostname = "telegraf-mintpower"

[[inputs.kafka_consumer]]
  brokers = ["kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092"]
  topics = ["opc-raw-data"]
  consumer_group = "telegraf-opc-consumer"
  offset = "newest"
  data_format = "json"
  json_time_key = "timestamp"
  json_time_format = "2006-01-02T15:04:05.999999999Z07:00"
  tag_keys = ["source_id", "device_id"]
  name_override = "opc_data"

[[inputs.cpu]]
  percpu = false
  totalcpu = true

[[inputs.mem]]

[[inputs.disk]]
  mount_points = ["/", "/mnt/nvme-storage"]
  ignore_fs = ["tmpfs", "devtmpfs", "overlay", "aufs", "squashfs"]

[[inputs.diskio]]
  devices = ["sda", "nvme0n1"]

[[outputs.influxdb_v2]]
  urls = ["http://influxdb.it.svc.cluster.local:8086"]
  token = "${INFLUXDB_TOKEN}"
  organization = "${INFLUXDB_ORG}"
  bucket = "${INFLUXDB_BUCKET}"
  timeout = "5s"
```

### Measurements ใน InfluxDB

| Measurement | แหล่งข้อมูล | ตัวอย่าง Fields |
|------------|------------|----------------|
| `opc_data` | Kafka `opc-raw-data` | Temp_Boiler_01, Press_Line_01, RPM_Motor_01 |
| `cpu` | Host CPU | usage_idle, usage_user, usage_system |
| `mem` | Host Memory | used, available, used_percent |
| `disk` | Host Disk (2 partitions) | used, free, total, used_percent |
| `diskio` | Host Disk I/O | read_bytes, write_bytes, iops |

### ข้อกำหนดสำหรับ disk และ diskio inputs

Telegraf ต้องเห็น Host filesystem จึงต้องมีการ mount พิเศษใน Deployment:

```yaml
env:
  - name: HOST_MOUNT_PREFIX
    value: /hostfs
  - name: HOST_PROC
    value: /hostfs/proc
  - name: HOST_SYS
    value: /hostfs/sys
volumeMounts:
  - name: hostfs
    mountPath: /hostfs
    readOnly: true
  - name: dev
    mountPath: /hostfs/dev
    readOnly: true
volumes:
  - name: hostfs
    hostPath:
      path: /
  - name: dev
    hostPath:
      path: /dev
```

---

## 9. InfluxDB

### InfluxDB คืออะไร?

**InfluxDB** คือ **ฐานข้อมูล Time-Series** ที่ออกแบบมาเพื่อเก็บข้อมูลที่มี Timestamp โดยเฉพาะ

ทำไมไม่ใช้ MySQL หรือ PostgreSQL?  
ฐานข้อมูลทั่วไปช้ามากเมื่อต้อง:
- Insert ข้อมูลพร้อม Timestamp นับพันครั้งต่อวินาที
- Query ช่วงเวลา (เช่น "อุณหภูมิ 3 ชั่วโมงที่แล้ว")
- Aggregate ตามเวลา (เช่น "ค่าเฉลี่ยทุก 5 นาที")

InfluxDB ออกแบบมาเพื่อสิ่งนี้โดยเฉพาะ

### ศัพท์ InfluxDB

| คำ | คืออะไร | เทียบกับ SQL |
|----|---------|-------------|
| **Organization** | กลุ่มผู้ใช้สูงสุด | Database Server |
| **Bucket** | กลุ่มข้อมูล | Database |
| **Measurement** | ประเภทข้อมูล | Table |
| **Field** | ค่าตัวเลขที่เปลี่ยนได้ | Column (numeric) |
| **Tag** | ค่าที่ใช้กรอง/index | Column (indexed string) |
| **Point** | ข้อมูล 1 แถว | Row |

ตัวอย่างข้อมูลใน InfluxDB:
```
measurement: opc_data
├── time: 2026-05-07T10:30:00Z   ← Timestamp (auto)
├── tags:
│   ├── source_id: mintserver-prosys
│   └── device_id: opc-prosys-300tags
└── fields:
    ├── Temp_Boiler_01: 85.3
    ├── Temp_Boiler_02: 86.1
    ├── Press_Line_01: 4.2
    └── ... (307 fields)
```

### Flux Query Language

InfluxDB 2.x ใช้ภาษา **Flux** แทน SQL:

```flux
from(bucket: "opc-data")
  |> range(start: -1h)                          // ย้อนหลัง 1 ชั่วโมง
  |> filter(fn: (r) => r._measurement == "opc_data")
  |> filter(fn: (r) => r._field == "Temp_Boiler_01")
  |> aggregateWindow(every: 5m, fn: mean)       // ค่าเฉลี่ยทุก 5 นาที
```

### การตั้งค่าใน Project นี้

| รายการ | ค่า |
|--------|-----|
| Version | InfluxDB 2.7 |
| NodePort | 30086 |
| Retention | 2160 ชั่วโมง (90 วัน) |
| Storage | 50 GB (NVMe) |

---

## 10. Grafana

### Grafana คืออะไร?

**Grafana** คือ **แพลตฟอร์ม Visualization** ที่ดึงข้อมูลจากหลายแหล่งมาแสดงเป็น Dashboard

สิ่งที่ Grafana ทำได้:
- แสดงกราฟ Time-Series จาก InfluxDB
- แสดงตาราง, Gauge, Heatmap
- ตั้ง Alert เมื่อค่าเกิน Threshold
- แชร์ Dashboard ให้ทีมดูพร้อมกัน

### Data Source ในระบบนี้

```
Grafana → InfluxDB (http://influxdb.it.svc.cluster.local:8086)
```

### Dashboard ที่มีอยู่

- **uid: `ffl0uchin1hxcc`** — OPC Sensor Data Dashboard v12
  - แสดง 307 Tags จาก OPC UA
  - ใช้ Timeseries Panel
  - Field names: `Temp_Boiler_01`, `Press_Line_01`, etc.

### ข้อสำคัญเรื่อง Legend

Grafana 11 Timeseries Panel ต้องตั้ง `legend.displayMode = "list"` เท่านั้น  
ถ้าตั้งเป็น `"hidden"` กราฟจะไม่ render (Bug ที่พบในระบบนี้)

---

## 11. MinIO

### MinIO คืออะไร?

**MinIO** คือ **Object Storage แบบ Self-hosted** ที่ Compatible กับ Amazon S3 API

เปรียบเทียบ:
- **Amazon S3** = Dropbox ขนาดองค์กรบน Cloud
- **MinIO** = เหมือน S3 แต่ติดตั้งในเครื่องเราเอง

ทำไมต้องมี MinIO:
- เก็บข้อมูลระยะยาว (Data Lake) ในรูปแบบไฟล์
- ไม่ขึ้นกับ Cloud (Airgap ได้)
- Trino สามารถ Query ไฟล์ JSON/Parquet ใน MinIO ผ่าน S3 API

### แนวคิด Bucket และ Object

| คำ | คืออะไร | เปรียบเหมือน |
|----|---------|-------------|
| **Bucket** | ภาชนะหลัก | โฟลเดอร์ root |
| **Object** | ไฟล์แต่ละไฟล์ | ไฟล์ |
| **Key** | ที่อยู่/ชื่อ Object | path ของไฟล์ |

### โครงสร้างข้อมูลใน MinIO

```
Bucket: opc-raw
└── data/
    ├── year=2026/
    │   ├── month=05/
    │   │   ├── day=06/
    │   │   │   ├── abc123.json   ← 100 records
    │   │   │   ├── def456.json
    │   │   │   └── ...
    │   │   └── day=07/
    │   │       └── ...
    │   └── ...
    └── ...
Bucket: opc-raw (metadata/)
└── metadata/            ← Trino Hive Metastore
```

โครงสร้าง `year=/month=/day=` นี้เรียกว่า **Partition** ช่วยให้ Trino Query เร็วขึ้น เพราะไม่ต้องสแกนทั้งหมด

### NodePort

| Service | Port |
|---------|------|
| MinIO API (S3) | 30900 |
| MinIO Console (UI) | 30901 |

---

## 12. Trino

### Trino คืออะไร?

**Trino** (เดิมชื่อ PrestoSQL) คือ **SQL Query Engine แบบกระจาย** สำหรับวิเคราะห์ข้อมูลขนาดใหญ่

Trino ไม่ได้เก็บข้อมูลเอง แต่ทำหน้าที่ **แปล SQL ไปยัง Data Source ต่าง ๆ**

ใน Project นี้ Trino เชื่อมกับ **MinIO** ผ่าน Hive Connector:
```sql
-- Query ข้อมูลย้อนหลังจาก MinIO โดยตรง!
SELECT AVG(Temp_Boiler_01), DATE_TRUNC('hour', timestamp)
FROM minio.opc.sensor_data
WHERE year = '2026' AND month = '05' AND day = '07'
GROUP BY 2
ORDER BY 2;
```

### Hive Metastore (File-based)

Trino ต้องรู้โครงสร้างข้อมูล (schema) ก่อน Query ได้ ใช้ **File-based Hive Metastore** ซึ่งเก็บ metadata ลงใน MinIO เอง ไม่ต้องตั้ง Hive Metastore Server แยก

### Partition Sync CronJob

เมื่อ NiFi Core เพิ่มโฟลเดอร์ `day=08` ใหม่ Trino จะยังไม่รู้จักจนกว่าจะ sync

CronJob `trino-partition-sync` รันทุกวันตี 0:05 (Bangkok time):
```sql
CALL minio.system.sync_partition_metadata(
  schema_name => 'opc',
  table_name  => 'sensor_data',
  mode        => 'ADD'
);
```

ผลคือ Trino ค้นพบ Partition ใหม่และพร้อม Query ทันที

---

## 13. OpenMAINT

### OpenMAINT คืออะไร?

**OpenMAINT** คือ **ระบบจัดการ Asset และการบำรุงรักษา** (CMDB - Configuration Management Database)

ในบริบทโรงงาน OpenMAINT ช่วย:
- บันทึกว่ามีเครื่องจักรอะไรบ้าง (Asset Register)
- เครื่องอยู่ที่ไหน ใครรับผิดชอบ
- ประวัติการซ่อมบำรุง
- แผนการบำรุงรักษา (Maintenance Schedule)

OpenMAINT สร้างบน **CMDBuild** (เป็น Application Framework) โดย Itmicus

### การแก้ปัญหาที่ซับซ้อน (สำคัญมาก!)

OpenMAINT ใน Project นี้มีการแก้ปัญหาพิเศษหลายอย่าง:

**ปัญหา 1: Container restart loop**  
CMDBuild ต้อง restart Tomcat ครั้งหนึ่งตอนบูตครั้งแรก เพื่อโหลด PostgreSQL JDBC Driver แต่เมื่อ Tomcat หยุดทำงาน Container ก็หยุดตาม (เพราะ Tomcat เป็น PID 1)

**วิธีแก้:** Override command ให้ entrypoint ทำงาน background และมี bash script (PID 1) คอย monitor Tomcat process:

```yaml
command: ["/bin/bash", "-c"]
args:
  - |
    trap 'pkill -f "org.apache.catalina"' SIGTERM
    /usr/local/bin/docker-entrypoint.sh &   # รัน background
    while true; do
      sleep 15
      pgrep -f "org.apache.catalina" > /dev/null && continue
      sleep 10
      pgrep -f "org.apache.catalina" > /dev/null || exit 1
    done
```

**ปัญหา 2: PostGIS Extension**  
CMDBuild ต้องการ PostGIS (GIS extension สำหรับ PostgreSQL) แต่ Image `postgres:15-alpine` ไม่มี PostGIS

**วิธีแก้:** สร้าง Fake/Stub PostGIS functions ใน PostgreSQL โดยตรง:
```sql
CREATE SCHEMA IF NOT EXISTS gis;
CREATE OR REPLACE FUNCTION public.postgis_lib_version() RETURNS text AS $$ SELECT '3.3.2' $$ LANGUAGE sql;
CREATE OR REPLACE FUNCTION public.postgis_version() RETURNS text AS $$ SELECT '3 USE_GEOS=1' $$ LANGUAGE sql;
```

ข้อมูลนี้ persistent อยู่ใน Database ไม่หายแม้ Pod restart

---

## 14. Data Flow

### ภาพรวม End-to-End

```
[Prosys OPC UA Simulator]
เครื่อง: mintserver
opc.tcp://<IP>:53530/OPCUA/SimulationServer
307 Tags → ส่งข้อมูลทุก 2 วินาที
           │
           │ opc.tcp Protocol
           ▼
┌──────────────────────────────────────────────────────┐
│  NiFi Edge (Pod: nifi-edge, ns: it, NodePort: 31444) │
│                                                      │
│  ExecuteGroovyScript (opc_reader_final.groovy)       │
│  ├── OpcUaClient.create() → connect → readValues()  │
│  ├── 307 tags อ่านพร้อมกัน (batch read)              │
│  └── สร้าง JSON FlowFile (flat format)               │
│           │                                          │
│  PublishKafka → topic: opc-raw-data                 │
└──────────────────────────────────────────────────────┘
           │
           │ Kafka Protocol (9092)
           ▼
┌──────────────────────────────────────────────────────┐
│  Kafka Broker (ns: dmz)                              │
│  Topic: opc-raw-data                                 │
│  Partitions: 3, Retention: 7 วัน                    │
└──────────────────────────────────────────────────────┘
           │
     ┌─────┴──────────────────┐
     │                        │
     ▼                        ▼
┌────────────┐      ┌────────────────────────────────┐
│  Telegraf  │      │  NiFi Core                     │
│            │      │  (Pod: nifi-core, ns: it)       │
│ consume    │      │                                 │
│ opc-raw    │      │  ConsumeKafka (opc-raw-data)    │
│ -data      │      │  → MergeRecord (100 records)   │
│            │      │  → PutS3Object (MinIO)          │
│ JSON parse │      └────────────────────────────────┘
│ → Line     │                   │
│   Protocol │                   │ S3 API
│            │                   ▼
└────────────┘      ┌────────────────────────────────┐
     │               │  MinIO (ns: it)                │
     │ HTTP API       │  Bucket: opc-raw               │
     ▼               │  Path: data/year=.../           │
┌──────────┐         │          month=.../             │
│ InfluxDB │         │          day=.../               │
│ (ns: it) │         │          {uuid}.json            │
│          │         └────────────────────────────────┘
│ Bucket:  │                    │
│ opc-data │                    │ (ทุกวัน 00:05)
│          │                    ▼
│ opc_data │         ┌────────────────────────────────┐
│ measure- │         │  Trino (ns: it)                │
│ ment     │         │  CronJob: partition sync        │
└──────────┘         │  SQL Query: SELECT * FROM       │
     │               │  minio.opc.sensor_data          │
     ▼               └────────────────────────────────┘
┌──────────┐
│ Grafana  │
│ (ns: it) │
│          │
│ Dashboard│
│ uid:ffl0 │
│ uchin1h  │
│ xcc      │
└──────────┘
```

### ตัวอย่าง JSON ที่ไหลผ่านระบบ

ข้อมูล 1 Packet ที่ NiFi Edge สร้างทุก 2 วินาที:

```json
{
  "timestamp": "2026-05-07T10:30:00.123Z",
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tag_count": 307,
  "bad_count": 0,
  "Counter": 12345,
  "Random": 0.7823,
  "Temp_Boiler_01": 85.3,
  "Temp_Boiler_02": 86.1,
  "Temp_HeatEx_01": 72.5,
  "Press_Line_01": 4.2,
  "Flow_Main_01": 125.7,
  "Level_Tank_01": 68.3,
  "Vibration_Pump_01": 0.023,
  "RPM_Motor_01": 1450.0,
  "CO2_Zone_01": 412.5,
  ...
}
```

---

## 15. โครงสร้างไฟล์

```
/home/mintpower/lab/k3s/
│
├── HANDBOOK.md          ← คู่มือนี้
├── README.md            ← Overview สั้น
├── concept.png          ← ภาพ Architecture
│
├── config/
│   └── k3s-config.yaml  ← k3s startup config
│
├── install/             ← ไฟล์ติดตั้ง (Airgap)
│   ├── k3s              ← k3s binary
│   ├── k3s-airgap-images-amd64.tar.gz  ← k3s system images
│   ├── grafana-image.tar
│   ├── influxdb-image.tar
│   ├── minio-images.tar
│   ├── nifi-image.tar
│   ├── akhq-image.tar
│   ├── postgres-image.tar
│   ├── openmaint-images.tar
│   ├── helm-v3.16.4-linux-amd64.tar.gz
│   └── strimzi-0.43.0/  ← Strimzi Kafka Operator
│
├── manifests/           ← Kubernetes YAML (แบ่งตาม Phase)
│   ├── phase1/          ← Infrastructure พื้นฐาน
│   │   ├── namespaces.yaml      ← สร้าง namespace dmz, it
│   │   ├── storage-class.yaml   ← local-nvme StorageClass
│   │   └── persistent-volumes.yaml  ← PV ทั้งหมด
│   │
│   ├── phase2/          ← Kafka Cluster
│   │   ├── strimzi-operator-config.yaml
│   │   ├── kafka-cluster.yaml   ← Kafka + KRaft
│   │   ├── kafka-topics.yaml    ← 3 Topics
│   │   ├── kafka-pvc.yaml
│   │   └── akhq.yaml
│   │
│   ├── phase3/          ← Metrics Stack
│   │   ├── influxdb.yaml
│   │   ├── influxdb-secret.yaml
│   │   ├── influxdb-pvc.yaml
│   │   ├── pv-influxdb2.yaml
│   │   ├── telegraf.yaml
│   │   ├── telegraf-config.yaml  ← Kafka consumer → InfluxDB
│   │   ├── grafana.yaml
│   │   ├── grafana-config.yaml
│   │   └── grafana-pvc.yaml
│   │
│   ├── phase4/          ← Data Lake + Query
│   │   ├── minio.yaml
│   │   ├── minio-secret.yaml
│   │   ├── minio-pvc.yaml
│   │   ├── minio-init-job.yaml  ← สร้าง bucket อัตโนมัติ
│   │   ├── nifi-core.yaml       ← Kafka → MinIO
│   │   ├── nifi-core-pvc.yaml
│   │   ├── trino.yaml
│   │   ├── trino-config.yaml    ← Hive connector → MinIO
│   │   ├── trino-pvc.yaml
│   │   └── trino-partition-sync.yaml  ← CronJob
│   │
│   ├── phase5/          ← OPC Edge + CMDB
│   │   ├── nifi-edge.yaml       ← OPC UA → Kafka
│   │   ├── nifi-edge-pvc.yaml
│   │   ├── openmaint.yaml       ← CMDB
│   │   ├── openmaint-secret.yaml
│   │   ├── openmaint-pvc.yaml
│   │   └── postgres.yaml        ← PostgreSQL สำหรับ OpenMAINT
│   │
│   └── phase6/          ← Network / Ingress
│       ├── traefik-values.yaml
│       ├── ingress-it.yaml
│       ├── ingress-dmz.yaml
│       ├── ingress-nifi-tcp.yaml
│       └── trino-middleware.yaml
│
├── tools/               ← Scripts และ Tools
│   ├── opc_reader_final.groovy  ← NiFi Edge Groovy Script (307 tags)
│   ├── opc_reader.groovy        ← เวอร์ชันเก่า
│   ├── browse_opc.py            ← Python script สำรวจ OPC nodes
│   ├── deploy_opc_script.py     ← Deploy script ไปยัง NiFi
│   └── gen_300tags.py           ← Generate tag definitions
│
├── scripts/
│   ├── setup-nifi-core-flow.sh  ← Setup NiFi Core flow อัตโนมัติ
│   └── telegraf-cpu-analysis.md
│
├── milo-jars/           ← Eclipse Milo OPC UA Library
│   └── *.jar            ← ต้อง copy ไปยัง NiFi Edge
│
├── opc-sim/             ← OPC Simulator setup files
│
├── plan/                ← เอกสาร Planning
│
└── data/                ← k3s data directory (อย่าลบ!)
    ├── agent/
    └── server/
```

---

## 16. การ Deploy

### ภาพรวม 6 Phases

| Phase | สิ่งที่ Deploy | ทำไมต้องทำก่อน |
|-------|--------------|---------------|
| **Phase 1** | Namespace, StorageClass, PV | ทุกอย่างต้องการพื้นที่เก็บข้อมูลก่อน |
| **Phase 2** | Kafka, AKHQ | Pipeline ต้องมี Message Bus ก่อน |
| **Phase 3** | InfluxDB, Telegraf, Grafana | ต้องมีที่เก็บ Metrics และแสดงผล |
| **Phase 4** | MinIO, NiFi Core, Trino | Data Lake และ Query Engine |
| **Phase 5** | NiFi Edge, OpenMAINT, Postgres | OPC Source และ CMDB |
| **Phase 6** | Traefik Ingress | เข้าถึงผ่าน Domain name |

### คำสั่งพื้นฐาน kubectl

```bash
# ดู pod ทั้งหมด
kubectl get pods -A

# ดู pod ใน namespace it
kubectl get pods -n it

# ดู log ของ pod
kubectl logs -n it telegraf-xxxxx

# เข้าไปใน pod
kubectl exec -it -n it telegraf-xxxxx -- /bin/bash

# Apply YAML
kubectl apply -f manifests/phase1/namespaces.yaml

# Apply ทั้งโฟลเดอร์
kubectl apply -f manifests/phase1/

# ดู Service (Port)
kubectl get svc -n it

# ดู PersistentVolume
kubectl get pv

# Restart deployment
kubectl rollout restart deployment/grafana -n it

# ดู resource usage
kubectl top pods -n it
```

### Load Airgap Images

ก่อน Deploy ต้องโหลด Image เข้า k3s ก่อน:

```bash
# โหลด Image เข้า containerd (k3s ใช้ containerd ไม่ใช่ Docker)
sudo k3s ctr images import install/grafana-image.tar
sudo k3s ctr images import install/influxdb-image.tar
sudo k3s ctr images import install/minio-images.tar
sudo k3s ctr images import install/nifi-image.tar
sudo k3s ctr images import install/akhq-image.tar
sudo k3s ctr images import install/postgres-image.tar
sudo k3s ctr images import install/openmaint-images.tar

# ดู Image ที่โหลดแล้ว
sudo k3s ctr images list
```

### Deploy Phase ตัวอย่าง (Phase 1)

```bash
# 1. Apply Storage Class
kubectl apply -f manifests/phase1/storage-class.yaml

# 2. สร้าง Directory บน Host (จำเป็นสำหรับ local PV)
sudo mkdir -p /mnt/nvme-storage/k8s-pv/{kafka,influxdb,minio,nifi-core,nifi-edge,grafana,openmaint,trino}
sudo chmod 777 /mnt/nvme-storage/k8s-pv/*

# 3. สร้าง Namespace
kubectl apply -f manifests/phase1/namespaces.yaml

# 4. สร้าง PersistentVolume
kubectl apply -f manifests/phase1/persistent-volumes.yaml

# ตรวจสอบ
kubectl get pv
```

---

## 17. URL และ Port

### NodePort (เข้าถึงได้จาก IP ของ Server โดยตรง)

แทน `<K3S_NODE_IP>` ด้วย IP จริงของ mintpower

| Service | URL | NodePort |
|---------|-----|----------|
| **Grafana** | `http://<IP>:30300` | 30300 |
| **InfluxDB** | `http://<IP>:30086` | 30086 |
| **MinIO Console** | `http://<IP>:30901` | 30901 |
| **MinIO API** | `http://<IP>:30900` | 30900 |
| **NiFi Core** | `https://<IP>:31443` | 31443 |
| **NiFi Edge** | `https://<IP>:31444` | 31444 |
| **Trino** | `http://<IP>:30800` | 30800 |
| **OpenMAINT** | `http://<IP>:30885/cmdbuild` | 30885 |
| **AKHQ (Kafka UI)** | `http://<IP>:32080` | 32080 |
| **Kafka External** | `<IP>:32092` | 32092 |

### Ingress Domain (ต้องตั้ง /etc/hosts ก่อน)

เพิ่มใน `/etc/hosts`:
```
<K3S_NODE_IP>  grafana.mintpower.local
<K3S_NODE_IP>  influxdb.mintpower.local
<K3S_NODE_IP>  minio.mintpower.local
<K3S_NODE_IP>  nifi-core.mintpower.local
<K3S_NODE_IP>  nifi-edge.mintpower.local
<K3S_NODE_IP>  trino.mintpower.local
<K3S_NODE_IP>  openmaint.mintpower.local
<K3S_NODE_IP>  akhq.mintpower.local
```

จากนั้นเข้าถึงได้ผ่าน:
- `http://grafana.mintpower.local`
- `http://minio.mintpower.local`
- ฯลฯ

### Internal DNS (สำหรับการสื่อสารระหว่าง Container)

ภายใน Kubernetes ใช้ format: `<service-name>.<namespace>.svc.cluster.local`

| ตัวอย่าง | ใช้ใน |
|---------|-------|
| `kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092` | Telegraf, NiFi ต่อ Kafka |
| `influxdb.it.svc.cluster.local:8086` | Telegraf ส่ง Metrics |
| `minio.it.svc.cluster.local:9000` | NiFi Core ส่ง File |
| `trino.it.svc.cluster.local:8080` | CronJob sync partition |

---

## 18. Troubleshoot

### เช็กสถานะระบบ

```bash
# ดู pod ทั้งหมดและสถานะ
kubectl get pods -A

# Pod ที่ไม่ใช่ Running/Completed → ปัญหา!
kubectl describe pod <pod-name> -n <namespace>

# ดู Log
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous  # log ของรอบก่อน crash
kubectl logs <pod-name> -n <namespace> -f          # follow real-time
```

### ปัญหาที่พบบ่อย

#### 1. Pod อยู่ใน CrashLoopBackOff

```bash
kubectl describe pod <pod-name> -n <ns>
# ดู Events ที่ด้านล่าง → บอกสาเหตุ

kubectl logs <pod-name> -n <ns> --previous
# ดู log ก่อน crash
```

#### 2. Pod อยู่ใน Pending

```bash
kubectl describe pod <pod-name> -n <ns>
# มักเกิดจาก:
# - PVC ไม่ได้ Bound (storage ไม่มีพื้นที่)
# - Node ไม่มี Resource พอ
```

#### 3. ข้อมูลไม่ไหลเข้า Grafana

ตรวจทีละขั้น:

```bash
# 1. ตรวจว่า NiFi Edge ส่ง message เข้า Kafka หรือเปล่า
# เปิด AKHQ → Topics → opc-raw-data → ดู Messages

# 2. ตรวจว่า Telegraf consume ได้หรือเปล่า
kubectl logs -n it telegraf-xxxxx | tail -50

# 3. ตรวจว่า InfluxDB รับข้อมูลหรือเปล่า
# เปิด InfluxDB UI → Data Explorer → Query opc_data measurement

# 4. ตรวจว่า Grafana Data Source ใช้งานได้
# Grafana → Configuration → Data Sources → Test
```

#### 4. NiFi ไม่ได้ flow ทำงาน

```bash
# เข้า NiFi UI
# https://<IP>:31443  (NiFi Core)
# https://<IP>:31444  (NiFi Edge)
# Login: admin / <password>
# ตรวจดูว่า Processor มีสถานะ Running หรือ Stopped
# ถ้า Error → คลิก Processor → View Status History
```

#### 5. MinIO ไม่มีไฟล์ใหม่

```bash
# เข้า MinIO Console http://<IP>:30901
# ดู Bucket: opc-raw → data/ → year=2026/month=05/day=07/
# ถ้าไม่มี → ปัญหาอยู่ที่ NiFi Core หรือ Kafka
```

#### 6. OpenMAINT ไม่ Boot

```bash
# ดู log จาก Container
kubectl logs -n it openmaint-xxxxx

# OpenMAINT log จริงอยู่ที่ Tomcat (ไม่ใช่ kubectl logs)
kubectl exec -it -n it openmaint-xxxxx -- \
  tail -f /usr/local/tomcat/logs/cmdbuild.log

# ตรวจสถานะ Boot
curl http://<IP>:30885/cmdbuild/services/rest/v3/boot/status
```

#### 7. Telegraf Consumer Lag สูง

```bash
# ดูผ่าน AKHQ: http://<IP>:32080
# Consumer Groups → telegraf-opc-consumer → ดู Lag
# ถ้า Lag สูงมาก → Telegraf อาจ restart หรือ InfluxDB ช้า
kubectl logs -n it telegraf-xxxxx | grep -i "error\|slow\|timeout"
```

#### 8. Kafka Consumer Group Lag สูง / Orphan Consumer Group

Consumer group ที่มี lag สูงแต่ไม่มี active member เรียกว่า **orphan group** — เกิดจาก processor ที่เคยใช้ group นั้นถูกลบออกแต่ group ยังค้างใน Kafka

```bash
# ตรวจสอบ consumer group ทั้งหมด
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --list

# ตรวจสอบว่ามี active member หรือเปล่า
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group <group-name>
# ถ้า "has no active members" = orphan

# ลบ orphan group (ปลอดภัย — ไม่ลบ message ใน topic)
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete --group <group-name>
```

> **กรณีตัวอย่าง (2026-05-07):** `nifi-edge-consumer` มี lag 65,694 — ตรวจพบว่าไม่มี processor ใดในระบบใช้ group นี้ เกิดจาก redeploy NiFi Edge โดยไม่มี ConsumeKafka ใน flow ใหม่ ได้ลบออกแล้ว InfluxDB ยังรับข้อมูลปกติ (43,878 records/5 นาที)

### ตรวจ Resource

```bash
# ดู CPU/Memory ของ pod
kubectl top pods -n it
kubectl top pods -n dmz

# ดู Disk usage ของ PV
df -h /mnt/nvme-storage/k8s-pv/
```

---

## 19. Storage

### PersistentVolume ทั้งหมด

| PV | Path บน Host | ขนาด | ใช้โดย |
|----|------------|------|--------|
| pv-kafka | `/mnt/nvme-storage/k8s-pv/kafka` | 50 GB | Kafka Messages |
| pv-influxdb | `/mnt/nvme-storage/k8s-pv/influxdb` | 50 GB | Time-series data |
| pv-minio | `/mnt/nvme-storage/k8s-pv/minio` | 100 GB | Data Lake files |
| pv-nifi-core | `/mnt/nvme-storage/k8s-pv/nifi-core` | 20 GB | NiFi config/repo |
| pv-nifi-edge | `/mnt/nvme-storage/k8s-pv/nifi-edge` | 10 GB | NiFi config/repo |
| pv-grafana | `/mnt/nvme-storage/k8s-pv/grafana` | 10 GB | Dashboard config |
| pv-openmaint | `/mnt/nvme-storage/k8s-pv/openmaint` | 20 GB | CMDB data |
| pv-trino | `/mnt/nvme-storage/k8s-pv/trino` | 20 GB | Trino spill |
| **รวม** | | **280 GB** | |

### ทำไม Reclaim Policy เป็น "Retain"?

```yaml
persistentVolumeReclaimPolicy: Retain
```

ถ้า Pod หรือ PVC ถูกลบ ข้อมูลยังคงอยู่บน Host ป้องกัน data loss โดยบังเอิญ

ถ้า Reclaim เป็น `Delete` → ลบ PVC ปุ๊บ ข้อมูลหายทันที

### StorageClass: local-nvme

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-nvme
provisioner: kubernetes.io/no-provisioner   # ← Manual provisioning
volumeBindingMode: WaitForFirstConsumer      # รอจนกว่า Pod จะ schedule ก่อน bind
reclaimPolicy: Retain
```

`no-provisioner` หมายความว่า PV ต้องสร้างด้วยมือ (ไม่ auto-provision) เหมาะกับ Single Node ที่รู้ว่า disk อยู่ที่ไหน

---

## 20. Security

### Zone Separation

```
[OPC UA Device / mintserver]
          │
          │ opc.tcp (port 53530)
          ▼
    ┌─────────────────────────────────┐
    │         DMZ Namespace           │
    │                                 │
    │  ┌─────────┐    ┌──────────┐   │
    │  │  Kafka  │◄───│  AKHQ    │   │
    │  │ Broker  │    │ (UI)     │   │
    │  └─────────┘    └──────────┘   │
    │       │                        │
    └───────┼────────────────────────┘
            │ Kafka Protocol (9092)
            │ (internal ClusterIP)
    ┌───────┼────────────────────────┐
    │       ▼         IT Namespace   │
    │  ┌─────────┐                   │
    │  │Telegraf │ → InfluxDB        │
    │  │NiFi Core│ → MinIO           │
    │  │NiFi Edge│ (อ่าน OPC ด้วย) │
    │  └─────────┘                   │
    └────────────────────────────────┘
```

IT Namespace ไม่มี Port expose สู่ภายนอกโดยตรงในสภาพ Production จริง ทุกอย่างผ่าน Ingress ที่ควบคุมได้

### Secrets ใน Kubernetes

Password และ Token เก็บเป็น Kubernetes Secret (base64 encoded):

```bash
# ดู Secret ที่มี
kubectl get secrets -n it

# ดู value (decode base64)
kubectl get secret influxdb-secret -n it -o jsonpath='{.data.admin-token}' | base64 -d
```

**ห้าม** hardcode password ใน YAML หรือ Code → ใช้ Secret Reference:
```yaml
env:
  - name: INFLUXDB_TOKEN
    valueFrom:
      secretKeyRef:
        name: influxdb-secret
        key: admin-token    # ← อ่านจาก Secret
```

### Network Policy (อนาคต)

ปัจจุบันยังไม่มี NetworkPolicy → Pod ทุกตัวในทุก Namespace คุยกันได้  
ใน Production จริงควรเพิ่ม NetworkPolicy จำกัดไม่ให้ DMZ คุยกับ IT Zone โดยตรง ยกเว้น Kafka

---

## ภาคผนวก: Glossary ศัพท์เทคนิค

| คำ | ความหมาย |
|----|---------|
| **Airgap** | ระบบที่ไม่ต่ออินเทอร์เน็ต |
| **Broker** | เซิร์ฟเวอร์ Kafka ที่รับ-ส่งข้อมูล |
| **Container** | กล่องรัน Application พร้อม dependencies |
| **CRD** | Custom Resource Definition — ขยาย Kubernetes ด้วย Object ใหม่ |
| **CMDB** | Configuration Management Database — ฐานข้อมูล IT Asset |
| **Data Lake** | ที่เก็บข้อมูลดิบขนาดใหญ่รูปแบบใดก็ได้ |
| **DMZ** | Demilitarized Zone — โซนกันชนระหว่าง External กับ Internal |
| **FlowFile** | หน่วยข้อมูลใน Apache NiFi |
| **Groovy** | ภาษา Script บน JVM ใช้ใน NiFi ExecuteScript |
| **Helm** | Package Manager สำหรับ Kubernetes |
| **Image** | Template สำหรับสร้าง Container |
| **Ingress** | ตัวรับ HTTP request แล้วแจกไปยัง Service ที่เหมาะสม |
| **KRaft** | Kafka Raft — Consensus Protocol ใหม่ แทน ZooKeeper |
| **Line Protocol** | รูปแบบข้อมูลของ InfluxDB |
| **Measurement** | ประเภทข้อมูลใน InfluxDB (คล้าย Table) |
| **Milo** | Eclipse Milo — Java Library สำหรับ OPC UA |
| **Namespace** | กลุ่มย่อยใน Kubernetes สำหรับแยก Resource |
| **NodePort** | Port บน Host ที่ forward เข้า Service ใน Cluster |
| **Object Storage** | ที่เก็บไฟล์แบบ flat ไม่มี hierarchy (S3, MinIO) |
| **OPC UA** | Open Platform Communications Unified Architecture |
| **Operator** | Program ใน Kubernetes ที่จัดการ Application อัตโนมัติ |
| **Partition** | การแบ่งข้อมูลตาม Key (Kafka) หรือ Folder (Data Lake) |
| **PV/PVC** | Persistent Volume / Claim — Storage ใน Kubernetes |
| **Pod** | Unit เล็กสุดที่รัน Container ใน Kubernetes |
| **Probe** | การตรวจสอบว่า Container ยังทำงานอยู่ |
| **Producer/Consumer** | ผู้ส่ง/ผู้รับข้อมูลใน Kafka |
| **Retention** | ระยะเวลาเก็บข้อมูลก่อนลบทิ้ง |
| **S3** | Simple Storage Service — Amazon S3 API (MinIO รองรับ) |
| **Strimzi** | Kubernetes Operator สำหรับ Kafka |
| **Tag** | ใน OPC UA = ตัวแปรจากเซ็นเซอร์ / ใน InfluxDB = indexed string |
| **Time-series** | ข้อมูลที่มี Timestamp บันทึกตามเวลา |
| **Topic** | หมวดหมู่ใน Kafka สำหรับจัดกลุ่มข้อมูล |
| **Traefik** | Ingress Controller ที่ k3s ใช้ by default |
| **YAML** | ภาษา Config สำหรับ Kubernetes (Yet Another Markup Language) |

---

*อัปเดตล่าสุด: 2026-05-07 | Phase 5 Complete | 307 OPC UA Tags | All pods Running | Disk Monitoring: เพิ่ม inputs.disk + inputs.diskio ใน Telegraf | Grafana Dashboard: storage-monitor-v1*
