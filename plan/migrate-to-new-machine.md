# แผนย้ายระบบไปเครื่องใหม่ (Offline / No Git)

**วันที่วางแผน:** 2026-05-09  
**ระบบปัจจุบัน:** mintpower (10.85.3.104) + mintserver (10.85.3.100)  
**เป้าหมาย:** ย้าย k3s data platform ทั้งระบบไปเครื่องใหม่แบบ offline ไม่ใช้ git

---

## ภาพรวม

```
เครื่องเดิม                        เครื่องใหม่
────────────────                   ────────────────
mintpower (k3s host)    ──copy──►  new-k3s-host
mintserver (OPC UA)     ──copy──►  new-opc-server (หรือเครื่องเดิม)
```

ไม่ใช้ `git clone` — ย้ายด้วย **Deployment Package** (folder/tar.gz) ผ่าน USB หรือ SCP

---

## Spec เครื่องใหม่ (ต่ำสุด)

| รายการ | ต่ำสุด | เครื่องปัจจุบัน |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 |
| RAM | 32 GB | 32 GB (ใช้ 48%) |
| Storage | NVMe ≥ 200 GB | NVMe |
| CPU | 4 core | — |
| Network | เชื่อมถึง OT zone | 10.85.3.x |
| User | user ไม่ใช่ root, มี sudo | mintpower |

---

## ส่วนที่ 1 — สร้าง Deployment Package (ทำบนเครื่องเดิม)

### โครงสร้าง Package

```
k3s-deploy-package/
├── install/                    # Container images + k3s binary (~5.1 GB)
│   ├── k3s
│   ├── k3s-airgap-images-amd64.tar.gz
│   ├── akhq-image.tar
│   ├── grafana-image.tar
│   ├── influxdb-image.tar
│   ├── minio-images.tar
│   ├── nifi-image.tar
│   ├── openmaint-images.tar
│   ├── postgres-image.tar
│   ├── strimzi-images.tar
│   ├── strimzi-0.43.0/
│   ├── telegraf-image.tar
│   ├── trino-image.tar
│   ├── busybox-image.tar
│   └── install.sh
├── bin/
│   └── helm
├── manifests/                  # YAML ทั้งหมด (phase1–5 + openmaint)
│   ├── phase1/
│   ├── phase2/
│   ├── phase3/
│   ├── phase4/
│   └── phase5/
├── tools/                      # Scripts ที่ยังใช้งาน
│   ├── openmaint_bridge.py
│   ├── opc_reader_final.groovy
│   ├── deploy_opc_script.py
│   └── browse_opc.py
├── scripts/
│   └── setup-nifi-core-flow.sh
├── milo-jars/                  # Eclipse Milo JARs (4.1 MB) — NiFi Edge ต้องการ
├── packages/
│   └── kafka-python/           # Python package สำหรับ openmaint-bridge (airgap)
├── plan/                       # Documentation
├── update/
│   └── guide-v4.html           # คู่มือฉบับสมบูรณ์
├── STATUS.md
└── README.md
```

### Script สร้าง Package

```bash
#!/bin/bash
# รันบน mintpower — สร้าง deployment package
set -e

PKG_DIR="$HOME/k3s-deploy-package"
K3S_DIR="/home/mintpower/lab/k3s"

rm -rf "$PKG_DIR" && mkdir -p "$PKG_DIR"

# copy ทุกส่วน
cp -r "$K3S_DIR/install"       "$PKG_DIR/"
cp -r "$K3S_DIR/bin"           "$PKG_DIR/"
cp -r "$K3S_DIR/manifests"     "$PKG_DIR/"
cp -r "$K3S_DIR/tools"         "$PKG_DIR/"
cp -r "$K3S_DIR/scripts"       "$PKG_DIR/"
cp -r "$K3S_DIR/milo-jars"     "$PKG_DIR/"
cp -r "$K3S_DIR/plan"          "$PKG_DIR/"
cp    "$K3S_DIR/STATUS.md"     "$PKG_DIR/"
cp    "$K3S_DIR/README.md"     "$PKG_DIR/"

# copy update/ เฉพาะ guide-v4
mkdir -p "$PKG_DIR/update"
cp "$K3S_DIR/update/guide-v4.html"          "$PKG_DIR/update/"
cp "$K3S_DIR/update/guide-start-stop-opc.md" "$PKG_DIR/update/"
cp "$K3S_DIR/update/guide-change-opc-tags.md" "$PKG_DIR/update/"

# copy kafka-python package (airgap)
mkdir -p "$PKG_DIR/packages"
cp -r /usr/local/lib/python3.12/dist-packages/kafka \
      /usr/local/lib/python3.12/dist-packages/kafka_python-2.3.1.dist-info \
      "$PKG_DIR/packages/kafka-python/"

# ลบ cache ที่ไม่จำเป็น
find "$PKG_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "Package size: $(du -sh $PKG_DIR | cut -f1)"
echo "Done: $PKG_DIR"
```

### อัด tar.gz (optional — ถ้าโอนผ่าน USB)

```bash
tar -czf ~/k3s-deploy-package.tar.gz -C ~ k3s-deploy-package/
# ขนาดประมาณ 4-5 GB หลัง compress
```

---

## ส่วนที่ 2 — ติดตั้งบนเครื่องใหม่ (k3s host)

### ขั้นตอน 0 — เตรียมเครื่อง

```bash
# สร้าง user (ถ้ายังไม่มี)
sudo adduser mintpower
sudo usermod -aG sudo mintpower

# สร้าง directory โครงสร้างเหมือนเดิม
sudo mkdir -p /mnt/nvme-storage/{influxdb,grafana,minio,nifi-core,nifi-edge,openmaint,postgres}
sudo chown -R mintpower:mintpower /mnt/nvme-storage

# copy package เข้าเครื่อง (เลือกวิธีใดวิธีหนึ่ง)
# USB: cp -r /media/usb/k3s-deploy-package ~/lab/k3s
# SCP: scp -r user@old-host:~/k3s-deploy-package ~/lab/k3s
# tar: tar -xzf k3s-deploy-package.tar.gz -C ~/lab/ && mv ~/lab/k3s-deploy-package ~/lab/k3s
```

### ขั้นตอน 1 — ปรับ IP ให้ตรงกับเครื่องใหม่

**ต้องแก้ทุกครั้ง** ก่อน apply manifests:

```bash
NEW_K3S_IP="x.x.x.x"       # IP เครื่อง k3s ใหม่
NEW_OPC_IP="x.x.x.x"        # IP เครื่อง OPC UA (mintserver ใหม่)
STORAGE_PATH="/mnt/nvme-storage"   # path storage บนเครื่องใหม่

# 1. persistent-volumes.yaml — hostPath
sed -i "s|/mnt/nvme-storage|$STORAGE_PATH|g" \
  ~/lab/k3s/manifests/phase1/persistent-volumes.yaml

# 2. nifi-edge.yaml — hostAliases (IP ของ mintserver)
sed -i "s|10.85.3.100|$NEW_OPC_IP|g" \
  ~/lab/k3s/manifests/phase4/nifi-edge.yaml  # ปรับชื่อไฟล์ตามจริง

# 3. openmaint_bridge.py — Kafka bootstrap
sed -i "s|10.85.3.104|$NEW_K3S_IP|g" \
  ~/lab/k3s/tools/openmaint_bridge.py
```

### ขั้นตอน 2 — ติดตั้ง k3s (airgap)

```bash
cd ~/lab/k3s/install

# copy airgap images ไปที่ k3s ต้องการ
sudo mkdir -p /var/lib/rancher/k3s/agent/images/
sudo cp k3s-airgap-images-amd64.tar.gz /var/lib/rancher/k3s/agent/images/

# ติดตั้ง k3s binary
sudo cp k3s /usr/local/bin/k3s
sudo chmod +x /usr/local/bin/k3s

# ติดตั้ง helm
sudo cp ../bin/helm /usr/local/bin/helm
sudo chmod +x /usr/local/bin/helm

# run installer (airgap mode)
INSTALL_K3S_SKIP_DOWNLOAD=true bash install.sh
sudo systemctl enable --now k3s
```

### ขั้นตอน 3 — Load container images

```bash
cd ~/lab/k3s/install

# load ทุก image เข้า containerd
for img in *.tar; do
  echo "Loading $img..."
  sudo k3s ctr images import "$img"
done

# ตรวจสอบ
sudo k3s ctr images list | grep -E "nifi|kafka|grafana|influx|minio|openmaint|trino|telegraf"
```

### ขั้นตอน 4 — Deploy manifests (ลำดับสำคัญ)

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
cd ~/lab/k3s/manifests

# Phase 1 — Namespaces + Storage
kubectl apply -f phase1/namespaces.yaml
kubectl apply -f phase1/storage-class.yaml
kubectl apply -f phase1/persistent-volumes.yaml

# Phase 2 — Kafka (Strimzi)
# ติดตั้ง Strimzi CRD ก่อน
kubectl apply -f ../install/strimzi-0.43.0/install/cluster-operator/ -n dmz
sleep 30  # รอ operator ready
kubectl apply -f phase2/kafka-pvc.yaml
kubectl apply -f phase2/kafka-cluster.yaml
kubectl wait --for=condition=Ready kafka/kafka-cluster -n dmz --timeout=300s
kubectl apply -f phase2/kafka-topics.yaml
kubectl apply -f phase2/akhq.yaml

# Phase 3 — InfluxDB + Grafana + Telegraf
kubectl apply -f phase3/influxdb-secret.yaml
kubectl apply -f phase3/influxdb-pvc.yaml
kubectl apply -f phase3/pv-influxdb2.yaml
kubectl apply -f phase3/influxdb.yaml
kubectl apply -f phase3/grafana-pvc.yaml
kubectl apply -f phase3/grafana-config.yaml
kubectl apply -f phase3/grafana-dashboard-combined.yaml
kubectl apply -f phase3/grafana.yaml
kubectl apply -f phase3/telegraf-config.yaml
kubectl apply -f phase3/telegraf.yaml

# Phase 4 — MinIO + NiFi Core + Trino
kubectl apply -f phase4/minio-secret.yaml
kubectl apply -f phase4/minio-pvc.yaml
kubectl apply -f phase4/minio.yaml
kubectl apply -f phase4/minio-init-job.yaml
kubectl apply -f phase4/nifi-core-pvc.yaml
kubectl apply -f phase4/nifi-core.yaml
kubectl apply -f phase4/trino-config.yaml
kubectl apply -f phase4/trino-partition-sync.yaml

# Phase 5 — NiFi Edge
kubectl apply -f phase5/   # ปรับตาม folder จริง

# OpenMAINT
kubectl apply -f openmaint/ # ปรับตาม folder จริง
```

### ขั้นตอน 5 — ตั้งค่า NiFi Edge (Groovy script)

```bash
# deploy Groovy script ขึ้น NiFi Edge
python3 ~/lab/k3s/tools/deploy_opc_script.py
```

ถ้า NiFi pod ไม่มี flow → ดู `update/guide-start-stop-opc.md`

### ขั้นตอน 6 — ติดตั้ง systemd services

```bash
# copy kafka-python ไปยัง system Python
sudo cp -r ~/lab/k3s/packages/kafka-python/kafka \
           ~/lab/k3s/packages/kafka-python/kafka_python-2.3.1.dist-info \
           /usr/local/lib/python3.12/dist-packages/

# ติดตั้ง openmaint-bridge service
sudo cp ~/lab/k3s/tools/openmaint_bridge.py /opt/openmaint_bridge.py
sudo tee /etc/systemd/system/openmaint-bridge.service > /dev/null <<'EOF'
[Unit]
Description=OpenMAINT Bridge — Kafka opc-raw-data to OpenMAINT Alarm + CorrectiveMaint
After=network.target

[Service]
Type=simple
User=mintpower
ExecStart=/usr/bin/python3 /opt/openmaint_bridge.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now openmaint-bridge
sudo systemctl status openmaint-bridge
```

### ขั้นตอน 7 — ติดตั้ง Prosys OPC UA บนเครื่อง OT ใหม่

ดูขั้นตอนละเอียดใน `update/guide-start-stop-opc.md`

```bash
# บน OPC server ใหม่ (mintserver ใหม่)
# copy prosys-start.sh + ไฟล์ Prosys
# ติดตั้ง systemd service prosys-opc

sudo systemctl enable --now prosys-opc
sudo systemctl status prosys-opc
```

---

## ส่วนที่ 3 — ย้าย Data (ถ้าต้องการ)

### InfluxDB

```bash
# บนเครื่องเดิม — backup
kubectl exec -n it <influxdb-pod> -- \
  influx backup /tmp/influx-backup -t influx-super-secret-token-mintpower
kubectl cp it/<influxdb-pod>:/tmp/influx-backup ./influx-backup/

# บนเครื่องใหม่ — restore
kubectl cp ./influx-backup/ it/<influxdb-pod-new>:/tmp/influx-backup
kubectl exec -n it <influxdb-pod-new> -- \
  influx restore /tmp/influx-backup -t influx-super-secret-token-mintpower
```

### PostgreSQL (OpenMAINT)

```bash
# บนเครื่องเดิม
kubectl exec -n it <postgres-pod> -- \
  pg_dump -U cmdbuild cmdbuild > openmaint-backup.sql

# บนเครื่องใหม่
kubectl cp openmaint-backup.sql it/<postgres-pod-new>:/tmp/
kubectl exec -n it <postgres-pod-new> -- \
  psql -U cmdbuild cmdbuild < /tmp/openmaint-backup.sql
```

### MinIO

```bash
# ใช้ mc mirror (ถ้าเครื่องเชื่อมกันได้)
mc alias set old http://10.85.3.104:30901 minioadmin minioadmin
mc alias set new http://<NEW_IP>:30901 minioadmin minioadmin
mc mirror old/opc-datalake new/opc-datalake
```

---

## ส่วนที่ 4 — ตรวจสอบหลัง Deploy

```bash
# 1. ดู pods ทั้งหมด
kubectl get pods -A

# 2. ตรวจ Kafka — มีข้อมูลไหล
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic opc-raw-data --max-messages 3 --timeout-ms 10000

# 3. ตรวจ Telegraf lag
kubectl exec -n dmz kafka-cluster-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group telegraf-opc-consumer

# 4. ตรวจ openmaint-bridge
sudo systemctl status openmaint-bridge
sudo journalctl -u openmaint-bridge -f

# 5. เปิด Grafana
# http://<NEW_IP>:30300   admin / admin2026
```

---

## สิ่งที่ต้องปรับทุกครั้งที่ย้ายเครื่อง

| รายการ | ไฟล์ | ค่าที่ต้องเปลี่ยน |
|---|---|---|
| Storage path | `manifests/phase1/persistent-volumes.yaml` | hostPath ทุก PV |
| OPC server IP | `manifests/phase4/nifi-edge.yaml` | `hostAliases` |
| Kafka bootstrap | `tools/openmaint_bridge.py` | `bootstrap_servers` |
| Grafana URL | `tools/openmaint_bridge.py` | `OPENMAINT_URL` |
| STATUS.md | `STATUS.md` | IP ทุกบรรทัด |

---

## ขนาด Package โดยประมาณ

| ส่วน | ขนาด |
|---|---|
| Container images (`install/`) | ~5.1 GB |
| `milo-jars/` | 4.1 MB |
| `kafka-python` package | ~500 KB |
| manifests + tools + docs | < 10 MB |
| **รวมก่อน compress** | **~5.1 GB** |
| **รวมหลัง tar.gz** | **~4.5 GB** |
