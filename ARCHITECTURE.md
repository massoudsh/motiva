# Motiva Architecture

## Scope

The MVP coordinates autonomous mobile robots for internal factory logistics. The operational flow is:

```text
Robot sensors → MQTT/telemetry ingestion → latest robot state + history
                                      ↓
ERP/WMS webhook → mission service → routing/optimization → robot commands
                                      ↓
                              WebSocket operations UI
```

## Boundaries

- **Identity and authorization:** Keycloak issues user claims; every organization and site query is scoped by those claims. Robot credentials never authenticate users.
- **Fleet service:** owns robot registration, latest telemetry, heartbeat/offline state, and telemetry retention.
- **Mission service:** owns the mission state machine, assignment, priority queue, timestamps, and audit events.
- **Map/routing service:** owns versioned site graphs, zones, stations, obstacles, and route calculation.
- **Integration adapters:** accept versioned WMS/ERP events with idempotency, HMAC verification, and bounded retries.
- **Operations UI:** reads HTTP resources and receives coalesced updates over WebSocket; it must not bypass backend safety or authorization checks.

## Data flow and safety

Commands are accepted only after authorization, state validation, and audit recording. A disconnected or stale robot is never treated as healthy. AI or optimization output is advisory until the mission service accepts it through the same guarded state transition as a manual action.

## Local development

The current prototype uses Python's standard library and SQLite so tests run without external services. It can run in the non-root `Dockerfile` image with `/data` mounted for persistence. The production target is Python services, PostgreSQL/TimescaleDB, EMQX, Keycloak, and Docker Compose. Production validation requires testing those services together before pilot deployment.

`Dockerfile` packages the API and dashboard as a single non-root service listening on `0.0.0.0:8787`, with SQLite in the `/data` volume. `docker-compose.yml` runs that service and an nginx container for `landing/`; the TimescaleDB, EMQX, and Keycloak containers are isolated in the `platform` profile because the application does not consume them yet.

## Quality gates

Run `python -m unittest discover -s app -p 'test_*.py'`. CI also runs syntax compilation, a Docker image build with a container health smoke test, and secret scanning; service integration tests should be added when the production dependencies are introduced.
