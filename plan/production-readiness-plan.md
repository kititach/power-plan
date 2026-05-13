# Production Readiness Plan

> แผนเปลี่ยนระบบจาก **Pilot/PoC** เป็น **Production-grade** + workflow การ update อย่างปลอดภัย
> สร้างเมื่อ: 2026-05-11

---

## 🎯 เป้าหมาย

ทำให้ระบบ k3s Data Platform พร้อมใช้งานจริงในระดับ production:
- มี **safe update workflow** — แก้แล้วไม่พัง / พังแล้วกู้คืนได้
- มี **backup + DR** — ข้อมูลไม่หายเมื่อ disk/เครื่องพัง
- มี **alerting** — รู้ทันทีเมื่อเกิดปัญหา
- มี **security baseline** — credentials ไม่ leak

---

## 📊 สถานะปัจจุบัน (2026-05-11)

```
PoC ──► [Pilot] ──► Pre-Prod ──► Production ──► Mission-Critical
 ✅       👈 อยู่ตรงนี้
```

**ระดับการใช้งานที่ปลอดภัยตอนนี้:**
- ✅ Pilot line, shadow run, dashboard monitoring
- ⚠️ Non-critical alerting (manual response)
- ❌ Safety-critical control, compliance audit (FDA/ISO)

---

## 🖥️ Resource Inventory (2026-05-11)

### เครื่อง k3s (mintpower 10.85.3.104)
| Resource | Total | ใช้อยู่ | เหลือ |
|---|---|---|---|
| CPU | 28 cores | 1.5 cores (5%) | 26.5 cores |
| RAM | 31 GB | 14.5 GB (47%) | **16 GB** |
| Disk NVMe `/mnt/nvme-storage` | 469 GB | 4 GB (1%) | **441 GB** |
| Disk Root `/` | 219 GB | 52 GB (25%) | 157 GB |

### TrueNAS (10.80.4.4) — Backup target ✅
| รายการ | ค่า |
|---|---|
| Version | TrueNAS **SCALE 25.04.2.6** (Linux) |
| Network | LAN 0.6ms latency, routed via 10.85.3.254 |
| SSH access | ✅ user `truenas_admin` (port 22 open) |
| Web UI | https://10.80.4.4 / https://truenas.khitkon.com |
| SMB (port 445) | ✅ enabled |
| NFS (port 2049) | ❌ disabled (เปิดได้) |
| S3 / iSCSI | ❌ disabled (เปิดได้) |

**ZFS Pools:**
| Pool | Size | Available | ใช้สำหรับ |
|---|---|---|---|
| **MainData** | 10.9 TB | **7.13 TB** | Data, backup |
| FastApps | 928 GB | 898 GB | TrueNAS apps |
| boot-pool | 31 GB | 28 GB | OS |

**Datasets ที่มีอยู่:** `MainData/storage-share`, `MainData/media` (ว่างทั้งคู่)

### สรุป Resource Decision

| Phase | Hardware เพิ่ม | เหตุผล |
|---|---|---|
| **A (Backup, Alert, Secret)** | ❌ ไม่ต้องเพิ่ม | TrueNAS เป็น backup target ได้เลย |
| **B (Monitoring, Retention, Cert)** | ❌ ไม่ต้องเพิ่ม | RAM/Disk เหลือพอ |
| **C (HA)** | ⚠️ เครื่องที่ 2 (optional) | ถ้าต้องการ true HA, single-node ทำไม่ได้ |

---

# Part 1 — Safe Update Workflow (Airgap, No Remote Git)

> ระบบนี้ทำงาน airgap และ **ไม่มีการ push ขึ้น git remote** — ใช้ local versioning + snapshot folder แทน

## หลักการ: แยก Environment ตาม Blast Radius

```
[Workspace สำเนา] ──► [Staging Namespace] ──► [Production]
   แก้/ทดสอบ            ลองรันใน cluster        ของจริง
   พังได้                ห้ามพังนาน              ห้ามพังเด็ดขาด
```

## 1.1 Local Versioning Strategy (ไม่ใช้ git remote)

ใช้โครงสร้าง folder + snapshot แทน git branch:

```
/home/mintpower/lab/k3s/
├── manifests/              ← ของจริง (ที่ apply ลง cluster)
├── manifests-staging/      ← copy ไว้แก้/ทดสอบ
└── snapshots/              ← ย้อนกลับได้
    ├── 2026-05-11-stable/  ← snapshot รายสัปดาห์ (manifests + config)
    ├── 2026-05-18-stable/
    └── pre-<change>/       ← snapshot ก่อน change ใหญ่
```

**กฎ:**
- `manifests/` = ตรงกับ cluster ที่รันจริง 100% เสมอ
- ก่อนแก้อะไร → `cp -a manifests/ snapshots/pre-<ชื่อ-change>-$(date +%F)/`
- Snapshot รายสัปดาห์อัตโนมัติ (CronJob) — เก็บ rolling 8 สัปดาห์
- ใช้ local git ได้ (commit แบบ local-only) แต่ไม่ใช่ข้อบังคับ

## 1.2 Namespace Isolation (Staging ใน Cluster เดียวกัน)

ระบบเป็น single-node ไม่มี cluster แยก — ใช้ namespace แยกแทน:

```
Production:  dmz, it
Staging:     dmz-dev, it-dev   (สำหรับ change ใหญ่ เท่านั้น)
```

**ใช้เมื่อ:**
- Test image version ใหม่ (NiFi, Kafka upgrade)
- Test schema change ก่อน apply prod
- Test threshold rule ใหม่ที่อาจกระทบของจริง

**ไม่ต้องใช้เมื่อ:**
- แก้ Grafana dashboard
- แก้ threshold value
- เพิ่ม alert rule

## 1.3 ระดับการเปลี่ยนแปลง — Decision Matrix

| Risk Level | ตัวอย่าง | วิธี | Snapshot ก่อน? |
|---|---|---|---|
| **🟢 Low** | Grafana panel, threshold value, ConfigMap edit | แก้ตรง prod | YAML 1 ไฟล์ |
| **🟡 Medium** | Image version, env var, resource limit | Copy → test ใน dev namespace → swap prod | YAML ทั้ง phase |
| **🔴 High** | DB schema, Kafka topic config, breaking change | Staging namespace + PVC snapshot | DB dump + manifests ทั้งหมด |
| **🟣 Critical** | Storage migration, k3s upgrade, HA change | Full DR plan + downtime window | Full system backup |

## 1.4 Standard Update Procedure

### 🟢 Low Risk
```bash
# 1. Backup ไฟล์เดิม
cp manifests/phase3/grafana-dashboard-combined.yaml \
   snapshots/pre-edit-$(date +%F-%H%M)/

# 2. แก้และ apply
vim manifests/phase3/grafana-dashboard-combined.yaml
kubectl apply -f manifests/phase3/grafana-dashboard-combined.yaml

# 3. Verify (ดู pod restart, ดู dashboard เปิดได้)
kubectl get pod -n it -l app=grafana
```

### 🟡 Medium Risk
```bash
# 1. Snapshot phase ที่จะแก้
SNAP=snapshots/pre-telegraf-upgrade-$(date +%F)
mkdir -p $SNAP
cp -a manifests/phase3/ $SNAP/
kubectl get deployment telegraf -n it -o yaml > $SNAP/telegraf-live.yaml

# 2. สร้าง dev copy + แก้
cp -a manifests/phase3 manifests-staging/phase3-telegraf-test
vim manifests-staging/phase3-telegraf-test/telegraf.yaml

# 3. Apply ลง dev namespace (เปลี่ยน namespace เป็น it-dev)
kubectl create ns it-dev 2>/dev/null
sed 's/namespace: it/namespace: it-dev/' \
  manifests-staging/phase3-telegraf-test/telegraf.yaml \
  | kubectl apply -f -

# 4. ทดสอบ ~30 นาที (ดู lag, ดู log)
kubectl logs -n it-dev deploy/telegraf

# 5. ถ้าเวิร์ค → copy ทับ manifests/ + apply prod
cp manifests-staging/phase3-telegraf-test/telegraf.yaml manifests/phase3/
kubectl apply -f manifests/phase3/telegraf.yaml

# 6. ลบ dev + ลบ staging copy
kubectl delete ns it-dev
rm -rf manifests-staging/phase3-telegraf-test
```

### 🔴 High Risk
```bash
# 1. Snapshot ทั้งระบบ
SNAP=snapshots/pre-openmaint-schema-$(date +%F)
mkdir -p $SNAP
cp -a manifests/ $SNAP/manifests/
bash scripts/backup-all.sh $SNAP/data/   # (ต้องสร้าง — ดู Part 2)

# 2. Snapshot PVC (rsync เพราะ k3s ใช้ local-path)
sudo rsync -a /mnt/nvme-storage/k8s-pv/postgres/ \
  /mnt/nvme-storage/backup/postgres-pre-change-$(date +%F)/

# 3. Apply ใน staging namespace + ทดสอบ
# 4. ถ้าเวิร์ค → maintenance window → apply prod
# 5. Verify ทุก consumer + dashboard ปกติ ~ 1 ชม.
# 6. ถ้าผ่าน — keep snapshot ไว้ 30 วัน
```

## 1.5 Rollback Procedure

```bash
# วิธีที่ 1 — Manifest rollback (เร็วที่สุดสำหรับ config)
cp snapshots/pre-<change>/manifests/phase3/telegraf.yaml manifests/phase3/
kubectl apply -f manifests/phase3/telegraf.yaml

# วิธีที่ 2 — Deployment rollback (ใช้ k8s revision history)
kubectl rollout undo deployment/<name> -n <ns>
kubectl rollout history deployment/<name> -n <ns>   # ดู revision

# วิธีที่ 3 — PVC rollback (data restoration)
kubectl scale deploy/<name> -n <ns> --replicas=0
sudo rsync -a --delete \
  /mnt/nvme-storage/backup/<snapshot>/ \
  /mnt/nvme-storage/k8s-pv/<name>/
kubectl scale deploy/<name> -n <ns> --replicas=1

# วิธีที่ 4 — Full restore (กรณีเลวร้ายสุด)
bash scripts/restore-all.sh snapshots/<date>/
```

## 1.6 Snapshot Automation

CronJob รัน weekly snapshot อัตโนมัติ:

```bash
# /etc/cron.weekly/k3s-snapshot
WEEK=$(date +%F)
SNAP=/home/mintpower/lab/k3s/snapshots/$WEEK-stable
mkdir -p $SNAP
cp -a /home/mintpower/lab/k3s/manifests $SNAP/
kubectl get all,cm,secret,pvc -A -o yaml > $SNAP/cluster-state.yaml

# Retention: เก็บ 8 สัปดาห์ล่าสุด
ls -dt /home/mintpower/lab/k3s/snapshots/*-stable | tail -n +9 | xargs rm -rf
```

## 1.7 Change Log (แทน git commit message)

เก็บ log ทุก change ที่ `snapshots/CHANGELOG.md`:

```markdown
## 2026-05-11
- [Low] แก้ Grafana panel threshold เป็น 95°C (จาก 90°C)
- [Medium] Upgrade Telegraf 1.28 → 1.30, test ใน it-dev 30 นาที ผ่าน
- Snapshot: snapshots/pre-telegraf-upgrade-2026-05-11/
```

---

# Part 2 — Production Roadmap

## 📋 Backlog ตามลำดับความสำคัญ

### 🔴 Phase A — Critical (ทำก่อน, ~1 สัปดาห์)

#### ✅ A1. Backup อัตโนมัติ — 3-Tier Strategy (เสร็จแล้ว 2026-05-11)

**Strategy: 3-Tier Backup (Implemented)**
```
┌─ Tier 1: Hot (local NVMe) ────────────────────┐
│  /mnt/nvme-storage/backup/                    │
│  Retention: 7 วัน — ใช้จริง 2.1 GB            │
└────────────────┬──────────────────────────────┘
                 │ rsync over SSH (รายวัน 02:00)
┌────────────────▼──────────────────────────────┐
│ Tier 2: Warm (TrueNAS HDD 10.80.4.4)          │
│ /mnt/MainData/k3s-backup/data/                │
│ Retention: 30 วัน — ใช้จริง 874 MB (LZ4 -58%) │
└────────────────┬──────────────────────────────┘
                 │ ZFS snapshot (auto)
┌────────────────▼──────────────────────────────┐
│ Tier 3: Archive (ZFS snapshot บน TrueNAS)     │
│ Retention: 90 วัน daily + 12 monthly          │
└───────────────────────────────────────────────┘
```

**งานย่อย:**
- [x] **TrueNAS prep**: dataset `MainData/k3s-backup` (500 GB quota, LZ4)
- [x] **TrueNAS user**: `k3s-backup` (uid 3001, password disabled, key only)
- [x] **SSH key**: `~/.ssh/k3s-backup-truenas` (ed25519, passwordless)
- [x] `scripts/backup/backup-all.sh` — orchestrator
- [x] PostgreSQL: pg_dumpall → 21 MB ✅
- [x] InfluxDB: influx backup → 242 MB ✅
- [x] MinIO: rsync host PVC → 1.6 GB ✅
- [x] NiFi: flow.json.gz + conf → 32 KB ✅
- [x] Manifests + cluster state → 904 KB ✅
- [x] `scripts/backup/sync-to-truenas.sh` — Tier 1 → Tier 2 (100 MB/s)
- [x] **Restore drill 5/5 ผ่าน** (smoke test ทุก component)
- [x] **systemd timer**: รัน 02:00 ทุกวัน (next: Tue 2026-05-12 02:04)
- [ ] TrueNAS snapshot policy (Tier 3) — pending (ทำใน Web UI)

**ผลการทดสอบ:** Full backup รัน 41 วินาที, ขนาดรวม Tier 1 = 2.1 GB, Tier 2 = 874 MB

**Acceptance:** ✅ All 5 components backup + restore drill pass

**ไฟล์ที่สร้าง:**
- `scripts/backup/` — 12 ไฟล์ (scripts + systemd + README)
- `plan/truenas-backup-setup.md` — คู่มือสร้าง TrueNAS dataset/user (SSH + Web UI)

---

#### ✅ A2. Alerting + Email (เสร็จแล้ว 2026-05-11)

**Components:**
- **Mailhog** — Mock SMTP สำหรับทดสอบ (ก่อนพร้อมใช้ Gmail/Outlook จริง)
- **Grafana Unified Alerting** — rules + contact point + policies provisioned
- **SMTP Secret** — `grafana-smtp` (plug-and-play เปลี่ยน host/user ทีเดียว)

**Alert Rules (6 rules):**

🔴 Critical Infrastructure:
- [x] OPC ingest stopped (count < 1 / 2m) — severity: critical
- [x] OPC tag count low (< 307) — severity: warning
- [x] OPC bad value high (mean > 10 / 5m) — severity: warning

🟡 Data Quality:
- [x] Boiler temp critical (> 95°C) — severity: critical
- [x] Hydraulic pressure (< 50 or > 160 bar) — severity: critical
- [x] Pump vibration (> 10 mm/s ISO 10816) — severity: warning

**Notification Policy:**
- `severity=critical` → instant, repeat 1h
- `severity=warning` → group 1m, repeat 6h
- Mute window 01:50-02:30 (เลี่ยง backup job)

**ผลการทดสอบ:**
- ✅ Alert engine running ("Sending alerts to local notifier")
- ✅ Mailhog received email (total: 3 in test)
- ✅ Manual contact point test → success
- ⚠️ บาง Flux query ยัง DatasourceError — tune ทีหลังผ่าน UI ได้

**Acceptance:** ✅ ปิด NiFi Edge → alert fire ภายใน 2 นาที (มี email ใน Mailhog)

**Plug-in SMTP จริง (5 นาที):**
```bash
kubectl create secret generic grafana-smtp -n it \
  --from-literal=smtp-host=smtp.gmail.com:587 \
  --from-literal=smtp-user=your@gmail.com \
  --from-literal=smtp-password='app-password' \
  ... --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deploy/grafana -n it
```

**ไฟล์ที่สร้าง:**
- `manifests/phase7-alerting/` — 4 ไฟล์ (mailhog + secret + provisioning + README)
- patch `manifests/phase3/grafana.yaml` — เพิ่ม SMTP env + alerting mount

**Access Points (เพิ่ม):**
- Mailhog UI: http://10.85.3.104:30825

**ยังต้องทำ (Polish ต่อ ไม่ blocking):**
- [ ] Tune Flux queries ให้ตรง bucket schema (แก้ผ่าน Grafana UI)
- [ ] เพิ่ม rule: pod down, disk > 85%, node down (ต้องใช้ Prometheus → Phase B1)
- [ ] OpenMAINT bridge → Slack/email เมื่อสร้าง CorrectiveMaint
- [ ] Runbook ต่อ alert (ใครรับ, แก้อย่างไร)

#### A3. Credentials Management (1-2 วัน)
**ทำไม:** Password อยู่ใน YAML + STATUS.md → ใครเห็นก็เข้าได้

**งานย่อย:**
- [ ] เลือกเครื่องมือ: **Sealed Secrets** (แนะนำ — airgap ทำงานได้) หรือ SOPS
- [ ] ย้าย password ทั้งหมดเข้า Secret
- [ ] ลบ plain text ใน STATUS.md → ใส่ใน `STATUS-private.md` (gitignore)
- [ ] Rotate password ทั้งหมด (Grafana, NiFi, InfluxDB, MinIO, PostgreSQL)
- [ ] เอกสาร: ใครได้สิทธิ์เข้าอะไรบ้าง

**Acceptance:** `git log -p | grep -i password` ไม่เจออะไรเลย

---

### 🟡 Phase B — Important (สัปดาห์ที่ 2, ~5-7 วัน)

#### B1. Monitoring Stack (2-3 วัน)
- [ ] Prometheus + Node Exporter (k3s metrics)
- [ ] kube-state-metrics
- [ ] Grafana dashboard: k3s cluster, node, pod resource
- [ ] Loki + Promtail (log aggregation)
- [ ] Alert: disk > 80%, RAM > 90%, pod CrashLoop

#### B2. Data Retention Policy (1 วัน)
- [ ] InfluxDB: retention 30 วัน raw + 1 ปี downsampled
- [ ] MinIO: lifecycle rule ลบ partition > 90 วัน
- [ ] PostgreSQL: archive table เก่า > 1 ปี
- [ ] Backup retention: 7d daily + 4 weekly + 12 monthly

#### B3. Internal CA + Cert จริง (1 วัน)
- [ ] สร้าง internal CA (`cfssl` หรือ `step-ca`)
- [ ] ออก cert ให้ NiFi UI, Grafana, MinIO
- [ ] Distribute CA cert ไปทุกเครื่อง client

---

### 🟢 Phase C — Production Hardening (สัปดาห์ที่ 3, ~1 สัปดาห์)

#### C1. HA & Redundancy (3-5 วัน)
- [ ] เพิ่ม worker node 1-2 ตัว (k3s agent)
- [ ] PostgreSQL replication (primary + standby)
- [ ] Kafka เพิ่ม broker เป็น 3 ตัว + replication factor 3
- [ ] etcd snapshot อัตโนมัติ (k3s built-in)
- [ ] Document failover procedure

#### C2. DR Drill (1 วัน)
- [ ] เตรียมเครื่องสำรอง / VM
- [ ] ทดสอบกู้คืนจาก backup เต็มรูปแบบ
- [ ] วัด RTO (Recovery Time Objective) และ RPO (Recovery Point Objective)
- [ ] เอกสาร DR runbook

#### C3. Apply Automation (Local, ไม่ใช้ git CI/CD) (1-2 วัน)
- [ ] Script `scripts/apply-safe.sh` — snapshot ก่อน apply อัตโนมัติ
- [ ] Pre-apply check: `kubectl diff` + `--dry-run=server`
- [ ] Post-apply verify: รอ pod ready + ตรวจ Kafka lag
- [ ] Logging ทุก apply ลง `snapshots/CHANGELOG.md` อัตโนมัติ
- [ ] (Optional) Gitea internal — ถ้าต้องการ local git server เฉพาะ versioning

---

### 🔵 Phase D — Future / Optional

- [ ] OPC Scenario B/C (MQTT, OPC PubSub) — ดู `plan/OPC-plan.md`
- [ ] Scale to 10k tags — ดู `plan/scale-10k-tags-plan.md`
- [ ] Migrate to new machine — ดู `plan/migrate-to-new-machine.md`
- [ ] Compliance documentation (ISO 27001 baseline)
- [ ] Penetration test internal

---

## 📅 Timeline สรุป

| สัปดาห์ | Phase | ผลลัพธ์ |
|---|---|---|
| **1** | A1, A2, A3 | ปลอดภัยพอใช้ในโรงงานสาขา |
| **2** | B1, B2, B3 | สบายใจในระดับ pre-production |
| **3** | C1, C2, C3 | เรียก "production-grade" ได้เต็มปาก |
| **ต่อไป** | D | ขยาย scale, compliance |

---

## ✅ Definition of Production-Ready

ระบบจะเรียก **production-ready** ได้เมื่อ:

- [x] Pipeline เสถียร > 30 วันต่อเนื่อง
- [x] **Backup อัตโนมัติ + test restore สำเร็จ** (A1 done 2026-05-11)
- [x] **Alerting ครอบคลุม critical path + รับ notification ภายใน 2 นาที** (A2 done 2026-05-11)
- [ ] Credentials ไม่อยู่ใน plain text (A3)
- [ ] Monitoring k3s + log aggregation (B1)
- [ ] Data retention policy active (B2)
- [ ] HA อย่างน้อยใน stateful service หลัก (C1)
- [ ] DR drill ผ่าน (RTO < 4 ชม., RPO < 1 ชม.) (C2)
- [ ] Runbook สำหรับ incident หลัก ๆ
- [ ] Update workflow มี approval + rollback ชัดเจน

**Progress: 3/10 (30%)** — เสร็จเฟสที่อันตรายสุด (data loss + ไม่รู้ปัญหา)

---

## 📜 Progress Log

### 2026-05-11
- ✅ **A1 Backup System** — 3-tier (NVMe → TrueNAS → ZFS snapshot)
  - TrueNAS dataset + user + SSH key setup
  - 5 backup scripts (postgres, influxdb, minio, nifi, manifests)
  - sync-to-truenas, restore-drill, backup-all orchestrator
  - systemd timer (daily 02:00)
  - Tested end-to-end (41s full backup, 5/5 restore drill pass)

- ✅ **A2 Alerting + Email** — Grafana Unified Alerting + Mailhog
  - Mailhog mock SMTP (port 30825 UI)
  - 6 alert rules (3 critical infra + 3 data quality)
  - Notification policy (critical/warning routing)
  - SMTP secret (plug-and-play for Gmail/Outlook)
  - Tested: email delivered to Mailhog

- 📝 **Plan Updates**
  - `plan/production-readiness-plan.md` (this file)
  - `plan/truenas-backup-setup.md` (TrueNAS setup guide, SSH + Web UI)
  - `manifests/phase7-alerting/` (4 ไฟล์)
  - `scripts/backup/` (12 ไฟล์)
  - Snapshot: `snapshots/pre-phase7-alerting-2026-05-11/`

---

## 🚀 ถัดไปทำอะไร

แนะนำเริ่มจาก **Phase A1 (Backup)** ก่อน เพราะ:
1. ความเสี่ยงสูงสุดตอนนี้ — ระบบทำงานดี แต่ข้อมูลไม่ได้ backup
2. เป็นรากฐานของทุก phase ถัดไป (ต้อง backup ได้ก่อนจะกล้า upgrade)
3. ใช้เวลาน้อย (1-2 วัน) เห็นผลทันที

```bash
# ขั้นแรกที่จะทำ
git checkout -b feature/backup-system
mkdir -p scripts/backup
# สร้าง backup-postgres.sh, backup-influxdb.sh, backup-minio.sh
# สร้าง CronJob YAML
# Test restore
```
