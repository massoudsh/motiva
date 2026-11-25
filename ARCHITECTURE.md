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

## VDA 5050 bridge

`app/vda5050.py` translates the standard's messages and nothing more. VDA 5050 fixes the message contract between a master control and a vehicle (order, state, instantActions, connection); it explicitly excludes traffic coordination, routing, functional safety, charging curves and load handling. Those remain fleet-manager responsibilities and are not claimed as solved by adopting the standard.

- **Inbound, wired:** `POST /api/integrations/vda5050` accepts `{"agv_id", "message_type": "state"|"connection", "payload"}` forwarded by whatever gateway subscribes to `state/{agv_id}` and `connection/{agv_id}`. State messages update battery, position, order context and safety flags; connection messages set the heartbeat directly. Coordinates are metres on the vehicle map, scaled to the site extent (`MOTIVA_MAP_EXTENT_METRES`) for the dashboard grid and clamped to 0-100.
- **Outbound, not wired:** `order_message()` builds a valid VDA order from a route of map node ids, but nothing publishes to `order/{agv_id}`. No endpoint claims a command reached a robot. Publishing through an MQTT client is the remaining seam.

## Auto-dispatch

`app/dispatch.py` ranks robots for a mission and explains the result. A robot is
excluded, with a reason, when it is `offline` (which includes stale heartbeats),
`charging`, has an unknown battery, or is below the dispatch battery floor.
Eligible robots are scored on a weighted blend of battery (0.40), workload
(0.35) and distance to the origin (0.25); weights are renormalised when a signal
is unavailable. Ties break on robot id so a recommendation is reproducible.

Distance is only used when the mission origin resolves to a placed map node. The
prototype's origins are free text, so an unresolved origin drops the distance
signal instead of inventing a location — the response reports `distance_used`
so the UI never implies a proximity it did not compute. `GET
/api/missions/{id}/dispatch` returns a dry-run recommendation; `POST
/api/missions/{id}/assign` with `{"auto": true}` performs the assignment inside
the same serialised transaction, and returns the full explanation alongside the
result.

## Traffic coordination

`app/traffic.py` reserves corridor nodes so two robots do not plan through the
same space at once. VDA 5050 explicitly excludes traffic coordination, deadlock
resolution and routing, so this is fleet-manager responsibility that the
protocol does not provide.

- **What is exclusive:** transit nodes only. A mission's start and goal are
  stations that several robots may legitimately share (pick-up queues,
  drop-off bays), so leasing them would make two trips through the same station
  impossible.
- **Leases expire.** Each lease carries `held_until`; there is no continuous
  progress feed in the prototype to release nodes as a robot passes them, so a
  bounded lease is the honest mechanism. Expired rows are cleared on the next
  claim.
- **One holder per node** is enforced by the primary key, not just by code, so a
  racing claim cannot double-book a corridor. A robot re-claiming its own node
  refreshes the lease rather than conflicting with itself.
- **Routing reports why.** `plan_route` returns `clear`, `detoured`,
  `blocked_by_traffic` or `no_route`, and a caller can distinguish a map that
  has no path from a corridor another robot occupies.

`POST /api/map/route` accepts `{"robot": "...", "reserve": true}` to plan and
lease; `POST /api/missions/{id}/assign` leases the mission route automatically
and reports `unrouted` when the endpoints are free text rather than placed
nodes. Cancelling a waiting mission releases its leases.

**Known limit:** leases are node-level and time-boxed, not time-windowed per
segment. Two robots can still meet mid-corridor if a lease expires while one is
still travelling, and there is no deadlock-resolution loop. Vertex reservations
with a bounded lease are an honest first step, not full traffic management.

## Charge management

`app/charging.py` decides *when* a robot should charge and *which* bay it gets.
OEM fleet managers charge between jobs rather than only at exhaustion, because
it protects battery life while keeping material moving.

- **When:** at or below 25% charge; at or below 5% it is flagged `critical`. An
  idle robot is the cheapest to charge and gets a distinct reason
  (`idle_below_threshold`) from a busy one (`below_threshold`), so an operator
  can see the trade-off rather than an opaque "send to charger".
- **Never:** a stale/offline robot, an already-charging robot, or one with no
  battery reading is never told to charge — a robot that is not reporting
  cannot act on the command.
- **Which:** the nearest free bay, using placed positions when both the robot
  and charger have them. Otherwise bays order by id, so the choice stays
  reproducible. Busy bays are named in `busy`, and an explicit request for an
  occupied bay returns `charger_unavailable` instead of quietly reassigning it.
- **One robot per bay** is enforced by the primary key, and the occupancy is a
  lease that expires. A robot that reports `moving` or `waiting` (over HTTP or
  via the VDA bridge) releases its bay immediately, otherwise a dead lease would
  block the charger until expiry.

### Wait queue and escalation

A robot refused because every bay was busy is stored in `charger_queue` rather
than discarded, so a stranded low-battery robot stays visible.

- **Order:** critical robots first, then robots waiting past
  `STARVATION_LIMIT_SECONDS` (600s), then lowest battery, then longest wait, then
  id. Every entry reports `waited_seconds` and `escalated`, so a robot jumping the
  queue is explained, not mysterious.
- **Admission is an offer, not a silent assignment.** `GET /api/chargers` returns
  `admit_now` — robots that should take a newly free bay — and they leave the
  queue once they actually charge.
- **Escalation is visible:** a critical or starving waiter raises a
  `charger_queue_stuck` alert carrying the reason and wait time.

### Dispatch and charging share one threshold

`MIN_DISPATCH_BATTERY` is derived from `CHARGE_THRESHOLD`, not duplicated. Before
this, dispatch excluded robots below 20% while charging began at 25%, so a robot
at 22% kept accepting missions while dispatch already flagged it for charging —
the work deferred the charge indefinitely. A robot at or below the charge
threshold now receives no new missions.

**Known limit:** the queue is served on request, not by a background worker —
admission happens when `/api/chargers` or a charge request is called, not the
instant a bay frees up under an idle system.

Endpoints: `GET /api/chargers`, `POST /api/chargers`,
`GET /api/robots/{id}/charge` (dry run) and `POST /api/robots/{id}/charge`.
Low-battery alerts now carry `charging_available` and the suggested `charger`, so
the warning states whether charging is actually achievable.

**Known limit:** there is no charging *queue*. A robot refused because every bay
is busy is not remembered and must be retried; there is also no cost model or
charging-curve awareness, which VDA 5050 leaves to the vendor.

## Mission queue and completion

`app/queueing.py` defines the single "next mission" order: priority (urgent,
high, normal, low), then deadline (a mission without one sorts after one with
one at the same priority), then creation order. `GET /api/missions/queue`
serves that order so the dashboard and the dispatcher agree.

`POST /api/missions/{id}/complete` is the only way to close a running mission.
It marks the mission `done`, sets progress to 100%, returns the robot to
`waiting` only if it was still `moving` (charging and stale robots keep their
own state), and releases the mission's corridor leases. Progress is 25% on
assignment. Any other status is rejected with `409`.

## Zone rules

`POST /api/map/rules` stores `max_speed` and `restricted` per map node.
`restricted` is enforced by writing the same node into `map_obstacles`, so
routing uses the mechanism it already has instead of a second one. `max_speed`
is stored and audited only; no robot-side speed enforcement exists, and the
response returns `speed_enforced: false` rather than implying otherwise.

## Audit log

`audit_log` is append-only by convention — no endpoint updates or deletes rows.
Mission create, assign, cancel and complete plus zone-rule changes record actor,
action, subject and detail. The actor is supplied by the caller and defaults to
`operator`; binding it to an authenticated principal is the authentication work
in issue #1. `GET /api/audit?limit=N` (1–500) returns newest first. There is no
tamper-evident chain, so this is accountability, not forensic proof.

## Operations analytics

`app/analytics.py` summarises stored rows only: mission status mix and
completion rate, daily telemetry sample counts, busiest robots, and a
moving-sample share. The share is an estimate (moving samples over a
per-minute-per-robot capacity), not measured uptime, and the payload carries a
`definitions` block saying so. `GET /api/analytics?days=1|7|30`.

## Heartbeat and offline state

A robot is offline when its last heartbeat is older than `MOTIVA_HEARTBEAT_TIMEOUT_SECONDS`, or when it has never reported. The stored `status` keeps what the robot last reported; the API exposes the derived `status` plus `reported_status`, `stale` and `heartbeat_at`. A stale robot is never counted as online, never raises a low-battery alert in place of an offline alert, and cannot be assigned a mission.

## Local development

The current prototype uses Python's standard library and SQLite so tests run without external services. It can run in the non-root `Dockerfile` image with `/data` mounted for persistence. The production target is Python services, PostgreSQL/TimescaleDB, EMQX, Keycloak, and Docker Compose. Production validation requires testing those services together before pilot deployment.

`Dockerfile` packages the API and dashboard as a single non-root service listening on `0.0.0.0:8787`, with SQLite in the `/data` volume. `docker-compose.yml` runs that service and an nginx container for `landing/`; the TimescaleDB, EMQX, and Keycloak containers are isolated in the `platform` profile because the application does not consume them yet.

## Quality gates

Run `python -m unittest discover -s app -p 'test_*.py'`. CI also runs syntax compilation, a Docker image build with a container health smoke test, and secret scanning; service integration tests should be added when the production dependencies are introduced.
