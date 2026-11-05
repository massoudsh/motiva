# ADR-001: MVP Stack

> Decision record for the first design-partner MVP.

## Status

Accepted for the MVP; production broker and TimescaleDB validation remain a deployment gate.

## Decision

- **Backend:** Python with FastAPI-compatible contracts; the current prototype remains dependency-light while the service boundary is established.
- **Frontend:** React-compatible browser client; the current RTL client is retained until the service migration is scheduled.
- **Database:** PostgreSQL with TimescaleDB for telemetry; SQLite remains the local prototype store.
- **Robot transport:** MQTT/EMQX for device telemetry.
- **UI realtime:** WebSocket, with HTTP endpoints for queries and commands.
- **Identity:** Keycloak for user identity and role claims; robot credentials are separate from user credentials.
- **Deployment:** Docker Compose for the MVP and an explicit migration path to Kubernetes in phase 2.

## Rationale

Python minimizes the distance to ROS 2, OR-Tools, NetworkX, and ML components while remaining sufficient for the measured ingestion spike. MQTT matches intermittent industrial networks, TimescaleDB supplies retention and downsampling primitives, and WebSocket avoids polling fan-out to the operations UI.

## Spike evidence

The 50-robot simulation used an in-process queue and SQLite WAL because EMQX and TimescaleDB were unavailable in the test environment. It reported p50 latency of 33 ms, p95 of 57 ms, 486 messages/second, 4.4% of one CPU core, and 35 MB RAM. Invalid telemetry was rejected and a 3-second watchdog detected offline robots in 3.0–3.5 seconds.

## Consequences

The MVP must keep latest robot state separate from raw telemetry, batch writes, coalesce UI updates, and define retention before production ingestion. Re-run the spike against EMQX and TimescaleDB before pilot deployment; the current prototype numbers do not validate broker or database performance.

## Related concepts

- [[concepts/dev-roadmap]]
- [[entities/operations-dashboard]]
