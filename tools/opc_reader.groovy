// ============================================================
// OPC UA Reader — Eclipse Milo + NiFi ExecuteGroovyScript
// วาง script นี้ใน "Script Body" ของ ExecuteGroovyScript
// Module Directory: /opt/nifi/nifi-current/data/milo-jars
// Scheduling: Timer driven, 2 sec
// ============================================================

import org.eclipse.milo.opcua.sdk.client.OpcUaClient
import org.eclipse.milo.opcua.sdk.client.api.config.OpcUaClientConfig
import org.eclipse.milo.opcua.stack.client.DiscoveryClient
import org.eclipse.milo.opcua.stack.core.types.builtin.NodeId
import org.eclipse.milo.opcua.stack.core.types.builtin.LocalizedText
import org.eclipse.milo.opcua.stack.core.types.enumerated.TimestampsToReturn
import org.apache.nifi.processor.io.OutputStreamCallback
import groovy.json.JsonOutput

// ── Config ────────────────────────────────────────────────────
@groovy.transform.Field
static final String OPC_ENDPOINT =
    "opc.tcp://10.85.3.100:53530/OPCUA/SimulationServer"

@groovy.transform.Field
static final String SOURCE_ID = "mintserver-prosys"

@groovy.transform.Field
static final String DEVICE_ID = "opc-prosys-300tags"

// ── Node IDs (Prosys Default 7 Tags) ──────────────────────────
// !! อัปเดตหลัง browse จริงด้วย browse_opc.py !!
// !! เพิ่ม 300 custom tags หลัง Phase 1 (Prosys XML) เสร็จ !!
@groovy.transform.Field
static final Map<String, NodeId> NODES = [
    // Prosys default 7 tags — NodeId จาก browse_opc.py
    "Counter"  : new NodeId(3, 1001),
    "Random"   : new NodeId(3, 1002),
    "Sawtooth" : new NodeId(3, 1003),
    "Sinusoid" : new NodeId(3, 1004),
    "Square"   : new NodeId(3, 1005),
    "Triangle" : new NodeId(3, 1006),
    "Constant" : new NodeId(3, 1007),

    // === 300 Custom Tags (เพิ่มหลัง gen_300tags.py + browse ยืนยัน) ===
    // "Temp_Boiler_01": new NodeId(3, 2001),
    // "Temp_Boiler_02": new NodeId(3, 2002),
    // ... (วางจาก /tmp/groovy_nodes.txt)
]

// ── Static OPC Client (persist ข้ามรอบ ไม่ reconnect ทุก 2วิ) ──
@groovy.transform.Field
static OpcUaClient opcClient = null

@groovy.transform.Field
static final Object LOCK = new Object()

def ensureConnected() {
    synchronized (LOCK) {
        if (opcClient == null) {
            log.info("[OPC] Connecting to ${OPC_ENDPOINT}")
            def endpoints = DiscoveryClient
                .getEndpoints(OPC_ENDPOINT)
                .get(10, java.util.concurrent.TimeUnit.SECONDS)
            if (!endpoints) {
                throw new RuntimeException("No endpoints at ${OPC_ENDPOINT}")
            }
            def config = OpcUaClientConfig.builder()
                .setEndpoint(endpoints[0])
                .setApplicationName(LocalizedText.english("NiFi OPC Client"))
                .setApplicationUri("urn:nifi:opc:client:mintpower")
                .setRequestTimeout(
                    org.eclipse.milo.opcua.stack.core.types.builtin.unsigned.UInteger.valueOf(5000))
                .build()
            opcClient = OpcUaClient.create(config)
            opcClient.connect().get(10, java.util.concurrent.TimeUnit.SECONDS)
            log.info("[OPC] Connected ✓  (${NODES.size()} nodes)")
        }
    }
}

// ── Main ──────────────────────────────────────────────────────
try {
    ensureConnected()

    // Batch read — เร็วกว่าอ่านทีละตัวมาก
    def nodeList = NODES.values().toList()
    def values   = opcClient
        .readValues(0.0, TimestampsToReturn.Both, nodeList)
        .get(15, java.util.concurrent.TimeUnit.SECONDS)

    // สร้าง tags map
    def tags = [:]
    NODES.eachWithIndex { entry, i ->
        def dv = values[i]
        if (dv?.statusCode?.isGood()) {
            def raw = dv.getValue()?.getValue()
            // แปลง UInt/Long เป็น Number ปกติ
            tags[entry.key] = (raw instanceof Number) ? raw : raw?.toString()
        } else {
            tags[entry.key] = null
            log.debug("[OPC] Bad quality: ${entry.key} = ${dv?.statusCode}")
        }
    }

    // สร้าง JSON payload (format ตรงกับ opc_server.py เดิม)
    def payload = [
        timestamp : System.currentTimeMillis() / 1000.0,
        source_id : SOURCE_ID,
        device_id : DEVICE_ID,
        tags      : tags,
        tag_count : tags.size(),
        bad_count : tags.values().count { it == null }
    ]

    // สร้าง FlowFile
    def ff = session.create()
    ff = session.write(ff, { outputStream ->
        outputStream.write(JsonOutput.toJson(payload).getBytes("UTF-8"))
    } as OutputStreamCallback)

    ff = session.putAttribute(ff, "mime.type",   "application/json")
    ff = session.putAttribute(ff, "opc.source",  SOURCE_ID)
    ff = session.putAttribute(ff, "tag.count",   "${tags.size()}")

    session.transfer(ff, REL_SUCCESS)

} catch (Exception e) {
    log.error("[OPC] Read failed: ${e.message}", e)
    synchronized (LOCK) { opcClient = null }  // reset → จะ reconnect รอบหน้า

    def ff = session.create()
    ff = session.putAttribute(ff, "error.message", e.message ?: "unknown")
    ff = session.putAttribute(ff, "error.class",   e.class.simpleName)
    session.transfer(ff, REL_FAILURE)
}
