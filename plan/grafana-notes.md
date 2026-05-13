# Grafana — Notes & Known Issues

## Current State

**Dashboard:** System & OPC — mintpower
- UID: `mintpower-combined-v1`
- Folder: mintpower
- URL: `http://10.85.3.104:30300/d/mintpower-combined-v1`
- Provisioned via ConfigMap `grafana-dashboards` (ns: it)

| Row | Panels |
|---|---|
| System Overview | Stat: CPU % · Memory % · Disk / % · Disk NVMe % |
| CPU & Memory | Timeseries: CPU Usage % · Memory Used % |
| Storage | Timeseries: Disk Used % (/ และ /mnt/nvme-storage) · Disk I/O (Bytes/s) |
| OPC Sensors | Temperature · Pressure · Flow · Vibration & RPM · Power/Voltage/Current |

**Grafana Admin**
- User: `admin` / Password: `Grafana@mintpower2024`

---

## ~~Known Issue — Datasource Token ต้อง Set ทุกครั้งที่ Restart~~ — แก้ถาวรแล้ว 2026-05-08

**แก้แล้วด้วย `lifecycle.postStart` hook ใน `manifests/phase3/grafana.yaml`:**
- inject `INFLUX_TOKEN` จาก Secret `influxdb-secret` (key: `admin-token`) เข้า env
- postStart รัน curl loop: retry จนกว่า `/api/health` ตอบ 200 แล้ว PUT datasource
- ทดสอบแล้ว: restart pod → token set เองทุกครั้ง ✅

**ถ้าต้อง set token ด้วยมือ (emergency fallback):**
```bash
INFLUX_TOKEN=$(kubectl get secret -n it influxdb-secret -o jsonpath='{.data.admin-token}' | base64 -d)
curl -s -u "admin:admin2026" \
  -X PUT -H "Content-Type: application/json" \
  -d "{\"id\":1,\"uid\":\"influxdb-opc\",\"name\":\"InfluxDB-OPC\",\"type\":\"influxdb\",\"access\":\"proxy\",\"url\":\"http://influxdb.it.svc.cluster.local:8086\",\"jsonData\":{\"version\":\"Flux\",\"organization\":\"mintpower-org\",\"defaultBucket\":\"opc-data\",\"tlsSkipVerify\":true},\"secureJsonData\":{\"token\":\"${INFLUX_TOKEN}\"},\"isDefault\":true}" \
  "http://10.85.3.104:30300/api/datasources/1"
```

---

## Files ที่เกี่ยวข้อง

| File | หน้าที่ |
|---|---|
| `manifests/phase3/grafana.yaml` | Deployment + Service (NodePort 30300) |
| `manifests/phase3/grafana-config.yaml` | Datasource provisioning + grafana.ini |
| `manifests/phase3/grafana-dashboard-combined.yaml` | Dashboard provisioner + dashboard JSON |
| `manifests/phase3/grafana-pvc.yaml` | PVC สำหรับ Grafana data |

---

## Changelog

### 2026-05-07 — รวม Dashboard + เพิ่ม CPU/Memory
- รวม "Storage Monitor" และ "OPC Sensor Dashboard" เป็น dashboard เดียว (`mintpower-combined-v1`)
- เพิ่ม panels: CPU Usage %, Memory Used % (จาก Telegraf `cpu` และ `mem` measurement)
- เพิ่ม dashboard provisioning ผ่าน ConfigMap แทนการ import ด้วยมือ
- เพิ่ม `uid: influxdb-opc` ใน datasource provisioner เพื่อให้ dashboard JSON อ้างอิง UID ได้แน่นอน
- **พบปัญหา:** dashboard ไม่มีข้อมูล → สาเหตุคือ token `CHANGE_ME` ใน datasource provisioning ไม่ถูก inject → แก้ชั่วคราวผ่าน Grafana API
