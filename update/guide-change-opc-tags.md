# คู่มือ: เปลี่ยนจำนวน Tag ใน OPC UA Pipeline

**เวอร์ชัน:** 1.0  
**วันที่:** 2026-05-06  
**ใช้กับ:** Prosys OPC UA Simulation Server → NiFi Edge → Kafka

---

## ภาพรวมระบบ

```
mintserver (10.85.3.100)          mintpower (10.85.3.104)
┌─────────────────────┐           ┌──────────────────────────────────┐
│  Prosys OPC UA      │  opc.tcp  │  NiFi Edge (k3s, namespace: it)  │
│  port 53530         │ ────────► │  ExecuteGroovyScript             │
│  307 tags (ns=3)    │           │  → PublishKafka                  │
└─────────────────────┘           │  → Kafka topic: opc-raw-data     │
                                  └──────────────────────────────────┘
```

**ไฟล์หลักที่ต้องแก้เมื่อ tag เปลี่ยน:**  
`/home/mintpower/lab/k3s/tools/opc_reader_final.groovy` — script ที่ deploy ใน NiFi

---

## ขั้นตอนที่ 1: ตรวจสอบ Tag ปัจจุบันใน Prosys

### 1.1 Browse NodeId ทั้งหมดจาก Prosys

```bash
# บน mintpower — activate venv ของ opc-sim
source /home/mintpower/lab/k3s/opc-sim/venv/bin/activate

# รัน browse script
python3 /home/mintpower/lab/k3s/tools/browse_opc.py
```

ผลลัพธ์จะแสดงตาราง NodeId ทั้งหมดใน namespace 3 และบันทึกไว้ที่ `/tmp/browse_result.txt`

```
NodeId                         BrowseName                          DataType
------------------------------------------------------------------------------------------
  ns=3;i=1001                  Counter                             int
  ns=3;i=1002                  Random                             float
  ns=3;i=2001                  Temp_Boiler_01                     float
  ...
พบทั้งหมด: 307 nodes ใน namespace 3
```

### 1.2 ดู Tag ที่มีอยู่ในสคริปต์ปัจจุบัน

```bash
# นับจำนวน tag ใน script ปัจจุบัน
grep -c '^\s*\[' /home/mintpower/lab/k3s/tools/opc_reader_final.groovy

# ดูรายชื่อ tag ทั้งหมด
grep '^\s*\[' /home/mintpower/lab/k3s/tools/opc_reader_final.groovy | \
  sed 's/.*"\(.*\)".*/\1/'
```

---

## ขั้นตอนที่ 2: แก้ไข Groovy Script

ไฟล์: `/home/mintpower/lab/k3s/tools/opc_reader_final.groovy`

### โครงสร้าง NODE_DEFS

```groovy
static final List NODE_DEFS = [
    // รูปแบบ: ["ชื่อ Tag", namespace, NodeId_number]
    ["Counter",        3, 1001],
    ["Random",         3, 1002],
    ["Temp_Boiler_01", 3, 2001],
    // ...
]
```

### 2.1 กรณี: เพิ่ม Tag ใหม่

เปิดไฟล์ `opc_reader_final.groovy` แล้วเพิ่มบรรทัดใน `NODE_DEFS`:

```bash
# ตัวอย่าง: เพิ่ม tag ใหม่ที่ ns=3, i=3001
# แก้ไขในไฟล์ที่บรรทัดก่อน "]" ของ NODE_DEFS
```

```groovy
static final List NODE_DEFS = [
    // ... tag เดิม ...
    ["Temp_Boiler_20", 3, 2020],
    // เพิ่มบรรทัดใหม่ที่นี่:
    ["New_Sensor_01",  3, 3001],
    ["New_Sensor_02",  3, 3002],
]
```

อย่าลืมอัปเดต `DEVICE_ID` ให้สะท้อนจำนวน tag ใหม่ (บรรทัดที่ 17):

```groovy
@groovy.transform.Field static final String DEVICE_ID = "opc-prosys-350tags"
```

### 2.2 กรณี: ลบ Tag ออก

ลบบรรทัดที่ต้องการออกจาก `NODE_DEFS` โดยตรง

### 2.3 กรณี: เปลี่ยน Tag ทั้งหมด (สร้างจาก browse ใหม่)

```bash
# 1. Browse และบันทึกผล
source /home/mintpower/lab/k3s/opc-sim/venv/bin/activate
python3 /home/mintpower/lab/k3s/tools/browse_opc.py

# 2. ผลจะอยู่ที่ /tmp/browse_result.txt (รูปแบบ Groovy)
# นำเข้า NODE_DEFS ในสคริปต์แทนของเดิม
cat /tmp/browse_result.txt
```

ผล `/tmp/browse_result.txt` อยู่ในรูปแบบที่วางลงใน NODE_DEFS ได้เลย:

```
// OPC UA Browse result
// พบ 350 nodes ใน ns=3

    "Counter": new NodeId(3, 1001),
    "Random": new NodeId(3, 1002),
    ...
```

> **หมายเหตุ:** `browse_result.txt` ใช้รูปแบบ `new NodeId(ns, i)` แต่ `NODE_DEFS` ใช้ `["name", ns, i]`  
> แปลงด้วยคำสั่ง:

```bash
# แปลงจาก browse_result.txt → รูปแบบ NODE_DEFS
python3 - << 'EOF'
import re
with open("/tmp/browse_result.txt") as f:
    for line in f:
        m = re.match(r'\s*"(.+)":\s*new NodeId\((\d+),\s*(\d+)\)', line)
        if m:
            name, ns, nid = m.groups()
            print(f'    ["{name}", {ns}, {nid}],')
EOF
```

---

## ขั้นตอนที่ 3: Deploy Script ใหม่ขึ้น NiFi

### 3.1 หา Processor ID

```bash
# Groovy OPC Reader processor ID ปัจจุบัน
GROOVY_ID="fb9e2d81-019d-1000-f255-9b25076647d6"
```

> ถ้า pod restart และ ID เปลี่ยน ดูด้วย:
> ```bash
> NIFI_TOKEN=$(curl -sk -X POST https://10.85.3.104:31444/nifi-api/access/token \
>   -H "Content-Type: application/x-www-form-urlencoded" \
>   -d "username=admin&password=Nifi%40mintpower2024%21" | tr -d '"')
> curl -sk -H "Authorization: Bearer $NIFI_TOKEN" \
>   https://10.85.3.104:31444/nifi-api/flow/process-groups/root \
>   | python3 -c "import json,sys; [print(p['id'], p['component']['name']) \
>     for p in json.load(sys.stdin)['processGroupFlow']['flow']['processors']]"
> ```

### 3.2 รัน Deploy Script

```bash
python3 /home/mintpower/lab/k3s/tools/deploy_opc_script.py
```

> หรือรันด้วยตนเอง:

```bash
python3 - << 'PYEOF'
import json, subprocess, urllib.request, ssl

GROOVY_ID = "fb9e2d81-019d-1000-f255-9b25076647d6"
SCRIPT_FILE = "/home/mintpower/lab/k3s/tools/opc_reader_final.groovy"

def nifi_req(token, method, path, data=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"https://10.85.3.104:31444/nifi-api{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data: req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, context=ctx) as r: return json.load(r)

token = subprocess.run(
    ["curl","-sk","-X","POST","https://10.85.3.104:31444/nifi-api/access/token",
     "-H","Content-Type: application/x-www-form-urlencoded",
     "-d","username=admin&password=Nifi%40mintpower2024%21"],
    capture_output=True, text=True).stdout.strip().strip('"')

# Stop
proc = nifi_req(token, "GET", f"/processors/{GROOVY_ID}")
rev = proc["revision"]["version"]
nifi_req(token, "PUT", f"/processors/{GROOVY_ID}/run-status", {"revision":{"version":rev},"state":"STOPPED"})
print("Stopped")

# Update script
with open(SCRIPT_FILE) as f: script = f.read()
proc = nifi_req(token, "GET", f"/processors/{GROOVY_ID}")
rev = proc["revision"]["version"]
result = nifi_req(token, "PUT", f"/processors/{GROOVY_ID}", {
    "revision": {"version": rev},
    "component": {"id": GROOVY_ID, "config": {"properties": {"groovyx-script-body": script}}}
})
print(f"Updated (rev {result['revision']['version']})")

# Start
proc = nifi_req(token, "GET", f"/processors/{GROOVY_ID}")
rev = proc["revision"]["version"]
nifi_req(token, "PUT", f"/processors/{GROOVY_ID}/run-status", {"revision":{"version":rev},"state":"RUNNING"})
print("Started ✓")
PYEOF
```

---

## ขั้นตอนที่ 4: ตรวจสอบผลลัพธ์

### 4.1 ดู Log ว่า connect สำเร็จ

```bash
NIFI_POD=$(kubectl get pods -n it -l app=nifi-edge -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n it $NIFI_POD --since=2m | grep "\[OPC\]"
```

คาดว่าจะเห็น:
```
[OPC] Built 350 NodeIds          ← จำนวน tag ใหม่
[OPC] Connected ✓  (350 nodes)
```

### 4.2 ดูสถิติ Processor

```bash
NIFI_TOKEN=$(curl -sk -X POST https://10.85.3.104:31444/nifi-api/access/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Nifi%40mintpower2024%21" | tr -d '"')

curl -sk -H "Authorization: Bearer $NIFI_TOKEN" \
  "https://10.85.3.104:31444/nifi-api/flow/processors/fb9e2d81-019d-1000-f255-9b25076647d6/status" \
  | python3 -c "
import json,sys
s = json.load(sys.stdin)['processorStatus']['aggregateSnapshot']
print('Tasks:', s['taskCount'], '| Out:', s['flowFilesOut'], '| Written:', s['written'])
"
```

### 4.3 ตรวจ Message ใน Kafka

```bash
kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- bash -c \
  "timeout 5 bin/kafka-console-consumer.sh \
   --bootstrap-server localhost:9092 \
   --topic opc-raw-data --max-messages 1 2>/dev/null" \
  | python3 -c "
import json,sys
d = json.load(sys.stdin)
print('tag_count:', d['tag_count'])
print('bad_count:', d['bad_count'])
print('tags sample:', list(d['tags'].items())[:3])
"
```

ดู `tag_count` ต้องตรงกับจำนวน tag ใหม่ และ `bad_count` ต้องเป็น 0

---

## ข้อมูลอ้างอิง

### ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|------|---------|
| `/home/mintpower/lab/k3s/tools/opc_reader_final.groovy` | Groovy script หลัก (แก้ที่นี่) |
| `/home/mintpower/lab/k3s/tools/browse_opc.py` | Browse NodeId จาก Prosys |
| `/home/mintpower/lab/k3s/tools/gen_300tags.py` | Generate tag list อัตโนมัติ |
| `/home/mintpower/lab/k3s/milo-jars/` | Eclipse Milo JARs (backup บน host) |

### Processor / Service IDs (ณ 2026-05-06)

| ชื่อ | ID |
|------|-----|
| ExecuteGroovyScript (OPC Reader) | `fb9e2d81-019d-1000-f255-9b25076647d6` |
| PublishKafka | `fb9e5838-019d-1000-1592-de95686c8a58` |
| Kafka3ConnectionService | `fb9d89e0-019d-1000-bde2-1078a57cae47` |

> **หมายเหตุ:** ID เหล่านี้จะเปลี่ยนถ้า NiFi pod restart และ flow.json.gz ถูก reset  
> ดู ID ปัจจุบันด้วยคำสั่งใน 3.1

### NiFi Credentials

| ค่า | ข้อมูล |
|-----|---------|
| URL | `https://10.85.3.104:31444` |
| Username | `admin` |
| Password | `Nifi@mintpower2024!` |

### Kafka Bootstrap

```
kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092
```

### OPC UA Namespace

Prosys OPC UA Simulation Server ใช้ **namespace 3 (ns=3)**  
- Default tags: `ns=3;i=1001` ถึง `ns=3;i=1007` (Counter, Random, Sawtooth, ...)  
- Custom tags: `ns=3;i=2001` เป็นต้นไป

---

## ตัวอย่าง: เพิ่ม Tag จาก 307 → 310 Tags

```bash
# 1. แก้ไข script
nano /home/mintpower/lab/k3s/tools/opc_reader_final.groovy

# เพิ่มบรรทัดใน NODE_DEFS (ก่อนบรรทัด ] ที่ปิด list):
#     ["New_Tag_01", 3, 3001],
#     ["New_Tag_02", 3, 3002],
#     ["New_Tag_03", 3, 3003],

# แก้ DEVICE_ID บรรทัด 17:
#     DEVICE_ID = "opc-prosys-310tags"

# 2. Deploy
python3 - << 'EOF'
# (วาง deploy script จากขั้นตอน 3.2)
EOF

# 3. ตรวจสอบหลัง 30 วินาที
kubectl exec -n dmz kafka-cluster-broker-0 -c kafka -- bash -c \
  "timeout 5 bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
   --topic opc-raw-data --max-messages 1 2>/dev/null" | \
   python3 -c "import json,sys; d=json.load(sys.stdin); print('tags:', d['tag_count'])"
```

---

## สิ่งที่ต้องระวัง

1. **NodeId ต้องตรงกับที่ Prosys กำหนด** — ถ้า NodeId ผิด ค่าจะเป็น `null` และ `bad_count > 0`
2. **อย่า restart NiFi pod ระหว่าง deploy** — รอให้ script deploy เสร็จก่อน
3. **NiFi จะ reconnect อัตโนมัติ** หลัง stop/start processor ไม่ต้องรีสตาร์ท pod
4. **Groovy script ถูก cache** — stop processor ก่อน update script ทุกครั้ง (deploy script ทำให้อัตโนมัติแล้ว)
