"""
OPC UA Simulator — จำลอง Industrial Sensor Data
Endpoint : opc.tcp://0.0.0.0:4840/
Kafka    : publish ทุก INTERVAL วินาที → opc-raw-data
"""
import asyncio
import json
import math
import random
import logging
import threading
from datetime import datetime, timezone
from asyncua import Server, ua
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("asyncua").setLevel(logging.WARNING)
logging.getLogger("kafka").setLevel(logging.WARNING)
log = logging.getLogger("opc-sim")
log.setLevel(logging.INFO)

# ─── Config ───────────────────────────────────────────────
ENDPOINT      = "opc.tcp://0.0.0.0:4840/"
SERVER_NAME   = "OPC-UA Simulator — mintpower lab"
NAMESPACE     = "urn:mintpower:opc-simulator"
INTERVAL      = 2.0   # วินาที

KAFKA_BROKERS = "10.85.3.104:32092"
KAFKA_TOPIC   = "opc-raw-data"
SOURCE_ID     = "PlantA"
DEVICE_ID     = "opc-sim-mintpower"

# ─── Sensor Definitions ───────────────────────────────────
SENSORS = [
    # (tag_id,          display_name,          unit,   min,   max,   noise)
    ("Temp_Boiler1",  "Temperature Boiler1", "degC",  60.0,  100.0, 0.5),
    ("Temp_Boiler2",  "Temperature Boiler2", "degC",  55.0,   95.0, 0.8),
    ("Press_Line1",   "Pressure Line1",      "bar",    1.5,    4.5, 0.05),
    ("Press_Line2",   "Pressure Line2",      "bar",    2.0,    5.0, 0.08),
    ("Flow_Main",     "Flow Rate Main",      "L/min", 80.0,  150.0, 2.0),
    ("Flow_Branch1",  "Flow Rate Branch1",   "L/min", 30.0,   70.0, 1.5),
    ("Level_Tank1",   "Tank Level 1",        "pct",   20.0,   95.0, 0.3),
    ("Level_Tank2",   "Tank Level 2",        "pct",   15.0,   90.0, 0.4),
    ("Vibration_Pump","Vibration Pump",      "mm/s",   0.5,    8.0, 0.2),
    ("Power_Motor1",  "Power Motor1",        "kW",     5.0,   25.0, 0.5),
    ("RPM_Motor1",    "RPM Motor1",          "rpm",  800.0, 1500.0, 10.0),
    ("Humidity_Room", "Humidity Room",       "pct",   30.0,   70.0, 0.5),
]

class SensorState:
    def __init__(self, tag_id, name, unit, vmin, vmax, noise):
        self.tag_id = tag_id
        self.name   = name
        self.unit   = unit
        self.vmin   = vmin
        self.vmax   = vmax
        self.noise  = noise
        self.phase  = random.uniform(0, 2 * math.pi)
        self.period = random.uniform(60, 300)
        self.var    = None
        self.t      = 0.0

    def next_value(self):
        self.t += INTERVAL
        mid   = (self.vmax + self.vmin) / 2
        amp   = (self.vmax - self.vmin) / 2 * 0.6
        sine  = amp * math.sin(2 * math.pi * self.t / self.period + self.phase)
        noise = random.gauss(0, self.noise)
        value = round(mid + sine + noise, 3)
        return max(self.vmin, min(self.vmax, value))


def create_kafka_producer():
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
            acks="all",
            retries=3,
        )
        log.info(f"Kafka producer connected → {KAFKA_BROKERS}")
        return producer
    except NoBrokersAvailable:
        log.warning(f"Kafka not available at {KAFKA_BROKERS} — will retry later")
        return None


async def main():
    # ── OPC UA Server ────────────────────────────────────────
    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_server_name(SERVER_NAME)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    idx = await server.register_namespace(NAMESPACE)
    plant       = await server.nodes.objects.add_object(idx, "PlantA")
    sensors_obj = await plant.add_object(idx, "Sensors")
    status_obj  = await plant.add_object(idx, "Status")

    states = []
    for (tag_id, name, unit, vmin, vmax, noise) in SENSORS:
        s = SensorState(tag_id, name, unit, vmin, vmax, noise)
        var = await sensors_obj.add_variable(idx, name, s.next_value())
        await var.set_writable()
        s.var = var
        states.append(s)

    server_time_var = await status_obj.add_variable(idx, "ServerTime", datetime.now(timezone.utc).isoformat())
    uptime_var      = await status_obj.add_variable(idx, "UptimeSeconds", 0)
    sample_count    = await status_obj.add_variable(idx, "SampleCount", 0)
    await server_time_var.set_writable()
    await uptime_var.set_writable()
    await sample_count.set_writable()

    # ── Kafka Producer ───────────────────────────────────────
    producer = create_kafka_producer()

    log.info("=" * 60)
    log.info("OPC UA Simulator started")
    log.info(f"Endpoint : {ENDPOINT}")
    log.info(f"Kafka    : {KAFKA_BROKERS} → {KAFKA_TOPIC}")
    log.info(f"Sensors  : {len(SENSORS)} tags under PlantA/Sensors/")
    log.info("=" * 60)

    tick = 0
    async with server:
        while True:
            await asyncio.sleep(INTERVAL)
            tick += 1

            ts = datetime.now(timezone.utc).isoformat()
            readings = {}

            for s in states:
                val = s.next_value()
                await s.var.write_value(val)
                readings[s.tag_id] = {"value": val, "unit": s.unit, "name": s.name}

            await server_time_var.write_value(ts)
            await uptime_var.write_value(tick * int(INTERVAL))
            await sample_count.write_value(tick * len(SENSORS))

            # ── Publish to Kafka ─────────────────────────────
            if producer is None:
                producer = create_kafka_producer()

            if producer:
                msg = {
                    "timestamp": ts,
                    "source":    SOURCE_ID,
                    "device":    DEVICE_ID,
                    "readings":  readings,
                }
                try:
                    producer.send(KAFKA_TOPIC, key=DEVICE_ID, value=msg)
                except Exception as e:
                    log.warning(f"Kafka send error: {e}")
                    producer = None

            if tick % 30 == 0:
                log.info(f"tick={tick} | uptime={tick*int(INTERVAL)}s | kafka={'ok' if producer else 'down'}")


if __name__ == "__main__":
    asyncio.run(main())
