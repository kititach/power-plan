#!/usr/bin/env python3
"""
gen_300tags.py — สร้าง XML snippet สำหรับเพิ่ม 300 OPC UA Tags ใน Prosys
รัน: python3 gen_300tags.py
Output: nodes.xml, simulations.xml (เพิ่มเข้า Prosys config files)
"""

TAG_GROUPS = [
    # (prefix, count, unit, min_val, max_val)
    ("Temp_Boiler",     20, "degC",   60,  120),
    ("Temp_HeatEx",     10, "degC",   40,   90),
    ("Press_Line",      20, "bar",     2,   10),
    ("Press_Tank",      10, "bar",     1,    8),
    ("Flow_Main",       15, "L/min",  50,  200),
    ("Flow_Branch",     15, "L/min",  10,   80),
    ("Level_Tank",      20, "%",      20,   95),
    ("Vibration_Pump",  20, "mm/s",    0,   15),
    ("Power_Motor",     20, "kW",      5,  150),
    ("RPM_Motor",       20, "rpm",   800, 3000),
    ("Humidity_Room",   10, "%",      30,   80),
    ("Current_Drive",   20, "A",       5,   80),
    ("Voltage_Bus",     10, "V",     380,  420),
    ("CO2_Zone",        10, "ppm",   400, 1200),
    ("Noise_Floor",     10, "dB",     40,   90),
    ("Torque_Motor",    20, "Nm",     10,  500),
    ("Temp_Ambient",    10, "degC",   20,   45),
    ("Flow_Coolant",    10, "L/min",   5,   50),
    ("Press_Hydraulic", 10, "bar",    50,  200),
    ("Temp_Oil",        10, "degC",   40,  100),
    ("Temp_Cooling",    10, "degC",    5,   35),
]
# รวม count = 300 tags

START_NODE_ID = 2001   # NodeId เริ่มต้น ns=1;i=2001 (= ns=3 บน wire)
START_SIM_ID  = 101    # Simulation NodeId ns=1;i=101

# ── Format จริงของ Prosys (จาก reverse-engineering Instances_idx_3.NodeSet2.xml) ──
# - ns=1 ในไฟล์ = ns=3 บน OPC UA wire
# - ต้องมี References ชี้ไปที่ Simulation folder
# - BrowseName prefix = "1:"
# - DataType i=11 = Double, i=6 = Int32

nodes_xml = []
sims_xml  = []
tag_map   = {}   # name -> Groovy NodeId (ns=3 บน wire)

idx_node = START_NODE_ID
idx_sim  = START_SIM_ID
total    = 0

for prefix, count, unit, lo, hi in TAG_GROUPS:
    for n in range(1, count + 1):
        name = f"{prefix}_{n:02d}"
        mid  = (lo + hi) / 2.0
        amp  = (hi - lo) / 2.0

        # Format ตรงกับ Prosys จริง (ns=1 ในไฟล์ = ns=3 บน wire)
        nodes_xml.append(f'''\
  <UAVariable AccessLevel="5" BrowseName="1:{name}" DataType="i=11" Historizing="true" MinimumSamplingInterval="-1.0" NodeId="ns=1;i={idx_node}" UserAccessLevel="3">
    <DisplayName>{name}</DisplayName>
    <References>
      <Reference ReferenceType="i=40">i=63</Reference>
      <Reference IsForward="false" ReferenceType="i=35">ns=1;s=85/0:Simulation</Reference>
    </References>
    <Value><uax:Double>{mid}</uax:Double></Value>
  </UAVariable>''')

        # Simulation config format (ดูจาก Simulations_idx_4.NodeSet2.xml)
        sims_xml.append(f'''\
  <ValueSimulation NodeId="ns=4;i={idx_sim}">
    <TargetNode>ns=1;i={idx_node}</TargetNode>
    <SimulationType>Sinusoid</SimulationType>
    <Amplitude>{amp}</Amplitude>
    <Offset>{mid}</Offset>
    <Period>30000</Period>
    <PhaseShift>{(idx_node % 12) * 30}</PhaseShift>
  </ValueSimulation>''')

        # ns=1 ในไฟล์ = ns=3 บน OPC UA wire (Groovy ใช้ ns=3)
        tag_map[name] = f"new NodeId(3, {idx_node})"

        idx_node += 1
        idx_sim  += 1
        total    += 1

print(f"// Generated {total} tags  (NodeId ns=3;i={START_NODE_ID} .. ns=3;i={idx_node-1})")
print()

# ── nodes.xml ──────────────────────────────────────────────────────────────
with open("/tmp/nodes.xml", "w") as f:
    f.write("<!-- === INSERT BEFORE </UANodeSet> in Instances_idx_3.NodeSet2.xml === -->\n")
    f.write("\n".join(nodes_xml))
    f.write("\n")
print("✓ /tmp/nodes.xml")

# ── simulations.xml ─────────────────────────────────────────────────────────
with open("/tmp/simulations.xml", "w") as f:
    f.write("<!-- === INSERT BEFORE </SimulationSet> in Simulations_idx_4.NodeSet2.xml === -->\n")
    f.write("\n".join(sims_xml))
    f.write("\n")
print("✓ /tmp/simulations.xml")

# ── groovy_nodes.txt — วางใน NODES map ของ Groovy script ─────────────────
with open("/tmp/groovy_nodes.txt", "w") as f:
    for name, nid in tag_map.items():
        f.write(f'    "{name}": {nid},\n')
print("✓ /tmp/groovy_nodes.txt  (วางใน NODES map ใน Groovy script)")
print()
print(f"สรุป: {total} tags | NodeId ns=3;i={START_NODE_ID}–{idx_node-1}")
