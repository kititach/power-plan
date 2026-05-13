# TrueNAS Backup Target — Setup Guide

> คู่มือสร้าง dataset + user + SSH key สำหรับ k3s backup บน TrueNAS SCALE
> เลือกได้ 2 แบบ: **SSH/CLI** (อัตโนมัติ, repeatable) หรือ **Web UI** (visual, สำหรับมือใหม่)
>
> สร้างเมื่อ: 2026-05-11 | ทดสอบบน TrueNAS SCALE 25.04.2.6

---

## 🎯 เป้าหมาย

สร้างพื้นที่ backup บน TrueNAS แยกเด็ดขาดจากของ user อื่น:

| รายการ | ค่า |
|---|---|
| Dataset | `MainData/k3s-backup` |
| Mount path | `/mnt/MainData/k3s-backup` |
| Quota | 500 GB |
| Compression | LZ4 (built-in, ฟรี) |
| User | `k3s-backup` (uid 3001, gid 3002) |
| Auth | SSH key only (password disabled) |
| Source key | `~/.ssh/k3s-backup-truenas` บน mintpower |

---

## ข้อมูลก่อนเริ่ม

| รายการ | ค่า |
|---|---|
| TrueNAS IP | `10.80.4.4` |
| TrueNAS admin | `truenas_admin` / `@123456789` |
| Web UI | https://10.80.4.4 หรือ https://truenas.khitkon.com |
| mintpower IP | `10.85.3.104` |
| ผู้ใช้บน mintpower | `mintpower` |

---

# 📘 วิธีที่ 1: SSH / CLI (อัตโนมัติ — แนะนำ)

## ข้อดี
- ✅ Reproducible — รัน script ซ้ำได้
- ✅ เร็ว (~1 นาที)
- ✅ บันทึก/version control ได้

## ข้อเสียที่ควรรู้
- ⚠️ ต้องเข้าใจ JSON / CLI
- ⚠️ ถ้าพิมพ์ผิด อาจสร้างของผิด

## Step 1.1 — Generate SSH Key บน mintpower

```bash
# สร้าง key เฉพาะสำหรับ backup (แยกจาก key อื่น)
ssh-keygen -t ed25519 -N "" \
  -C "k3s-backup@mintpower" \
  -f ~/.ssh/k3s-backup-truenas

# ดู public key (จะ paste ลง TrueNAS)
cat ~/.ssh/k3s-backup-truenas.pub
```

**ผลลัพธ์ที่ได้:**
- `~/.ssh/k3s-backup-truenas` — private key (เก็บไว้เครื่องเดียว, mode 600)
- `~/.ssh/k3s-backup-truenas.pub` — public key (paste ลง TrueNAS user)

## Step 1.2 — สร้าง Dataset ผ่าน TrueNAS API

```bash
# เก็บ public key ไว้ใช้ในขั้นถัดไป
PUBKEY=$(cat ~/.ssh/k3s-backup-truenas.pub)

# สร้าง dataset 500GB LZ4
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "midclt call pool.dataset.create '{
    \"name\": \"MainData/k3s-backup\",
    \"compression\": \"LZ4\",
    \"quota\": 536870912000,
    \"comments\": \"k3s backup target - 500GB quota\"
  }'"
```

**Parameters อธิบาย:**
| Field | ค่า | ความหมาย |
|---|---|---|
| `name` | `MainData/k3s-backup` | path เต็ม `<pool>/<dataset>` |
| `compression` | `LZ4` | บีบอัดอัตโนมัติ, ประหยัด ~30-50% |
| `quota` | `536870912000` | 500 GB = 500 × 1024³ bytes |
| `comments` | (string) | comment สำหรับ admin |

**Optional fields เพิ่มเติม:**
| Field | ค่า | ใช้เมื่อ |
|---|---|---|
| `encryption` | `true` | ต้องการ encryption at rest |
| `sync` | `STANDARD` / `ALWAYS` / `DISABLED` | ปรับ ZFS sync mode |
| `recordsize` | `131072` (128K) | ปรับสำหรับ workload (default OK) |
| `atime` | `OFF` | ปิด access time → IO ลดลง |

## Step 1.3 — สร้าง User k3s-backup

```bash
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "midclt call user.create '{
    \"username\": \"k3s-backup\",
    \"full_name\": \"k3s Backup User\",
    \"group_create\": true,
    \"home\": \"/mnt/MainData/k3s-backup\",
    \"home_create\": false,
    \"shell\": \"/usr/bin/bash\",
    \"password_disabled\": true,
    \"sshpubkey\": \"$PUBKEY\",
    \"smb\": false
  }'"
```

**Parameters อธิบาย:**
| Field | ค่า | เหตุผล |
|---|---|---|
| `username` | `k3s-backup` | ชื่อ user |
| `group_create` | `true` | สร้าง group ชื่อเดียวกันอัตโนมัติ |
| `home` | `/mnt/MainData/k3s-backup` | home = backup dataset |
| `home_create` | `false` | dataset มีอยู่แล้ว ไม่ต้องสร้างซ้ำ |
| `shell` | `/usr/bin/bash` | จำเป็นสำหรับ rsync |
| `password_disabled` | `true` | ปิด password — ใช้ key อย่างเดียว |
| `sshpubkey` | (public key) | authorize key สำหรับ SSH |
| `smb` | `false` | ไม่ให้ใช้ SMB (security) |

## Step 1.4 — Set Ownership

```bash
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "echo '@123456789' | sudo -S chown -R k3s-backup:k3s-backup /mnt/MainData/k3s-backup && \
   echo '@123456789' | sudo -S chmod 750 /mnt/MainData/k3s-backup"
```

## Step 1.5 — ทดสอบ

```bash
# Test 1: SSH key auth
ssh -i ~/.ssh/k3s-backup-truenas k3s-backup@10.80.4.4 \
  'whoami && pwd && df -h /mnt/MainData/k3s-backup'

# Expected:
# k3s-backup
# /mnt/MainData/k3s-backup
# MainData/k3s-backup  500G  256K  500G  1%  /mnt/MainData/k3s-backup

# Test 2: Write access
ssh -i ~/.ssh/k3s-backup-truenas k3s-backup@10.80.4.4 \
  'echo "test $(date)" > test.txt && cat test.txt && rm test.txt'

# Test 3: rsync (ที่จะใช้จริงใน Phase A1)
echo "hello" > /tmp/test-backup.txt
rsync -av -e "ssh -i ~/.ssh/k3s-backup-truenas" \
  /tmp/test-backup.txt \
  k3s-backup@10.80.4.4:/mnt/MainData/k3s-backup/
```

## Step 1.6 — สร้าง SSH config (เลือกใช้ได้)

เพิ่มลง `~/.ssh/config`:

```sshconfig
Host truenas-backup
    HostName 10.80.4.4
    User k3s-backup
    IdentityFile ~/.ssh/k3s-backup-truenas
    IdentitiesOnly yes
```

หลังจากนั้น command สั้นลง:
```bash
ssh truenas-backup
rsync -av /path/ truenas-backup:/mnt/MainData/k3s-backup/
```

---

# 🖱️ วิธีที่ 2: Web UI (Visual — สำหรับเข้าใจง่าย)

## ข้อดี
- ✅ Visual, เข้าใจง่าย
- ✅ มี validation built-in
- ✅ ดู snapshot policy / permission แบบ GUI ได้

## ข้อเสียที่ควรรู้
- ⚠️ ทำซ้ำหลายครั้งเหนื่อย
- ⚠️ ไม่ scriptable

## Step 2.1 — เข้า Web UI

1. เปิด browser → https://10.80.4.4 (หรือ https://truenas.khitkon.com)
2. กด **Advanced** → **Proceed** ถ้าเตือน cert (self-signed)
3. Login: `truenas_admin` / `@123456789`

## Step 2.2 — สร้าง Dataset

1. Sidebar → **Datasets**
2. คลิก pool `MainData` ในแผนผัง
3. กดปุ่ม **Add Dataset** (มุมขวาบน)
4. กรอกข้อมูล:

| Field | กรอกอะไร |
|---|---|
| **Name** | `k3s-backup` |
| **Dataset Preset** | `Generic` |
| **Comments** | `k3s backup target - 500GB quota` |

5. คลิก **Advanced Options** เพื่อตั้งค่าเพิ่ม:

| Field | กรอกอะไร |
|---|---|
| **Compression Level** | `LZ4` |
| **Sync** | `Standard` (default) |
| **Atime** | `Off` (ลด IO) |
| **ACL Type** | `POSIX` (default) |

6. กด **Save**
7. คลิกที่ dataset ใหม่ที่เพิ่งสร้าง → ปุ่ม **Edit** ตรง section **Space Management**
8. ตั้ง:

| Field | กรอกอะไร |
|---|---|
| **Quota for this dataset** | `500` GiB |
| **Quota warning level** | `80` % (alert เมื่อใช้ 400GB) |
| **Quota critical level** | `95` % |

9. **Save**

### ตรวจสอบ
- Dataset ใหม่จะแสดงในแผนผัง: `MainData → k3s-backup`
- คลิกดู Properties → Quota: 500 GiB, Compression: lz4 ✅

## Step 2.3 — สร้าง User

1. Sidebar → **Credentials** → **Users**
2. กด **Add** มุมขวาบน
3. กรอก **Identification**:

| Field | กรอกอะไร |
|---|---|
| **Full Name** | `k3s Backup User` |
| **Username** | `k3s-backup` |
| **Email** | (เว้นว่าง) |

4. กรอก **User ID and Groups**:

| Field | กรอกอะไร |
|---|---|
| **UID** | `3001` (default ก็ได้) |
| **Create New Primary Group** | ✅ ติ๊ก |
| **Auxiliary Groups** | (เว้นว่าง) |

5. กรอก **Directories and Permissions**:

| Field | กรอกอะไร |
|---|---|
| **Home Directory** | `/mnt/MainData/k3s-backup` |
| **Create Home Directory** | ❌ **ไม่ติ๊ก** (มีอยู่แล้ว) |
| **Home Directory Permissions** | `750` |

6. กรอก **Authentication**:

| Field | กรอกอะไร |
|---|---|
| **Password** | (เว้นว่าง) |
| **Disable Password** | ✅ ติ๊ก |
| **Shell** | `bash` |
| **SSH Public Key** | paste public key จาก `cat ~/.ssh/k3s-backup-truenas.pub` |
| **Allow SSH Login with Password** | ❌ ไม่ติ๊ก |
| **Samba Authentication** | ❌ ไม่ติ๊ก |

7. **Save**

### ตรวจสอบ
- User `k3s-backup` แสดงใน list
- คลิกที่ user → ดู SSH Public Key → ต้องตรงกับที่เครื่อง mintpower

## Step 2.4 — ตั้ง Permission ของ Dataset

1. Sidebar → **Datasets** → คลิก `MainData/k3s-backup`
2. ใน section **Permissions** → คลิก **Edit**
3. ตั้งค่า:

| Field | กรอกอะไร |
|---|---|
| **Owner** | `k3s-backup` |
| **Owner Group** | `k3s-backup` |
| **Apply Owner** | ✅ ติ๊ก |
| **Apply Group** | ✅ ติ๊ก |
| **Access Mode** | `750` (Owner: rwx, Group: r-x, Other: ---) |
| **Apply Recursively** | ✅ ติ๊ก |

4. **Save**

## Step 2.5 — ทดสอบจาก mintpower

```bash
# Test SSH
ssh -i ~/.ssh/k3s-backup-truenas k3s-backup@10.80.4.4 'whoami && pwd'

# Test write
ssh -i ~/.ssh/k3s-backup-truenas k3s-backup@10.80.4.4 \
  'echo "ok" > /mnt/MainData/k3s-backup/test.txt && cat /mnt/MainData/k3s-backup/test.txt && rm /mnt/MainData/k3s-backup/test.txt'
```

---

# 🔄 (Optional) สร้าง Snapshot Policy

> ใช้ Web UI เท่านั้น (CLI ก็ทำได้แต่ยาว — แนะนำ UI)

1. Sidebar → **Data Protection** → **Periodic Snapshot Tasks** → **Add**
2. กรอก:

| Field | กรอกอะไร |
|---|---|
| **Dataset** | `MainData/k3s-backup` |
| **Recursive** | ❌ |
| **Snapshot Lifetime** | `90 Days` (Tier 3 daily) |
| **Naming Schema** | `auto-%Y%m%d-%H%M` |
| **Schedule Preset** | `Daily (00:00)` |
| **Begin / End** | `00:00 - 23:59` |
| **Allow taking empty snapshots** | ❌ |
| **Enabled** | ✅ |

3. **Save**

### Monthly snapshot (เก็บนาน 12 เดือน)

ทำซ้ำขั้นตอนข้างต้น แต่:
- **Lifetime**: `12 Months`
- **Schedule Preset**: `Monthly (00:00 day 1)`
- **Naming Schema**: `monthly-%Y%m`

---

# 🔍 Verify & Troubleshooting

## ตรวจสอบทุกอย่างพร้อมใช้

```bash
# 1. Dataset
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "midclt call pool.dataset.query '[[\"name\",\"=\",\"MainData/k3s-backup\"]]'" | jq '.[0] | {name, quota: .quota.value, compression: .compression.value, available: .available.value}'

# 2. User
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "midclt call user.query '[[\"username\",\"=\",\"k3s-backup\"]]'" | jq '.[0] | {username, uid, home, shell, password_disabled, sshpubkey}'

# 3. SSH auth จาก mintpower
ssh -i ~/.ssh/k3s-backup-truenas -o BatchMode=yes k3s-backup@10.80.4.4 'id && df -h $HOME'
```

## ปัญหาที่เจอบ่อย

### "Permission denied (publickey)"
- ตรวจ `~/.ssh/k3s-backup-truenas.pub` ตรงกับที่ใส่ใน TrueNAS user
- ตรวจ permission key file: `chmod 600 ~/.ssh/k3s-backup-truenas`
- ตรวจ user TrueNAS: `password_disabled: true` แต่ `sshpubkey` ต้องไม่ว่าง

### "Could not open a connection to your authentication agent"
- ใช้ `-i <key>` ทุกครั้ง หรือ setup ssh-agent: `eval $(ssh-agent) && ssh-add ~/.ssh/k3s-backup-truenas`

### "rsync: failed to set times on ...: Operation not permitted"
- ตรวจ ownership: dataset ต้องเป็นของ `k3s-backup`
- รัน: `sudo chown -R k3s-backup:k3s-backup /mnt/MainData/k3s-backup` ที่ TrueNAS

### "Disk quota exceeded"
- ใช้พื้นที่เกิน 500GB → ขยาย quota หรือลบ snapshot เก่า
- ขยาย quota:
  ```bash
  midclt call pool.dataset.update MainData/k3s-backup '{"quota": 1073741824000}'  # 1TB
  ```

### Dataset ลบไม่ได้
- ต้องลบ snapshot ทั้งหมดก่อน:
  ```bash
  midclt call pool.dataset.delete MainData/k3s-backup '{"recursive": true}'
  ```

---

# 🗑️ Rollback / Cleanup

ถ้าต้องการลบทุกอย่างที่สร้างไว้ (เริ่มใหม่):

```bash
# 1. ลบ user
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "USER_ID=\$(midclt call user.query '[[\"username\",\"=\",\"k3s-backup\"]]' | jq '.[0].id'); \
   midclt call user.delete \$USER_ID"

# 2. ลบ dataset (จะลบข้อมูลทั้งหมดด้วย!)
sshpass -p '@123456789' ssh truenas_admin@10.80.4.4 \
  "midclt call pool.dataset.delete MainData/k3s-backup '{\"recursive\":true,\"force\":true}'"

# 3. ลบ SSH key จาก mintpower
rm ~/.ssh/k3s-backup-truenas ~/.ssh/k3s-backup-truenas.pub
```

---

# 📊 Current Status — 2026-05-11

| Item | สถานะ |
|---|---|
| Dataset `MainData/k3s-backup` | ✅ Created (500GB, LZ4) |
| User `k3s-backup` | ✅ Created (uid 3001, password disabled, key only) |
| SSH key | ✅ `~/.ssh/k3s-backup-truenas` (ed25519) |
| Permission (parent) | ✅ Mode **775**, owner k3s-backup:k3s-backup |
| Permission (data/) | ✅ Mode **775** recursive, group rwx |
| Connection test (SSH) | ✅ SSH + rsync passed |
| **SMB share `k3s-backup`** | ✅ Path `/mnt/MainData/k3s-backup/data` (RW for kititach) |
| Backup scripts | ✅ systemd timer daily 02:00 (see `scripts/backup/`) |
| Snapshot policy | ⏳ Pending (Web UI Data Protection) |

---

# 🪟 SMB Share Setup (เพิ่ม 2026-05-11)

ให้ user `kititach` เข้าถึง backup data ผ่าน SMB:

## ขั้นตอน

```bash
# 1. ปรับ POSIX permission ให้ traverse + write
ssh truenas_admin@10.80.4.4 "echo '@123456789' | sudo -S bash -c '
  chmod 775 /mnt/MainData/k3s-backup
  chmod -R 775 /mnt/MainData/k3s-backup/data
'"

# 2. สร้าง / update SMB share ชี้ /data (ไม่ใช่ root — ซ่อน .ssh/)
midclt call sharing.smb.update <SHARE_ID> '{
  "path": "/mnt/MainData/k3s-backup/data",
  "enabled": true, "ro": false, "browsable": true
}'

# 3. Restart SMB เพื่อ flush cache
midclt call service.restart cifs
```

## Mount

| OS | Command |
|---|---|
| Windows | `\\10.80.4.4\k3s-backup` (File Explorer) หรือ `net use Z: \\10.80.4.4\k3s-backup /user:kititach` |
| macOS | `smb://10.80.4.4/k3s-backup` (Finder Cmd+K) |
| Linux | `sudo mount -t cifs //10.80.4.4/k3s-backup /mnt/x -o username=kititach,vers=3.0` |

## Troubleshooting — Windows "Access Denied" หลัง login

**สาเหตุ:** Windows cache credential เก่าจาก share path เดิม + traverse permission

**แก้:**
```cmd
# Admin Command Prompt:
cmdkey /list | findstr 10.80.4.4
cmdkey /delete:10.80.4.4
net use \\10.80.4.4 /delete /y
net use Z: \\10.80.4.4\k3s-backup /persistent:yes /user:kititach
```

หรือผ่าน UI: `Win+R` → `control /name Microsoft.CredentialManager` → Remove entry `10.80.4.4`

**ฝั่ง TrueNAS check list:**
- POSIX permission >= 775 (parent + recursive)
- kititach อยู่ใน group ที่ own dataset (เช็ค `id kititach`)
- SMB service running (`midclt call service.query '[[\"service\",\"=\",\"cifs\"]]'`)
- Share `ro: false`, `enabled: true`
