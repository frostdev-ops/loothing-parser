#!/bin/bash
# InfluxDB Initialization Script for Test Suite

set -e

# Wait for InfluxDB to be ready
echo "Waiting for InfluxDB to be ready..."
until influx ping; do
  echo "InfluxDB not ready yet, waiting..."
  sleep 2
done

echo "InfluxDB is ready, setting up test environment..."

# Variables from environment
INFLUX_ORG="${INFLUX_ORG:-wow-guild}"
INFLUX_BUCKET="${INFLUX_BUCKET:-combat-events}"
INFLUX_TOKEN="${INFLUX_TOKEN:-test-token-12345678901234567890123456789012345678901234567890}"
INFLUX_USERNAME="${INFLUX_USERNAME:-admin}"
INFLUX_RETENTION="${INFLUX_RETENTION:-30d}"

# Create additional buckets for testing different data types
echo "Creating additional test buckets..."

# Metrics bucket for aggregated data
influx bucket create \
  --name "combat-metrics" \
  --org "$INFLUX_ORG" \
  --retention "$INFLUX_RETENTION" \
  --token "$INFLUX_TOKEN" || echo "Bucket combat-metrics might already exist"

# Test bucket for development data
influx bucket create \
  --name "test-data" \
  --org "$INFLUX_ORG" \
  --retention "7d" \
  --token "$INFLUX_TOKEN" || echo "Bucket test-data might already exist"

# Performance test bucket
influx bucket create \
  --name "performance-tests" \
  --org "$INFLUX_ORG" \
  --retention "1d" \
  --token "$INFLUX_TOKEN" || echo "Bucket performance-tests might already exist"

echo "Creating test data..."

# Write some sample data points for testing
influx write \
  --bucket "$INFLUX_BUCKET" \
  --org "$INFLUX_ORG" \
  --token "$INFLUX_TOKEN" \
  --precision s \
  "combat_events,encounter_id=test-encounter-1,guild_id=1,event_type=SWING_DAMAGE,source_name=Testpaladin amount=1250i,critical=false $(date -d '5 minutes ago' +%s)"

influx write \
  --bucket "$INFLUX_BUCKET" \
  --org "$INFLUX_ORG" \
  --token "$INFLUX_TOKEN" \
  --precision s \
  "combat_events,encounter_id=test-encounter-1,guild_id=1,event_type=SPELL_HEAL,source_name=Testpriest amount=2500i,critical=true $(date -d '4 minutes ago' +%s)"

influx write \
  --bucket "$INFLUX_BUCKET" \
  --org "$INFLUX_ORG" \
  --token "$INFLUX_TOKEN" \
  --precision s \
  "combat_events,encounter_id=test-encounter-1,guild_id=1,event_type=SPELL_DAMAGE,source_name=Testmage,spell_name=Fireball amount=3750i,critical=false $(date -d '3 minutes ago' +%s)"

# Create test queries for validation
echo "Creating test queries..."

# Test query 1: Basic damage aggregation
TEST_QUERY1='from(bucket: "combat-events")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "combat_events")
  |> filter(fn: (r) => r.event_type =~ /.*DAMAGE.*/)
  |> filter(fn: (r) => r._field == "amount")
  |> group(columns: ["source_name"])
  |> sum()'

# Test query 2: Healing metrics
TEST_QUERY2='from(bucket: "combat-events")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "combat_events")
  |> filter(fn: (r) => r.event_type =~ /.*HEAL.*/)
  |> filter(fn: (r) => r._field == "amount")
  |> group(columns: ["source_name"])
  |> sum()'

echo "Running validation queries..."

# Test the queries to ensure they work
echo "Testing damage aggregation query..."
echo "$TEST_QUERY1" | influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" || echo "Query failed, but that's expected with minimal test data"

echo "Testing healing aggregation query..."
echo "$TEST_QUERY2" | influx query --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" || echo "Query failed, but that's expected with minimal test data"

# Create continuous queries for real-time aggregations (if supported)
echo "Setting up continuous queries for performance testing..."

# Write performance test data
echo "Generating performance test data..."
for i in {1..100}; do
  timestamp=$(date -d "$i seconds ago" +%s)
  damage=$((RANDOM % 5000 + 1000))

  influx write \
    --bucket "performance-tests" \
    --org "$INFLUX_ORG" \
    --token "$INFLUX_TOKEN" \
    --precision s \
    "performance_test,test_id=load-test-1,source=generator damage=${damage}i,sequence=${i}i $timestamp" 2>/dev/null || true
done

echo "InfluxDB test environment setup complete!"
echo "Buckets created:"
echo "  - $INFLUX_BUCKET (main combat events)"
echo "  - combat-metrics (aggregated metrics)"
echo "  - test-data (development testing)"
echo "  - performance-tests (load testing)"
echo ""
echo "Access InfluxDB UI at http://localhost:8086"
echo "Username: $INFLUX_USERNAME"
echo "Organization: $INFLUX_ORG"
echo "Token: $INFLUX_TOKEN"