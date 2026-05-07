#!/usr/bin/env python3
"""
browse_opc.py — Browse OPC UA tree จาก Prosys บน mintserver
รัน: python3 browse_opc.py
ต้องการ: asyncua (มีอยู่ใน venv ของ opc-sim แล้ว)
"""
import asyncio
import sys

OPC_ENDPOINT = "opc.tcp://<OPC_SERVER_IP>:53530/OPCUA/SimulationServer"
TARGET_NS    = 3   # Prosys simulation namespace

async def browse():
    try:
        from asyncua import Client
    except ImportError:
        print("ERROR: asyncua ไม่พบ — รัน: source /home/mintpower/lab/k3s/opc-sim/venv/bin/activate")
        sys.exit(1)

    print(f"Connecting to {OPC_ENDPOINT} ...")
    try:
        async with Client(OPC_ENDPOINT, timeout=10) as client:
            print("Connected ✓\n")
            print(f"{'NodeId':<30} {'BrowseName':<35} {'DataType'}")
            print("-" * 90)

            found = []

            async def walk(node, depth=0):
                try:
                    bn  = await node.read_browse_name()
                    nid = node.nodeid
                    if nid.NamespaceIndex == TARGET_NS:
                        try:
                            val = await node.read_value()
                            dtype = type(val).__name__
                        except:
                            dtype = "—"
                        line = f"ns={nid.NamespaceIndex};i={nid.Identifier}"
                        print(f"  {line:<28} {bn.Name:<35} {dtype}")
                        found.append((bn.Name, f"ns={nid.NamespaceIndex};i={nid.Identifier}",
                                      f"new NodeId({nid.NamespaceIndex}, {nid.Identifier})"))
                    if depth < 6:
                        for child in await node.get_children():
                            await walk(child, depth + 1)
                except Exception:
                    pass

            root = client.get_node("ns=0;i=84")
            await walk(root)

            print(f"\n{'='*60}")
            print(f"พบทั้งหมด: {len(found)} nodes ใน namespace {TARGET_NS}")
            print()

            # สร้าง Groovy map snippet
            print("=== Groovy NODES Map (วางใน ExecuteGroovyScript) ===")
            for name, _, groovy in found[:20]:
                print(f'    "{name}": {groovy},')
            if len(found) > 20:
                print(f'    // ... และอีก {len(found)-20} nodes')

            # บันทึกเป็นไฟล์
            with open("/tmp/browse_result.txt", "w") as f:
                f.write(f"// OPC UA Browse result — {OPC_ENDPOINT}\n")
                f.write(f"// พบ {len(found)} nodes ใน ns={TARGET_NS}\n\n")
                for name, nid_str, groovy in found:
                    f.write(f'    "{name}": {groovy},\n')
            print(f"\n✓ บันทึกผลที่ /tmp/browse_result.txt")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

asyncio.run(browse())
