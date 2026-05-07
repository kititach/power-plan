#!/bin/bash
# Configure NiFi Core: ConsumeKafka(opc-datalake) → MergeRecord → PutS3Object(MinIO)
# Format: JSON (Parquet ไม่มีใน NiFi 2.0.0 standard NARs ของ airgap)
# Path: opc-raw/YYYY/MM/DD/<uuid>.json
set -euo pipefail

NIFI_URL="https://localhost:31443"
KAFKA_BOOTSTRAP="kafka-cluster-kafka-bootstrap.dmz.svc.cluster.local:9092"
MINIO_ENDPOINT="http://minio.it.svc.cluster.local:9000"
MINIO_ACCESS="minioadmin"
MINIO_SECRET='CHANGE_ME'
BUCKET="opc-raw"

# ─── 1. Auth ──────────────────────────────────────────────────────────────────
echo "▶ [1/7] Getting auth token..."
TOKEN=$(curl -sk -X POST "$NIFI_URL/nifi-api/access/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=CHANGE_ME")

if [ -z "$TOKEN" ]; then
  echo "✗ Failed to get token — is NiFi Core running?"
  exit 1
fi
echo "  ✓ Token OK"

# ─── 2. Root Process Group ────────────────────────────────────────────────────
echo "▶ [2/7] Getting root process group..."
ROOT_PG=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  "$NIFI_URL/nifi-api/flow/process-groups/root" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['processGroupFlow']['id'])")
echo "  ✓ Root PG: $ROOT_PG"

# ─── Helper: get current revision version of a controller service ─────────────
cs_version() {
  curl -sk -H "Authorization: Bearer $TOKEN" \
    "$NIFI_URL/nifi-api/controller-services/$1" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['revision']['version'])"
}

# ─── Helper: enable a controller service ─────────────────────────────────────
enable_cs() {
  local cs_id=$1 name=$2
  local ver=$(cs_version "$cs_id")
  local result
  result=$(curl -sk -X PUT \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "$NIFI_URL/nifi-api/controller-services/$cs_id/run-status" \
    -d "{\"revision\":{\"version\":$ver},\"state\":\"ENABLED\"}")
  local state
  state=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('component',{}).get('state','?'))" 2>/dev/null || echo "?")
  echo "  ✓ $name → $state"
}

# ─── 3. Controller Services ───────────────────────────────────────────────────
echo "▶ [3/7] Creating Controller Services..."

# 3a. Kafka3ConnectionService
CS_KAFKA_RESP=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/controller-services" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.service.Kafka3ConnectionService\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-3-service-nar\",\"version\":\"2.0.0\"},
      \"name\": \"KafkaConnectionService-Core\",
      \"properties\": {
        \"bootstrap.servers\": \"$KAFKA_BOOTSTRAP\"
      }
    }
  }")
CS_KAFKA=$(echo "$CS_KAFKA_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Kafka CS:    $CS_KAFKA"

# 3b. JsonTreeReader — อ่าน JSON จาก Kafka message
CS_READER_RESP=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/controller-services" \
  -d '{
    "revision": {"version": 0},
    "component": {
      "type": "org.apache.nifi.json.JsonTreeReader",
      "bundle": {"group":"org.apache.nifi","artifact":"nifi-record-serialization-services-nar","version":"2.0.0"},
      "name": "JsonTreeReader",
      "properties": {
        "schema-access-strategy": "infer-schema"
      }
    }
  }')
CS_READER=$(echo "$CS_READER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Reader CS:   $CS_READER"

# 3c. JsonRecordSetWriter — เขียน JSON array ลง MinIO
CS_WRITER_RESP=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/controller-services" \
  -d '{
    "revision": {"version": 0},
    "component": {
      "type": "org.apache.nifi.json.JsonRecordSetWriter",
      "bundle": {"group":"org.apache.nifi","artifact":"nifi-record-serialization-services-nar","version":"2.0.0"},
      "name": "JsonRecordSetWriter",
      "properties": {
        "schema-access-strategy": "inherit-record-schema",
        "output-grouping": "output-oneline"
      }
    }
  }')
CS_WRITER=$(echo "$CS_WRITER_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  Writer CS:   $CS_WRITER"

# 3d. AWSCredentialsProviderControllerService — credentials สำหรับ MinIO
CS_AWS_RESP=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/controller-services" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.processors.aws.credentials.provider.service.AWSCredentialsProviderControllerService\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-aws-nar\",\"version\":\"2.0.0\"},
      \"name\": \"MinIO-Credentials\",
      \"properties\": {
        \"Access Key\": \"$MINIO_ACCESS\",
        \"Secret Key\": \"$MINIO_SECRET\"
      }
    }
  }")
CS_AWS=$(echo "$CS_AWS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  AWS Creds CS: $CS_AWS"

# ─── 4. Enable Controller Services ───────────────────────────────────────────
echo "▶ [4/7] Enabling Controller Services (waiting 3s for NiFi to register)..."
sleep 3
enable_cs "$CS_KAFKA"   "KafkaConnectionService-Core"
enable_cs "$CS_READER"  "JsonTreeReader"
enable_cs "$CS_WRITER"  "JsonRecordSetWriter"
enable_cs "$CS_AWS"     "MinIO-Credentials"
sleep 3

# ─── 5. Create Processors ─────────────────────────────────────────────────────
echo "▶ [5/7] Creating Processors..."

# 5a. ConsumeKafka — รับ opc-datalake
CONSUME=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.kafka.processors.ConsumeKafka\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-kafka-nar\",\"version\":\"2.0.0\"},
      \"name\": \"ConsumeKafka — opc-datalake\",
      \"position\": {\"x\": 300, \"y\": 100},
      \"config\": {
        \"properties\": {
          \"Kafka Connection Service\": \"$CS_KAFKA\",
          \"Topics\": \"opc-datalake\",
          \"Group ID\": \"nifi-core-consumer\",
          \"auto.offset.reset\": \"earliest\",
          \"Output Strategy\": \"USE_VALUE\"
        },
        \"autoTerminatedRelationships\": [\"parse.failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  ConsumeKafka: $CONSUME"

# 5b. MergeRecord — batch ทุก 100 records (หรือทุก 60 วินาที)
MERGE=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.processors.standard.MergeRecord\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-standard-nar\",\"version\":\"2.0.0\"},
      \"name\": \"MergeRecord — batch 100\",
      \"position\": {\"x\": 300, \"y\": 320},
      \"config\": {
        \"properties\": {
          \"record-reader\": \"$CS_READER\",
          \"record-writer\": \"$CS_WRITER\",
          \"merge-strategy\": \"Bin-Packing Algorithm\",
          \"min-records\": \"100\",
          \"max-records\": \"1000\",
          \"max-bin-age\": \"60 sec\"
        },
        \"autoTerminatedRelationships\": [\"original\", \"failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  MergeRecord:  $MERGE"

# 5c. PutS3Object — เขียนลง MinIO bucket opc-raw พร้อม partition YYYY/MM/DD
OBJECT_KEY="data/year=\${now():format('yyyy')}/month=\${now():format('MM')}/day=\${now():format('dd')}/\${uuid}.json"

PUTS3=$(curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/processors" \
  -d "{
    \"revision\": {\"version\": 0},
    \"component\": {
      \"type\": \"org.apache.nifi.processors.aws.s3.PutS3Object\",
      \"bundle\": {\"group\":\"org.apache.nifi\",\"artifact\":\"nifi-aws-nar\",\"version\":\"2.0.0\"},
      \"name\": \"PutS3Object — MinIO opc-raw\",
      \"position\": {\"x\": 300, \"y\": 540},
      \"config\": {
        \"properties\": {
          \"AWS Credentials Provider service\": \"$CS_AWS\",
          \"Bucket\": \"$BUCKET\",
          \"Object Key\": \"$OBJECT_KEY\",
          \"Region\": \"us-east-1\",
          \"Endpoint Override URL\": \"$MINIO_ENDPOINT\",
          \"use-path-style-access\": \"true\",
          \"Signer Override\": \"Default Signature\",
          \"Content Type\": \"application/json\"
        },
        \"autoTerminatedRelationships\": [\"success\", \"failure\"]
      }
    }
  }" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  PutS3Object:  $PUTS3"

# ─── 6. Connect Processors ────────────────────────────────────────────────────
echo "▶ [6/7] Connecting processors..."

curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/connections" \
  -d "{\"revision\":{\"version\":0},\"component\":{
    \"source\":{\"id\":\"$CONSUME\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"destination\":{\"id\":\"$MERGE\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"selectedRelationships\":[\"success\"]}}" > /dev/null
echo "  ✓ ConsumeKafka → MergeRecord (success)"

curl -sk -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/process-groups/$ROOT_PG/connections" \
  -d "{\"revision\":{\"version\":0},\"component\":{
    \"source\":{\"id\":\"$MERGE\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"destination\":{\"id\":\"$PUTS3\",\"groupId\":\"$ROOT_PG\",\"type\":\"PROCESSOR\"},
    \"selectedRelationships\":[\"merged\"]}}" > /dev/null
echo "  ✓ MergeRecord  → PutS3Object  (merged)"

# ─── 7. Start Flow ────────────────────────────────────────────────────────────
echo "▶ [7/7] Starting flow..."
curl -sk -X PUT \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$NIFI_URL/nifi-api/flow/process-groups/$ROOT_PG" \
  -d "{\"id\":\"$ROOT_PG\",\"state\":\"RUNNING\"}" > /dev/null
echo "  ✓ Flow started"

# ─── Verify ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  รอ ~70 วินาที (MergeRecord flush ทุก 60s)"
echo "════════════════════════════════════════════"
sleep 70

echo "▶ Verify — MinIO bucket opc-raw:"
kubectl exec -n it deploy/minio -- mc ls local/opc-raw/ --recursive 2>/dev/null | head -20 || \
  echo "  (ตรวจ MinIO UI: http://<K3S_NODE_IP>:30901)"

echo ""
echo "▶ Verify — NiFi processor stats:"
curl -sk -H "Authorization: Bearer $TOKEN" \
  "$NIFI_URL/nifi-api/processors/$PUTS3" | \
  python3 -c "
import sys,json
d=json.load(sys.stdin)
status=d.get('status',{}).get('aggregateSnapshot',{})
print(f\"  PutS3Object — flowFilesIn: {status.get('flowFilesIn','?')}, bytesWritten: {status.get('bytesWritten','?')}\")
" 2>/dev/null || echo "  (check NiFi UI: https://<K3S_NODE_IP>:31443/nifi)"

echo ""
echo "════════════════════════════════════════════"
echo "  IDs สำหรับ debug:"
echo "  ConsumeKafka : $CONSUME"
echo "  MergeRecord  : $MERGE"
echo "  PutS3Object  : $PUTS3"
echo "  Kafka CS     : $CS_KAFKA"
echo "  AWS Creds CS : $CS_AWS"
echo "════════════════════════════════════════════"
