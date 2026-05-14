# Phase 7 — Alerting

> Grafana Unified Alerting + Mailhog (mock SMTP) + Email contact point
> สร้างเมื่อ: 2026-05-11

---

## องค์ประกอบ

| ไฟล์ | หน้าที่ |
|---|---|
| `01-mailhog.yaml` | Mock SMTP server + Web UI (NodePort 30825) สำหรับทดสอบเมล |
| `02-grafana-smtp-secret.yaml` | SMTP credentials — เริ่มต้นชี้ไปที่ mailhog, แก้เมื่อพร้อมใช้ Gmail/Outlook |
| `03-grafana-alerting-provisioning.yaml` | Contact points + Policies + Mute timings + Alert rules |

Grafana deployment patch (เพิ่มใน `phase3/grafana.yaml`):
- SMTP env vars จาก `grafana-smtp` Secret
- Mount alerting ConfigMap ที่ `/etc/grafana/provisioning/alerting/`
- Enable Unified Alerting

---

## วิธีติดตั้ง

```bash
# 1. Apply phase 7
kubectl apply -f manifests/phase7-alerting/

# 2. Re-apply Grafana (เพื่อให้รับ env vars + alerting mount ใหม่)
kubectl apply -f manifests/phase3/grafana.yaml

# 3. รอ Grafana ready
kubectl rollout status -n it deploy/grafana --timeout=120s
kubectl rollout status -n it deploy/mailhog --timeout=60s
```

---

## ทดสอบ

### 1. ตรวจ Grafana โหลด alerting provisioning ครบ
```bash
# Login
curl -s -u admin:admin2026 http://10.85.3.104:30300/api/v1/provisioning/alert-rules | jq '. | length'
# ควรได้ >= 5 (rules ที่เราใส่ไว้)

curl -s -u admin:admin2026 http://10.85.3.104:30300/api/v1/provisioning/contact-points | jq '.[].name'
# ควรเห็น: email-default, webhook-debug
```

### 2. ทดสอบส่งเมลผ่าน Mailhog
```bash
# Test เมลจาก Grafana UI:
# Configuration → Contact Points → email-default → Test
# หรือ:
curl -s -u admin:admin2026 \
  -X POST http://10.85.3.104:30300/api/alertmanager/grafana/config/api/v1/receivers/email-default/test \
  -H "Content-Type: application/json" -d '{}'

# เปิดดูใน Mailhog UI:
xdg-open http://10.85.3.104:30825
# (หรือเปิดใน browser เอง)
```

### 3. ทดสอบ alert rule ทำงาน
```bash
# Force fire alert โดยปิด NiFi Edge (จะทำให้ OPC ingest หยุด)
kubectl scale deploy/nifi-edge -n it --replicas=0

# รอ 2-3 นาที → alert "OPC ingest stopped" จะ fire → ส่งเมลเข้า Mailhog

# Restore
kubectl scale deploy/nifi-edge -n it --replicas=1
```

---

## เปลี่ยน SMTP จาก Mailhog → Gmail/Production

### Gmail (ต้องมี 2FA + App Password)

1. ไป https://myaccount.google.com/apppasswords สร้าง App Password
2. แก้ secret:
```bash
kubectl edit secret grafana-smtp -n it
```
หรือ:
```bash
kubectl create secret generic grafana-smtp -n it \
  --from-literal=smtp-host=smtp.gmail.com:587 \
  --from-literal=smtp-user=your-email@gmail.com \
  --from-literal=smtp-password='xxxx-xxxx-xxxx-xxxx' \
  --from-literal=smtp-from-address=your-email@gmail.com \
  --from-literal=smtp-from-name='k3s Alert' \
  --from-literal=smtp-skip-verify=false \
  --from-literal=smtp-starttls-policy=MandatoryStartTLS \
  --from-literal=alert-recipient=you@gmail.com \
  --dry-run=client -o yaml | kubectl apply -f -
```

3. แก้ recipient ใน contact point — `03-grafana-alerting-provisioning.yaml`:
```yaml
settings:
  addresses: you@gmail.com   # เปลี่ยนจาก ops@k3s.local
```
4. Re-apply + restart:
```bash
kubectl apply -f manifests/phase7-alerting/03-grafana-alerting-provisioning.yaml
kubectl rollout restart deploy/grafana -n it
```

5. ทดสอบ:
```bash
curl -s -u admin:admin2026 \
  -X POST http://10.85.3.104:30300/api/v1/provisioning/contact-points/uid/email_default/test \
  -H "Content-Type: application/json" -d '{}'
```

---

## Alert Rules ที่มี

### 🔴 Critical Infrastructure (`critical-infra` group)
| Rule | Threshold | Severity | For |
|---|---|---|---|
| OPC ingest stopped | count(opc_data, 2m) < 1 | critical | 1m |
| OPC tag count low | tag_count < 307 | warning | 3m |
| OPC bad value high | mean(bad_count, 5m) > 10 | warning | 5m |

### 🟡 Data Quality (`data-quality` group)
| Rule | Threshold | Severity | For |
|---|---|---|---|
| Boiler temp critical | max(Temp_Boiler_*) > 95°C | critical | 1m |
| Hydraulic pressure | <50 or >160 bar | critical | 1m |
| Pump vibration high | max(Vibration_Pump_*) > 10 mm/s | warning | 2m |

ขยาย rule เพิ่มได้ใน `03-grafana-alerting-provisioning.yaml` → `rules.yaml`

---

## Notification Policy

```
Default → email-default (group_wait 30s, repeat 4h)
├── severity=critical → email-default (instant, repeat 1h)
└── severity=warning  → email-default (group 1m, repeat 6h)
```

**Mute window:** 01:50-02:30 (เลี่ยงตอน backup job รัน)

---

## Access Points

| Service | URL | Credentials |
|---|---|---|
| Grafana | http://10.85.3.104:30300 | admin / admin2026 |
| Mailhog UI | http://10.85.3.104:30825 | (no auth) |
| Mailhog SMTP | `mailhog.it.svc.cluster.local:1025` | (in-cluster) |

---

## Troubleshooting

### Alert rule ไม่ปรากฏใน UI
- ดู log: `kubectl logs -n it deploy/grafana | grep -i alert`
- ตรวจ ConfigMap mount: `kubectl exec -n it deploy/grafana -- ls /etc/grafana/provisioning/alerting/`
- Force reload: `curl -X POST -u admin:admin2026 http://10.85.3.104:30300/api/admin/provisioning/alerting/reload`

### เมลไม่ถึง Mailhog
- ตรวจ SMTP config: `kubectl exec -n it deploy/grafana -- env | grep GF_SMTP`
- ตรวจ mailhog reachable: `kubectl exec -n it deploy/grafana -- nc -zv mailhog 1025`
- ดู log Grafana: `kubectl logs -n it deploy/grafana | grep -i smtp`

### Gmail "535-5.7.8 Username and Password not accepted"
- ใช้ **App Password** ไม่ใช่ password ปกติ
- ต้อง enable 2FA ก่อน
- ตรวจ user ตรงกับ `from-address` (Gmail บังคับ)

### Alert ฟ้อง "No Data" ตลอดเวลา
- ตรวจ datasource UID ใน rule (ต้องตรงกับ `influxdb-opc`)
- รัน query ใน Grafana Explore ก่อน — เห็นผลไหม
- ปรับ `noDataState` เป็น `OK` ถ้า bucket ว่างชั่วคราว

---

## Acceptance Test (Phase A2 Definition of Done)

- [ ] `kubectl apply -f manifests/phase7-alerting/` ผ่าน
- [ ] Mailhog UI เปิดได้ที่ http://10.85.3.104:30825
- [ ] Grafana → Alerting → Alert rules แสดง 6+ rules
- [ ] Contact point test → เมลเข้า Mailhog
- [ ] ปิด NiFi Edge → alert fire ใน 2 นาที → เมลเข้า Mailhog
- [ ] เปลี่ยน SMTP → Gmail (เมื่อมี credentials) → เมลเข้าจริง
