#!/usr/bin/env python3
"""
OpenMAINT Bridge — Kafka opc-raw-data → OpenMAINT Alarm + CorrectiveMaint
รัน: /home/mintpower/lab/k3s/opc-sim/venv/bin/python3 openmaint_bridge.py
"""

import json
import logging
import time
from datetime import datetime, timezone
from kafka import KafkaConsumer
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Config ───────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP    = "localhost:32092"
KAFKA_TOPIC        = "opc-raw-data"
KAFKA_GROUP        = "openmaint-consumer"

OPENMAINT_URL      = "http://localhost:30885/cmdbuild/services/rest/v3"
OPENMAINT_USER     = "admin"
OPENMAINT_PASS     = "admin"

COOLDOWN_SECONDS   = 300   # 5 นาที / tag — ป้องกัน spam

# ─── Threshold Rules ──────────────────────────────────────────────────────────
# รูปแบบ: pattern_prefix → { max, min (optional), unit, severity, description }
# severity: "Critical" | "High" | "Medium"
RULES = [
    # Boiler Temperature
    {"prefix": "Temp_Boiler_",   "max": 95.0,  "unit": "°C",   "severity": "Critical",
     "description": "Boiler temperature overheat — risk of pressure vessel failure"},

    # Heat Exchanger
    {"prefix": "Temp_HeatEx_",   "max": 80.0,  "unit": "°C",   "severity": "High",
     "description": "Heat exchanger outlet temperature high — fouling or flow reduction"},

    # Oil Temperature
    {"prefix": "Temp_Oil_",      "max": 85.0,  "unit": "°C",   "severity": "High",
     "description": "Oil temperature high — lubrication degradation risk"},

    # Cooling Water (high = cooling system failure)
    {"prefix": "Temp_Cooling_",  "max": 30.0,  "unit": "°C",   "severity": "High",
     "description": "Cooling water temperature high — cooling system performance degraded"},

    # Pump Vibration (ISO 10816 Class II: alarm >7.1 mm/s, danger >11.2)
    {"prefix": "Vibration_Pump_","max": 10.0,  "unit": "mm/s", "severity": "High",
     "description": "Pump vibration excessive — bearing wear or misalignment"},

    # Line Pressure
    {"prefix": "Press_Line_",    "max": 8.0,   "min": 2.0,     "unit": "bar", "severity": "High",
     "description": "Line pressure out of safe range — check valves and pump"},

    # Tank Pressure
    {"prefix": "Press_Tank_",    "max": 6.0,   "min": 1.0,     "unit": "bar", "severity": "High",
     "description": "Tank pressure out of safe range — check relief valve"},

    # Hydraulic Pressure
    {"prefix": "Press_Hydraulic_","max": 160.0,"min": 50.0,    "unit": "bar", "severity": "Critical",
     "description": "Hydraulic pressure out of safe range — system integrity at risk"},

    # Tank Level (high = overflow, low = pump cavitation)
    {"prefix": "Level_Tank_",    "max": 90.0,  "min": 10.0,    "unit": "%",   "severity": "High",
     "description": "Tank level out of safe range — overflow or dry-run risk"},

    # Motor Current
    {"prefix": "Current_Drive_", "max": 60.0,  "unit": "A",    "severity": "High",
     "description": "Drive current high — motor overload or mechanical jam"},

    # Motor Torque
    {"prefix": "Torque_Motor_",  "max": 350.0, "unit": "Nm",   "severity": "High",
     "description": "Motor torque high — mechanical overload"},

    # Motor RPM
    {"prefix": "RPM_Motor_",     "max": 2200.0,"min": 500.0,   "unit": "rpm", "severity": "Medium",
     "description": "Motor speed out of operating range"},

    # Motor Power
    {"prefix": "Power_Motor_",   "max": 100.0, "unit": "kW",   "severity": "Medium",
     "description": "Motor power consumption high — efficiency loss"},

    # Bus Voltage
    {"prefix": "Voltage_Bus_",   "max": 440.0, "min": 350.0,   "unit": "V",   "severity": "Critical",
     "description": "Bus voltage out of range — electrical system fault"},

    # CO2 (ASHRAE 62.1: action at 1000 ppm)
    {"prefix": "CO2_Zone_",      "max": 1000.0,"unit": "ppm",  "severity": "Medium",
     "description": "CO2 level high — ventilation insufficient"},

    # Humidity
    {"prefix": "Humidity_Room_", "max": 80.0,  "min": 20.0,    "unit": "%",   "severity": "Medium",
     "description": "Room humidity out of comfort/equipment range"},

    # Main Flow (low = blockage, high = leak/burst)
    {"prefix": "Flow_Main_",     "max": 160.0, "min": 30.0,    "unit": "m³/h","severity": "High",
     "description": "Main flow out of range — check pipeline and pump"},

    # Branch Flow
    {"prefix": "Flow_Branch_",   "max": 60.0,  "min": 10.0,    "unit": "m³/h","severity": "Medium",
     "description": "Branch flow out of range"},

    # Coolant Flow
    {"prefix": "Flow_Coolant_",  "max": 40.0,  "min": 10.0,    "unit": "m³/h","severity": "High",
     "description": "Coolant flow out of range — cooling effectiveness compromised"},
]

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BRIDGE] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── OpenMAINT Session ────────────────────────────────────────────────────────
class OpenMAINTClient:
    def __init__(self):
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503])
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.token = None
        self._login()

    def _login(self):
        try:
            r = self.session.post(
                f"{OPENMAINT_URL}/sessions?scope=service&returnId=true",
                json={"username": OPENMAINT_USER, "password": OPENMAINT_PASS},
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            if data.get("success"):
                self.token = data["data"]["_id"]
                log.info("OpenMAINT login ok (token: %s...)", self.token[:8])
            else:
                log.error("OpenMAINT login failed: %s", data)
        except Exception as e:
            log.error("OpenMAINT login error: %s", e)

    def _headers(self):
        if not self.token:
            self._login()
        return {"CMDBuild-Authorization": self.token, "Content-Type": "application/json"}

    def create_alarm(self, tag, value, rule, ts):
        """สร้าง Alarm record ใน OpenMAINT"""
        direction = "HIGH" if value > rule.get("max", float("inf")) else "LOW"
        threshold = rule.get("max") if direction == "HIGH" else rule.get("min")
        name = f"ALARM-{tag}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        payload = {
            "Code":        name,
            "Name":        f"[AUTO] {tag} {direction}: {value:.2f} {rule['unit']}",
            "Description": f"{rule['description']}",
            "Notes":       (
                f"Tag: {tag}\n"
                f"Value: {value:.4f} {rule['unit']}\n"
                f"Threshold ({direction}): {threshold} {rule['unit']}\n"
                f"OPC Timestamp: {ts}\n"
                f"Detected at: {datetime.now(timezone.utc).isoformat()}"
            ),
        }
        try:
            r = self.session.post(
                f"{OPENMAINT_URL}/classes/Alarm/cards",
                headers=self._headers(),
                json=payload,
                timeout=10
            )
            r.raise_for_status()
            result = r.json()
            if result.get("success"):
                alarm_id = result["data"].get("_id")
                log.info("Alarm created: %s (id=%s)", name, alarm_id)
                return alarm_id
            else:
                log.error("Alarm create failed: %s", result)
        except Exception as e:
            log.error("Alarm create error: %s", e)
        return None

    def create_corrective_maint(self, tag, value, rule, ts, alarm_id=None):
        """สร้าง CorrectiveMaint work order ใน OpenMAINT"""
        direction = "HIGH" if value > rule.get("max", float("inf")) else "LOW"
        threshold = rule.get("max") if direction == "HIGH" else rule.get("min")
        priority_map = {"Critical": "1", "High": "2", "Medium": "3"}
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "ShortDescr":   f"[AUTO] {tag} {direction}: {value:.2f} {rule['unit']} (threshold: {threshold})",
            "ProcessNotes": (
                f"Automatic work order generated by OpenMAINT Bridge\n\n"
                f"Tag: {tag}\n"
                f"Measured value: {value:.4f} {rule['unit']}\n"
                f"Threshold ({direction}): {threshold} {rule['unit']}\n"
                f"Severity: {rule['severity']}\n"
                f"OPC Timestamp: {ts}\n"
                f"Detected at: {datetime.now(timezone.utc).isoformat()}\n"
                + (f"Related Alarm ID: {alarm_id}\n" if alarm_id else "")
                + f"\nAction required: {rule['description']}"
            ),
            "OpeningDate":  now_iso,
            "_advance":     True,   # ผ่าน Opening step อัตโนมัติ → Assignment
        }
        try:
            r = self.session.post(
                f"{OPENMAINT_URL}/processes/CorrectiveMaint/instances",
                headers=self._headers(),
                json=payload,
                timeout=10
            )
            r.raise_for_status()
            result = r.json()
            if result.get("success"):
                wf_id = result["data"].get("_id")
                log.info("CorrectiveMaint created: id=%s for tag=%s", wf_id, tag)
                return wf_id
            else:
                log.error("CorrectiveMaint create failed: %s", result)
        except Exception as e:
            log.error("CorrectiveMaint create error: %s", e)
        return None


# ─── Threshold Check ──────────────────────────────────────────────────────────
def find_violations(data: dict) -> list:
    """ตรวจหา tag ที่เกิน threshold ตาม RULES"""
    violations = []
    for tag, value in data.items():
        if not isinstance(value, (int, float)):
            continue
        for rule in RULES:
            if tag.startswith(rule["prefix"]):
                exceeded = False
                if "max" in rule and value > rule["max"]:
                    exceeded = True
                if "min" in rule and value < rule["min"]:
                    exceeded = True
                if exceeded:
                    violations.append((tag, value, rule))
                break
    return violations


# ─── Main Loop ────────────────────────────────────────────────────────────────
def main():
    log.info("OpenMAINT Bridge starting...")
    log.info("  Kafka: %s → topic: %s (group: %s)", KAFKA_BOOTSTRAP, KAFKA_TOPIC, KAFKA_GROUP)
    log.info("  OpenMAINT: %s", OPENMAINT_URL)
    log.info("  Cooldown: %ds per tag", COOLDOWN_SECONDS)
    log.info("  Rules: %d threshold rules loaded", len(RULES))

    om = OpenMAINTClient()
    cooldown: dict[str, float] = {}   # tag → last_alert_time

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=KAFKA_GROUP,
        auto_offset_reset="latest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=-1,   # block forever
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )
    log.info("Kafka consumer connected — waiting for messages...")

    for msg in consumer:
        try:
            data = msg.value
            ts = data.get("timestamp", "")
            violations = find_violations(data)

            for tag, value, rule in violations:
                now = time.time()
                last = cooldown.get(tag, 0)
                if now - last < COOLDOWN_SECONDS:
                    remaining = int(COOLDOWN_SECONDS - (now - last))
                    log.debug("Cooldown %s: skip (%.2f %s > %.2f) — %ds left",
                              tag, value, rule["unit"], rule.get("max", rule.get("min")), remaining)
                    continue

                cooldown[tag] = now
                direction = "HIGH" if value > rule.get("max", float("inf")) else "LOW"
                threshold = rule.get("max") if direction == "HIGH" else rule.get("min")
                log.warning("VIOLATION %s | %s | %.4f %s | threshold(%s)=%.1f | severity=%s",
                            tag, direction, value, rule["unit"], direction, threshold, rule["severity"])

                # 1. สร้าง Alarm
                alarm_id = om.create_alarm(tag, value, rule, ts)
                # 2. สร้าง CorrectiveMaint work order
                om.create_corrective_maint(tag, value, rule, ts, alarm_id)

        except Exception as e:
            log.error("Message processing error: %s", e)


if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            log.info("Bridge stopped by user")
            break
        except Exception as e:
            log.error("Bridge crashed: %s — restarting in 30s", e)
            time.sleep(30)
