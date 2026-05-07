#!/usr/bin/env python3
"""
deploy_opc_script.py — Deploy Groovy OPC script ขึ้น NiFi Edge

วิธีใช้:
    python3 deploy_opc_script.py
    python3 deploy_opc_script.py --script /path/to/other.groovy
    python3 deploy_opc_script.py --dry-run   (ดูโดยไม่ deploy จริง)
"""
import json
import subprocess
import urllib.request
import ssl
import sys
import argparse
import time

NIFI_URL  = "https://<K3S_NODE_IP>:31444"
NIFI_USER = "admin"
NIFI_PASS = "CHANGE_ME"

DEFAULT_SCRIPT = "/home/mintpower/lab/k3s/tools/opc_reader_final.groovy"
DEFAULT_GROOVY_ID = "fb9e2d81-019d-1000-f255-9b25076647d6"


def get_token():
    result = subprocess.run(
        ["curl", "-sk", "-X", "POST", f"{NIFI_URL}/nifi-api/access/token",
         "-H", "Content-Type: application/x-www-form-urlencoded",
         "-d", f"username={NIFI_USER}&password=Nifi%40mintpower2024%21"],
        capture_output=True, text=True
    )
    token = result.stdout.strip().strip('"')
    if not token or "invalid" in token.lower():
        print(f"ERROR: ไม่สามารถ login NiFi ได้: {token}")
        sys.exit(1)
    return token


def nifi_req(token, method, path, data=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{NIFI_URL}/nifi-api{path}"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=ctx) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR {e.code}: {body[:300]}")
        sys.exit(1)


def find_groovy_processor(token):
    """ค้นหา ExecuteGroovyScript processor ID จาก NiFi"""
    flow = nifi_req(token, "GET", "/flow/process-groups/root")
    for p in flow["processGroupFlow"]["flow"]["processors"]:
        if "Groovy" in p["component"]["type"] or "OPC" in p["component"]["name"]:
            return p["id"], p["component"]["name"]
    return None, None


def count_tags(script_content):
    """นับจำนวน tag ใน NODE_DEFS"""
    return script_content.count('", 3,')


def main():
    parser = argparse.ArgumentParser(description="Deploy Groovy OPC script ขึ้น NiFi")
    parser.add_argument("--script", default=DEFAULT_SCRIPT, help="path ของ .groovy file")
    parser.add_argument("--processor-id", default=None, help="Processor ID (ถ้าไม่ระบุจะค้นหาอัตโนมัติ)")
    parser.add_argument("--dry-run", action="store_true", help="แสดงข้อมูลโดยไม่ deploy จริง")
    args = parser.parse_args()

    print("=" * 60)
    print("  NiFi OPC Script Deployer")
    print("=" * 60)

    # อ่าน script
    try:
        with open(args.script) as f:
            script = f.read()
    except FileNotFoundError:
        print(f"ERROR: ไม่พบไฟล์ {args.script}")
        sys.exit(1)

    tag_count = count_tags(script)
    print(f"Script  : {args.script}")
    print(f"Tags    : ~{tag_count} tags (นับจาก NODE_DEFS)")
    print(f"Size    : {len(script):,} chars")

    if args.dry_run:
        print("\n[DRY RUN] ไม่ได้ deploy จริง")
        return

    print(f"\nเชื่อมต่อ NiFi ที่ {NIFI_URL} ...")
    token = get_token()
    print("Login สำเร็จ ✓")

    # หา Processor ID
    groovy_id = args.processor_id or DEFAULT_GROOVY_ID
    proc = nifi_req(token, "GET", f"/processors/{groovy_id}")

    # ถ้าไม่พบ ID เดิม ค้นหาใหม่
    if "component" not in proc:
        print(f"ไม่พบ processor ID {groovy_id} — กำลังค้นหาใหม่...")
        groovy_id, name = find_groovy_processor(token)
        if not groovy_id:
            print("ERROR: ไม่พบ ExecuteGroovyScript processor ใน NiFi")
            sys.exit(1)
        print(f"พบ: {name} ({groovy_id})")
        proc = nifi_req(token, "GET", f"/processors/{groovy_id}")

    proc_name = proc["component"]["name"]
    current_state = proc["component"]["state"]
    print(f"\nProcessor: {proc_name}")
    print(f"State    : {current_state}")

    # Stop processor
    print("\n[1/3] Stopping processor ...")
    rev = proc["revision"]["version"]
    stop_r = nifi_req(token, "PUT", f"/processors/{groovy_id}/run-status",
                      {"revision": {"version": rev}, "state": "STOPPED"})
    time.sleep(2)
    print(f"      Stopped (rev {stop_r['revision']['version']})")

    # Update script
    print("[2/3] Uploading script ...")
    proc = nifi_req(token, "GET", f"/processors/{groovy_id}")
    rev = proc["revision"]["version"]
    result = nifi_req(token, "PUT", f"/processors/{groovy_id}", {
        "revision": {"version": rev},
        "component": {
            "id": groovy_id,
            "config": {
                "properties": {
                    "groovyx-script-body": script
                }
            }
        }
    })
    print(f"      Updated (rev {result['revision']['version']})")

    # Validate
    val_status = result["component"]["validationStatus"]
    val_errors = result["component"].get("validationErrors", [])
    if val_status != "VALID":
        print(f"WARNING: Validation {val_status}")
        for e in val_errors:
            print(f"  - {e}")

    # Start processor
    print("[3/3] Starting processor ...")
    proc = nifi_req(token, "GET", f"/processors/{groovy_id}")
    rev = proc["revision"]["version"]
    start_r = nifi_req(token, "PUT", f"/processors/{groovy_id}/run-status",
                       {"revision": {"version": rev}, "state": "RUNNING"})
    print(f"      Running ✓ (rev {start_r['revision']['version']})")

    print("\n" + "=" * 60)
    print("Deploy สำเร็จ!")
    print(f"รอ ~10 วินาที แล้วตรวจสอบด้วย:")
    print(f"  kubectl logs -n it $(kubectl get pods -n it -l app=nifi-edge -o jsonpath='{{.items[0].metadata.name}}') --since=1m | grep '\\[OPC\\]'")
    print("=" * 60)


if __name__ == "__main__":
    main()
