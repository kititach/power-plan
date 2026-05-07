# Phase 4 Update — OPC UA → NiFi Edge → Kafka
**Date:** 2026-05-06  
**Status:** ✅ COMPLETE — All 307 OPC UA tags flowing to Kafka

---

## Summary

Phase 4 of the OPC UA simulator pipeline is complete. The Groovy OPC UA reader running inside NiFi Edge (k3s, namespace `it`) reads 307 tags every 2 seconds from the Prosys OPC UA Simulation Server on mintserver and publishes to Kafka topic `opc-raw-data`.

---

## Component Versions

| Component | Version | Location |
|-----------|---------|----------|
| NiFi Edge | 2.0.0 | k3s `it` namespace, NodePort 31444 |
| Eclipse Milo | 0.6.12 | `/opt/nifi/nifi-current/data/milo-jars/` |
| Guava | 33.3.1-jre | Same directory (added this session) |
| Prosys OPC UA Sim Server | latest | mintserver (<OPC_SERVER_IP>:53530) |
| Kafka | 3.x (Strimzi) | k3s `dmz` namespace |

---

## Issues Resolved This Session

### 1. Missing Guava JAR (`NoClassDefFoundError: com/google/common/base/Preconditions`)
- **Root cause:** Milo's `NodeId.<clinit>` calls `Preconditions.checkNotNull()` (Guava) at class initialization, but Guava was not in `groovyx-additional-classpath`
- **Fix:** Copied `/opt/nifi/nifi-toolkit-current/lib/guava-33.3.1-jre.jar` → `/opt/nifi/nifi-current/data/milo-jars/`; added to classpath
- **File:** `/home/mintpower/lab/k3s/milo-jars/guava-33.3.1-jre.jar`

### 2. OPC UA Endpoint Hostname Resolution (`UnknownHostException: mintserver`)
- **Root cause:** Prosys server advertises endpoint with hostname `mintserver` in the `EndpointDescription`; NiFi pod could not resolve this hostname
- **Fix:** Patched k3s deployment `nifi-edge` to add `hostAliases: [{ip: <OPC_SERVER_IP>, hostnames: [mintserver]}]`
- **Command:** `kubectl patch deployment nifi-edge -n it --type=json -p='[{"op":"add","path":"/spec/template/spec/hostAliases","value":[{"ip":"<OPC_SERVER_IP>","hostnames":["mintserver"]}]}]'`

### 3. NiFi Flow Lost After Pod Restart
- **Root cause:** NiFi stores `flow.json.gz` in `/opt/nifi/nifi-current/conf/` which is NOT on the PVC (PVC only mounts at `/opt/nifi/nifi-current/data/`)
- **Impact:** All processor configs were lost after the pod restart triggered by the `hostAliases` patch
- **Mitigation:** Recreated all processors via NiFi REST API; TODO: fix PVC mount to include `conf/` directory

### 4. PublishKafka: Transactions Without Idempotence
- **Root cause:** NiFi 2.0 PublishKafka defaults `Transactions Enabled = true`, which requires Kafka `enable.idempotence=true`; incompatible with `acks=0`
- **Fix:** Set `Transactions Enabled = false` in PublishKafka processor

### 5. Kafka Bootstrap URL Wrong
- **Root cause:** Old flow used `kafka-0.kafka-headless.dmz.svc.cluster.local:9092` (wrong service name)
- **Fix:** Updated to `kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092`

### 6. Groovy Script: OpcUaClient.create() 3-arg API
- **Used:** `OpcUaClient.create(endpointUrl, endpointSelector, configBuilder)` — the correct Milo pattern that handles discovery AND endpoint URL rewriting automatically

---

## Final NiFi Flow (pod: nifi-edge-69f6b56fc5-8nnq4)

| Processor | ID | Status |
|-----------|-----|--------|
| Read OPC UA — Prosys mintserver | `fb9e2d81-019d-1000-f255-9b25076647d6` | RUNNING |
| Publish → opc-raw-data | `fb9e5838-019d-1000-1592-de95686c8a58` | RUNNING |
| Kafka 3.x Connection Service | `fb9d89e0-019d-1000-bde2-1078a57cae47` | ENABLED |

**Connection:** ExecuteGroovyScript[success] → PublishKafka  
**Classpath:** 8 JARs (Milo 0.6.12 x7 + guava-33.3.1)

---

## Verification

```
Kafka topic offsets (2026-05-06 ~04:59):
  opc-raw-data:0:105
  opc-raw-data:1:106074   ← Python simulator messages
  opc-raw-data:2:105

Sample NiFi message:
{
  "timestamp": 1778043552.844,
  "source_id": "mintserver-prosys",
  "device_id": "opc-prosys-300tags",
  "tags": { "Counter": 19, "Random": 1.349701, ... (307 tags) },
  "tag_count": 307,
  "bad_count": 0
}
```

---

## TODO / Pending

- [ ] **Fix NiFi flow persistence:** Mount PVC to include `/opt/nifi/nifi-current/conf/` so `flow.json.gz` survives pod restarts (currently configs are lost on restart)
- [ ] **Phase 6:** Stop Python `opc-simulator` service on mintserver (`sudo systemctl stop opc-simulator`) once NiFi source is validated stable
- [ ] **Fan-out:** Add PublishKafka processors for `opc-metrics` and `opc-datalake` topics

---

## Key Files

| File | Description |
|------|-------------|
| `/home/mintpower/lab/k3s/tools/opc_reader.groovy` | Original Groovy script template |
| `/tmp/opc_reader_deferred.groovy` | Current active script (deployed to NiFi) |
| `/home/mintpower/lab/k3s/milo-jars/` | Eclipse Milo + Guava JARs (source copy) |
| `/opt/nifi/nifi-current/data/milo-jars/` | JARs in NiFi pod PVC |
| `/home/mintpower/lab/k3s/update/plan-opc-nifi.html` | Full 6-phase plan |
