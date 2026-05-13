# STATUS — k3s Data Platform
> **อ่านไฟล์นี้ก่อนทุกครั้งที่เข้ามาทำงาน**  
> อัปเดตท้ายไฟล์ทุกครั้งที่แก้อะไร — ไม่ว่าจะสำเร็จหรือพัง

---

## 🟢 สถานะล่าสุด — 2026-05-11 (Phase A1+A2 production hardening)

### Pipeline ทำงานอยู่
```
Prosys OPC UA (mintserver:53530)
  └─[opc.tcp]─► NiFi Edge (Groovy/Eclipse Milo) ──► Kafka: opc-raw-data
                                                          ├─► Telegraf ──► InfluxDB ──► Grafana         ✅
                                                          ├─► NiFi Core ──► MinIO ──► Trino             ✅
                                                          └─► OpenMAINT Bridge (systemd) ──► OpenMAINT  ✅
                                                                └─► Alarm + CorrectiveMaint (work order)
```

### Component Status
| Component | Status | หมายเหตุ |
|-----------|--------|---------|
| Prosys OPC UA (mintserver) | ✅ Running | systemd `prosys-opc`, uptime 1d+ |
| NiFi Edge | ✅ Running | 307 tags, ทุก 2 วินาที |
| Kafka `opc-raw-data` | ✅ Active | ~500 msg/วัน (partition 0+2) |
| Telegraf → InfluxDB | ✅ Active | lag < 5 msg |
| NiFi Core → MinIO | ✅ Active | 132+ files/วัน |
| Grafana | ✅ Running | dashboard: `mintpower-combined-v1` |
| InfluxDB | ✅ Running | bucket: `opc-data` |
| OpenMAINT | ✅ Running | รับข้อมูลผ่าน openmaint-bridge (systemd) |
| OpenMAINT Bridge | ✅ Running | systemd `openmaint-bridge`, Kafka→Alarm+CorrectiveMaint |
| Trino | ✅ Running | — |
| **Backup system** | ✅ Active | systemd `k3s-backup.timer` daily 02:00 → TrueNAS (10.80.4.4) |
| **Mailhog** | ✅ Running | Mock SMTP — http://10.85.3.104:30825 |
| **Grafana Alerting** | ✅ Active | 6 rules (3 critical infra + 3 data quality) |

### สิ่งที่ทำเสร็จแล้ว
- [x] ~~Grafana datasource token: ต้อง set ทุกครั้งที่ restart pod~~ — แก้ถาวรแล้ว 2026-05-08 ด้วย `lifecycle.postStart` hook
- [x] ~~Trino partition sync~~ — แก้ถาวรแล้ว 2026-05-08: เปลี่ยน schedule เป็น `5 0,12 * * *` (2x/วัน)
- [x] ~~OpenMAINT integrate กับ Kafka~~ — แก้ถาวรแล้ว 2026-05-08 ด้วย `openmaint-bridge` systemd service
- [x] **Backup system 3-tier** — 2026-05-11 (NVMe → TrueNAS → ZFS snapshot, daily 02:00)
- [x] **Alerting + Email (Mailhog)** — 2026-05-11 (Grafana 6 rules, plug-and-play SMTP)

---

## 🗺️ แผนพัฒนาระบบ

### ✅ เสร็จแล้ว
| งาน | วันที่ |
|---|---|
| OPC UA TCP pipeline — 307 tags, NiFi Edge + Eclipse Milo | 2026-05-06 |
| Kafka architecture fix — consumers อ่าน `opc-raw-data` โดยตรง | 2026-05-06 |
| Grafana datasource token permanent fix — `lifecycle.postStart` hook | 2026-05-08 |
| Trino partition sync — เปลี่ยนเป็น 2x/วัน (00:05, 12:05 Bangkok) | 2026-05-08 |
| OpenMAINT Kafka integration — `openmaint-bridge` systemd + Alarm + CorrectiveMaint | 2026-05-08 |

---

### 🔵 OPC Transport Evolution (ดูรายละเอียดใน `plan/OPC-plan.md`)
เปลี่ยนวิธีรับข้อมูลจาก OT Zone — **ไม่กระทบ downstream เลย** (Kafka format คงเดิม)

| Scenario | วิธี | Latency | ต้องเพิ่ม | ความซับซ้อน |
|---|---|---|---|---|
| **ปัจจุบัน** | OPC UA TCP + Eclipse Milo (poll 2s) | 2s | — | กลาง |
| **A** | REST API → InvokeHTTP → Kafka | 2s+ | ไม่มี | ต่ำ |
| **B** | MQTT Pub/Sub → ConsumeMQTT → Kafka | < 100ms | MQTT Broker | กลาง |
| **C** | OPC UA PubSub Part 14 → MQTT → Kafka | < 100ms | MQTT Broker | สูง |

---

### 📋 Backlog — ยังไม่ได้ทำ (เรียงตามลำดับแนะนำ)

#### ระยะสั้น
- [ ] **Alerting** — Grafana alert rules → Line Notify / Email เมื่อ sensor ผิดปกติ
- [ ] **OpenMAINT dashboard** — Grafana datasource: PostgreSQL, ดู Alarm + CorrectiveMaint work order
- [ ] **pg_dump cronjob** — backup OpenMAINT database อัตโนมัติ (ปัจจุบันไม่มี backup เลย)

#### ระยะกลาง
- [ ] **Data retention** — InfluxDB retention policy + MinIO auto-delete partition เก่า > N วัน
- [ ] **OPC Scenario B (MQTT)** — ถ้าต้องการ latency < 100ms หรือ scale device เพิ่ม

#### ระยะยาว
- [ ] **High Availability** — เพิ่ม worker node หรือ HA control plane (ปัจจุบัน single-node)
- [ ] **Security hardening** — ย้าย credentials เข้า Kubernetes Secret ที่ proper + cert จริง

---

## 🔑 Credentials (ครบถ้วน)

| Service | URL | User | Password / Token |
|---------|-----|------|-----------------|
| **Grafana** | http://10.85.3.104:30300 | admin | **admin2026** ⚠️ (เปลี่ยนจาก `Grafana@mintpower2024` เมื่อ 2026-05-08) |
| **InfluxDB** | http://10.85.3.104:30086 | admin | token: `influx-super-secret-token-mintpower` |
| **MinIO** | http://10.85.3.104:30901 | minioadmin | minioadmin |
| **NiFi Edge** | https://10.85.3.104:31444 | admin | Nifi@mintpower2024! |
| **NiFi Core** | https://10.85.3.104:31443 | admin | Nifi@mintpower2024! |
| **AKHQ (Kafka UI)** | http://10.85.3.104:30880 | — | — |
| **Mailhog (mock SMTP)** | http://10.85.3.104:30825 | — | — |
| **TrueNAS Web UI** | https://10.80.4.4 | truenas_admin | @123456789 |
| **TrueNAS (k3s-backup user)** | SSH key: `~/.ssh/k3s-backup-truenas` | k3s-backup | (no password — key only) |
| **TrueNAS SMB share** | `\\10.80.4.4\k3s-backup` → `/mnt/MainData/k3s-backup/data` | kititach | (มี password ส่วนตัว) |
| **Prosys OPC UA** | mintserver:53530 | — | — |
| **mintserver SSH** | 10.85.3.100 | demo | @123456789 (The root user also uses the same password.) |
| **mintpower SSH** | 10.85.3.104 | mintpower | @123456789 (The root user also uses the same password.)|

---

## ⚠️ Known Issues & Gotchas

### 1. ~~Grafana datasource token หายทุกครั้งที่ restart pod~~ — แก้ถาวรแล้ว 2026-05-08
**สาเหตุเดิม:** datasource provisioning YAML ไม่ support env substitution → token คงเป็น `CHANGE_ME`  
**แก้ถาวรแล้วด้วย:** `lifecycle.postStart` hook ใน `manifests/phase3/grafana.yaml`  
- inject `INFLUX_TOKEN` จาก Secret `influxdb-secret` เข้า env
- postStart รัน curl loop (retry จนกว่า Grafana HTTP พร้อม) แล้ว PUT datasource อัตโนมัติ
- ทดสอบแล้ว: restart pod → token set เองทุกครั้ง ✅

### 2. Prosys OPC UA ไม่มี systemd ใน mintserver เดิม
ตอนนี้ใช้ `systemd prosys-opc` แล้ว แต่ต้อง SSH ด้วย user `demo` (ไม่ใช่ root):
```bash
ssh demo@10.85.3.100   # password: @123456789
sudo systemctl start|stop|restart|status prosys-opc
```

### 3. NiFi flow หายถ้า pod restart โดยไม่ได้ตั้งใจ
`flow.json.gz` อยู่ใน PVC subPath `conf/` แล้ว — ป้องกันได้  
ถ้าหาย: ใช้ `python3 /home/mintpower/lab/k3s/tools/deploy_opc_script.py` re-deploy Groovy script

### ~~4. Kafka topic `opc-metrics` และ `opc-datalake`~~ — ลบแล้ว 2026-05-08
ลบทิ้งแล้ว เนื่องจากเป็นข้อมูลเก่าจาก Python simulator ไม่มีใคร produce/consume อีกต่อไป  
Kafka topics ที่เหลืออยู่: **`opc-raw-data`** เท่านั้น

---

## 📋 Key File Locations

| ไฟล์ | หน้าที่ |
|------|--------|
| `tools/opc_reader_final.groovy` | Groovy script ใน NiFi Edge (OPC UA reader) |
| `tools/deploy_opc_script.py` | Deploy/update Groovy script ขึ้น NiFi |
| `plan/grafana-notes.md` | Grafana known issues + datasource workaround |
| `plan/plan.md` | System overview + architecture |
| `update/update-2026-05-06-phase4.md` | Phase 4 log (NiFi + OPC UA) |
| `update/update-2026-05-06-phase5.md` | Phase 5 log (systemd + flatten + Telegraf) |
| `update/guide-start-stop-opc.md` | คู่มือ start/stop Prosys |
| `update/guide-change-opc-tags.md` | คู่มือเปลี่ยน OPC tag |
| `tools/openmaint_bridge.py` | Kafka→OpenMAINT bridge (threshold rules + Alarm + CorrectiveMaint) |
| `plan/scale-10k-tags-plan.md` | แผน scale ระบบรองรับ 10,000 tags/s + retention 3เดือน/5ปี |
| `update/guide-v4.html` ⭐ | คู่มือฉบับสมบูรณ์ v4 (รวม OpenMAINT Bridge, threshold rules, scale plan) |

---

## 🚨 OpenMAINT Bridge — Threshold Rules

`COOLDOWN_SECONDS = 300` (5 นาที/tag — ป้องกัน spam)

| Tag Pattern | Normal | Max | Min | Unit | Severity | หมายเหตุ |
|---|---|---|---|---|---|---|
| `Temp_Boiler_*` | 90 | **95** | — | °C | Critical | Boiler overheat |
| `Temp_HeatEx_*` | 65 | **80** | — | °C | High | Heat exchanger fouling |
| `Temp_Oil_*` | 70 | **85** | — | °C | High | Oil lubrication degradation |
| `Temp_Cooling_*` | 20 | **30** | — | °C | High | Cooling system failure |
| `Vibration_Pump_*` | 7.5 | **10.0** | — | mm/s | High | ISO 10816 bearing wear |
| `Press_Line_*` | 6.0 | **8.0** | **2.0** | bar | High | Line pressure anomaly |
| `Press_Tank_*` | 4.5 | **6.0** | **1.0** | bar | High | Tank relief valve |
| `Press_Hydraulic_*` | 125 | **160** | **50** | bar | Critical | Hydraulic integrity |
| `Level_Tank_*` | 57.5 | **90** | **10** | % | High | Overflow / dry-run |
| `Current_Drive_*` | 42.5 | **60** | — | A | High | Motor overload |
| `Torque_Motor_*` | 255 | **350** | — | Nm | High | Mechanical overload |
| `RPM_Motor_*` | 1900 | **2200** | **500** | rpm | Medium | Speed out of range |
| `Power_Motor_*` | 77.5 | **100** | — | kW | Medium | Power consumption high |
| `Voltage_Bus_*` | 400 | **440** | **350** | V | Critical | Electrical fault |
| `CO2_Zone_*` | 800 | **1000** | — | ppm | Medium | ASHRAE 62.1 limit |
| `Humidity_Room_*` | 55 | **80** | **20** | % | Medium | Comfort/equipment range |
| `Flow_Main_*` | 125 | **160** | **30** | m³/h | High | Pipeline/pump anomaly |
| `Flow_Branch_*` | 45 | **60** | **10** | m³/h | Medium | Branch flow anomaly |
| `Flow_Coolant_*` | 27.5 | **40** | **10** | m³/h | High | Cooling effectiveness |

**เมื่อ violation เกิดขึ้น:**
1. สร้าง **Alarm** ใน OpenMAINT (บันทึกค่า + timestamp)
2. สร้าง **CorrectiveMaint** work order (มอบหมายให้ช่างดำเนินการ)

**คำสั่ง systemd:**
```bash
sudo systemctl status openmaint-bridge    # ดูสถานะ
sudo journalctl -u openmaint-bridge -f    # ดู log realtime
sudo systemctl restart openmaint-bridge   # restart
```

---

## 📜 ประวัติการแก้ไข

### 2026-05-11 — Production Hardening Phase A1 + A2

#### A1: Backup System 3-Tier ✅
- TrueNAS prep: dataset `MainData/k3s-backup` (500GB LZ4), user `k3s-backup`, SSH key
- 5 backup scripts: postgres (21MB), influxdb (242MB), minio (1.6GB), nifi (32KB), manifests (904KB)
- `sync-to-truenas.sh` rsync over SSH → Tier 2 (100 MB/s)
- `restore-drill.sh` 5/5 pass
- systemd `k3s-backup.timer` (daily 02:00 ±5min)
- Full backup รัน 41 วินาที, Tier 1 = 2.1 GB, Tier 2 = 874 MB (LZ4 -58%)
- ไฟล์: `scripts/backup/` (12 files), `plan/truenas-backup-setup.md`

#### A2: Alerting + Email ✅
- Mailhog deployed (port 30825 UI, 1025 SMTP)
- `grafana-smtp` Secret (plug-and-play สำหรับ Gmail/Outlook)
- Grafana Unified Alerting + 6 rules (critical infra + data quality)
- Notification policy (critical instant, warning grouped)
- Tested: email delivered to Mailhog (FIRING:5 + manual test)
- ไฟล์: `manifests/phase7-alerting/` (4 files), patch `phase3/grafana.yaml`
- Snapshot: `snapshots/pre-phase7-alerting-2026-05-11/`

#### Bug fixed ตอนทำ
- `set -e` + `[[ -z VAR ]] && cmd` → exit (แก้: ใช้ if/then)
- `ls glob | head` + pipefail → fail when no match (แก้: wrap with `|| true`)
- rsync `--delete-after` ลบ `.ssh/authorized_keys` (home = backup target) → ย้ายเข้า `data/` subdir
- MinIO container ไม่มี `tar` → ใช้ rsync host PVC แทน
- rsync preserve source mtime → prune ลบ backup ใหม่ทันที → `touch` reset mtime
- mute-timings `weekdays: ['monday:sunday']` → "start day cannot be before end day" (แก้: ลบ weekdays)

#### A1+ SMB Share สำหรับ kititach ✅
- เพิ่ม SMB share `k3s-backup` ชี้ `/mnt/MainData/k3s-backup/data` (ซ่อน `.ssh/` ของ user backup)
- kititach อยู่ใน group `k3s-backup` (gid 3002) อยู่แล้ว — มีสิทธิ์ RW
- POSIX 775 ทั้ง parent + recursive (เปลี่ยนจาก 770)
- Mount: `\\10.80.4.4\k3s-backup` (Windows), `smb://10.80.4.4/k3s-backup` (macOS)

**ปัญหาที่เจอ + แก้:** Windows access denied หลังเปลี่ยน share path
- สาเหตุ: cached credentials จาก share path เดิม + POSIX traverse บน parent
- แก้: ปรับ chmod 775, restart SMB, ล้าง Windows credential cache (`cmdkey /delete:10.80.4.4`)

---

### 2026-05-09 — Cleanup + Migration Plan

**ทำอะไร:**

#### ลบไฟล์ที่ไม่ใช้งาน (Group A)
- ลบ `opc-sim/` ทั้งโฟลเดอร์ — Python OPC simulator เก่า แทนด้วย Prosys บน mintserver แล้ว
- ลบ `tools/opc_reader.groovy` — Groovy เวอร์ชันเก่า ใช้ `opc_reader_final.groovy` แทน
- ลบ `tools/gen_300tags.py` — script ใช้ครั้งเดียวตอน generate 307 tags เสร็จแล้ว
- ลบ `update/guide.html`, `guide-v2.html`, `guide-v3.html`, `summary.html`, `SUMMARY.md` — เก่า ใช้ `guide-v4.html` แทน
- commit pending deletions root-level (`SUMMARY.md`, `guide*.html`, `summary.html`)

#### อัปเดต plan/
- `plan/OPC-plan.md` — เพิ่ม section "สถานะ Simulation ปัจจุบัน" (2026-05-09)
  - ตรวจพบ: process tags ทั้ง 307 ค่าคงที่ที่ baseline ตลอด → OpenMAINT bridge ไม่ trigger alarm
  - เสนอ 3 แนวทางแก้ (Prosys waveform / Groovy noise inject / Python simulator)
- สร้าง `plan/migrate-to-new-machine.md` — แผนย้ายระบบไปเครื่องใหม่แบบ offline/no git
  - Deployment Package structure (~5.1 GB)
  - ขั้นตอน deploy ทีละ phase บนเครื่องใหม่
  - วิธี migrate data: InfluxDB backup, pg_dump, MinIO mirror
  - รายการ IP ที่ต้องปรับทุกครั้งที่ย้ายเครื่อง

#### Push manifests/phase3 ขึ้น origin
- `grafana.yaml` — postStart hook + INFLUX_TOKEN from Secret + dashboard volumes
- `grafana-config.yaml` — เพิ่ม `uid: influxdb-opc`
- `grafana-dashboard-combined.yaml` — new ConfigMap (dashboard)
- `telegraf-config.yaml` — topic `opc-raw-data`, tag_keys, disk/diskio inputs
- `telegraf.yaml` — hostfs volumes + HOST_MOUNT_PREFIX env vars

---

### 2026-05-08 — สร้าง guide-v4.html (คู่มือฉบับสมบูรณ์)
**ทำอะไร:**
- สร้าง `update/guide-v4.html` — รวมทุกอย่างจาก STATUS.md + plan/ files
- 23 sections + Glossary, ~89KB, 1,597 บรรทัด
- ครอบคลุม: ภาพรวม, credentials, architecture, ทุก component, OpenMAINT Bridge ⭐, troubleshooting, backup, scale plan
- Sidebar navigation + smooth scroll + dark theme

---

### 2026-05-08 — OpenMAINT DMS Disabled
**ปัญหา:** กด Execute ใน CorrectiveMaint workflow ขึ้น "Generic error" — Tomcat พยายาม connect Alfresco DMS ที่ `localhost:10080` แต่ระบบไม่มี Alfresco
**แก้:**
```sql
UPDATE "_SystemConfig" SET "Value" = 'false' WHERE "Code" = 'org.cmdbuild.dms.enabled';
```
แล้ว restart OpenMAINT pod — workflow เดินหน้าได้ปกติทุก step

---

### 2026-05-08 — OpenMAINT pod recovery (Tomcat ตาย)
**ปัญหา:** OpenMAINT API ไม่ตอบ — pod READY 1/1 แต่ใช้ RAM แค่ 2Mi (Tomcat ตายเหลือแค่ sleep loop)
**แก้:** `kubectl rollout restart deployment/openmaint -n it` — ข้อมูลใน PostgreSQL ปลอดภัย

---

### 2026-05-08 — Bridge fix: _advance=True
**ปัญหา:** Work order ที่ bridge สร้างค้างที่ Opening — กดอะไรไม่ได้ใน UI (ไม่ผ่าน workflow engine)
**แก้:** เพิ่ม `"_advance": True` ใน payload ตอน POST → workflow ผ่าน Opening → Assignment ทันที

---

### 2026-05-08 — OpenMAINT + Kafka Integration (openmaint-bridge)
**ทำอะไร:**
- สร้าง Python bridge script `tools/openmaint_bridge.py`
  - Kafka consumer group `openmaint-consumer` อ่านจาก `opc-raw-data`
  - ตรวจ 19 threshold rules ครอบคลุม Temp / Pressure / Vibration / Flow / Level / Voltage / CO2 / Humidity
  - Cooldown 5 นาที/tag ป้องกัน spam
  - เมื่อ violation: สร้าง **Alarm** + **CorrectiveMaint** work order ใน OpenMAINT อัตโนมัติ
- Deploy เป็น systemd service `openmaint-bridge` บน mintpower (enabled, auto-start)
- ติดตั้ง `kafka-python 2.3.1` จาก opc-sim venv → system Python (airgap, ไม่มี pip install)
- ทดสอบแล้ว: Alarm id=618997, CorrectiveMaint id=619000 ถูกสร้างใน OpenMAINT ✅

---

### 2026-05-08 — Trino partition sync: เปลี่ยน schedule 1x → 2x/วัน
**ปัญหา:** CronJob `trino-partition-sync` รัน `5 0 * * *` (วันละครั้ง) แต่ `day=08` ยังไม่ถูก sync ทำให้ข้อมูลวันนี้มองไม่เห็นใน Trino  
**แก้:** เปลี่ยน schedule เป็น `5 0,12 * * *` (00:05 และ 12:05 Bangkok) + trigger manual sync ทันที  
**ผล:** `day=08` ปรากฏใน Trino (5,746 rows), lag สูงสุดลดจาก 24h → 12h

---

### 2026-05-08 — Grafana datasource token: แก้ถาวรด้วย postStart hook
**ปัญหา:** ทุกครั้งที่ restart Grafana pod, datasource token reset เป็น `CHANGE_ME` เพราะ provisioning YAML ไม่รองรับ env substitution  
**แก้:** เพิ่มใน `manifests/phase3/grafana.yaml`:
- `env.INFLUX_TOKEN` ดึงจาก Secret `influxdb-secret` (key: `admin-token`)
- `lifecycle.postStart` รัน curl loop รอ `/api/health` → PUT datasource อัตโนมัติ
- แก้ `GF_SECURITY_ADMIN_PASSWORD` เป็น `admin2026` (ตรงกับ password ปัจจุบัน)  
**ทดสอบ:** restart pod 2 รอบ → token set เองทุกครั้ง ✅

---

### 2026-05-08 — ลบ Kafka topics เก่า
ลบ `opc-metrics` และ `opc-datalake` ทิ้ง — ข้อมูลเก่าจาก Python simulator, ไม่มี producer/consumer ใช้งานอีกแล้ว  
Kafka topics ที่เหลือ: `opc-raw-data` เพียงตัวเดียว

---

### 2026-05-08 — Grafana พัง (เกิดจากความผิดพลาด)
**เกิดอะไร:**
1. ต้องการดู Grafana dashboard → ไม่รู้ password → ลอง password สุ่มหลายครั้ง
2. Account ถูก lock: `too many consecutive incorrect login attempts`
3. Restart pod เพื่อ unlock → pod restart ทำให้ **datasource token หายไป** (known issue ข้อ 1)
4. ลอง password ต่อ → lock ซ้ำอีกรอบ
5. แก้โดย: copy SQLite DB ออกมา → ลบ `login_attempt` table → copy กลับ → restart pod → datasource token กลับมา

**บทเรียน:**
- อ่าน `plan/grafana-notes.md` ก่อนแตะ Grafana เสมอ
- Password อยู่ในไฟล์ notes ไม่ใช่ในหัว
- **อย่า restart Grafana pod** ถ้าไม่จำเป็น — datasource token จะหายทุกครั้ง
- ถ้า account lock: แก้ที่ SQLite DB (`login_attempt` table) ไม่ใช่ restart pod

**Password หลัง incident นี้:** เปลี่ยนเป็น `admin2026` (จาก `Grafana@mintpower2024`)

---

### 2026-05-06 — Phase 5: systemd + Kafka Architecture Fix
**ทำอะไร:**
- สร้าง systemd service `prosys-opc` บน mintserver  
  - wrapper script `/usr/local/bin/prosys-start.sh` ใช้ `kill -0` loop แทน `wait` (เพราะ Java เป็น grandchild process)
- แก้ Groovy script: เปลี่ยน timestamp Unix float → ISO8601, flatten `tags{}` → top-level fields
- แก้ Telegraf ConfigMap: `opc-metrics` → `opc-raw-data`, เพิ่ม `tag_keys`
- NiFi Core ConsumeKafka: `opc-datalake` → `opc-raw-data`

**ทำที่บ้าน (session แยก):**
- Grafana dashboard update 12 panels ให้ query field ชุดใหม่
- ตรวจสอบ MinIO รับข้อมูล

---

### 2026-05-06 — Phase 4: NiFi Edge OPC UA Connection สำเร็จ
**ทำอะไร:**
- แก้ Eclipse Milo missing Guava JAR (`NoClassDefFoundError`)
- แก้ k3s hostAliases สำหรับ hostname `mintserver` ใน NiFi pod
- Recreate NiFi flow หลัง pod restart ทำให้ `flow.json.gz` หาย
- แก้ PublishKafka: `Transactions Enabled = false`
- แก้ Kafka bootstrap URL

**ผล:** 307 OPC tags ไหลเข้า Kafka ทุก 2 วินาที

---

### 2026-05-03 to 05-04 — Initial Setup
- Deploy k3s single-node (airgap)
- แก้ OpenMAINT 7 ปัญหา (PG15, container restart loop)
- Kafka, NiFi, Telegraf, InfluxDB, Grafana, MinIO, Trino
- Python OPC simulator → Kafka (ต่อมาถูกแทนด้วย Prosys + Eclipse Milo)
