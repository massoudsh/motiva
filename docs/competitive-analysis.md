# Competitive Analysis — AMR Fleet Operations Software

> Desk research, November 2026. Scope: operator-facing software for coordinating autonomous mobile robots in factories and warehouses. Claims below come from vendor pages and review round-ups; none were verified in a live trial.

## Why this matters

Motiva sits in the software layer above AMR fleets. Its closest competitors are not robot makers as such, but the fleet-management consoles bundled with AMR hardware and the vendor-neutral operations platforms. The feature gap that matters is therefore the one inside the operator console: dispatch, charging, traffic rules, analytics, and auditability.

## International rivals

| # | Vendor | What it is | Notable capabilities |
|---|---|---|---|
| 1 | **InOrbit** | Cloud RobOps platform, multi-vendor | Any robot / VDA 5050 connect, exclusion zones, multi-floor and elevator zones, multi-site management, incident-focused event logging tied to mission history, RobOps Copilot (LLM Q&A over fleet data) |
| 2 | **OTTO Fleet Manager** (Rockwell) | Fleet software for OTTO AMRs | Live job-to-robot pairing by battery, idle time and utilization; opportunistic charging between jobs; traffic rules with speed limits, exclusion zones and queuing; WMS/MES/ERP/PLC links |
| 3 | **MiR Fleet / MiR Insights** | Fleet control for MiR robots (up to ~100) | Mission scheduling with priority and robot groups, traffic and resource management, automatic charging dispatch, REST API into ERP/WMS/MES, separate analytics product |
| 4 | **Locus Robotics (LocusONE)** | Orchestration for Locus picking AMRs | Multi-robot coordination across zones, order-to-robot assignment, warehouse-level productivity reporting |
| 5 | **Cogniteam Nimbus / Synaos** | Vendor-neutral fleet and fleet-OS platforms | Approval-gated configuration changes tied to robot event logs, replayable mission history, mixed-fleet integration |

## Iranian rivals

| # | Vendor | What it is | Notable capabilities |
|---|---|---|---|
| 1 | **Tonb Soft (تُنب)** | TBOT-500/600 AMR plus fleet management | Live robot position, charge and task monitoring; smart task assignment by priority, capability, proximity and charge; traffic distribution to avoid congestion; charging dispatch; API task intake from WMS; IoT devices such as doors and lifts |
| 2 | **Megamachine Group** | AMR/AGV supply plus "smart factory" data platform | LiDAR and AI navigation robots, production data analytics for bottlenecks and downtime, integration into a broader factory-automation stack |
| 3 | **Navran (ناوران)** | Smart logistics and delivery fleet/parcel management | Route optimization, delivery-time tracking, fleet and parcel management. Adjacent rather than AMR-specific |
| 4 | **Pishgaman Asia (پیشگامان آسیا)** | Cloud fleet-management SaaS | Vehicle tracking, maintenance and driver management for transport fleets. Not warehouse robots |
| 5 | **Pars Robot** | Industrial arms and robotic cells | Welding, palletizing and handling cells with leasing and after-sales service. Hardware adjacency only; no fleet software found on their site |

The honest read: Iran has few credible direct AMR fleet-software competitors. Tonb is the one that clearly overlaps. Most local alternatives are hardware integrators or general vehicle-fleet SaaS, which leaves room for a vendor-neutral operations layer.

## Top 5 features extracted

The five capabilities that recur across these rivals and matter most for an operator console:

| Feature | Seen in | Status in Motiva |
|---|---|---|
| **Smart auto-dispatch** | OTTO, MiR, Tonb | Already present: `app/dispatch.py` ranks robots on battery, workload and distance and explains exclusions; `POST /api/missions/{id}/assign` with `{"auto": true}` assigns inside one transaction. |
| **Charge management** | OTTO, MiR, Tonb | Already present: `app/charging.py` decides when to charge, picks a bay, keeps a wait queue and escalates stranded robots. |
| **Zone rules: speed limits and restricted areas** | OTTO, InOrbit | **Added now:** `POST /api/map/rules` stores `max_speed` and `restricted` per zone. A restricted zone is enforced through the existing routing obstacle mechanism. |
| **Operations analytics** | MiR Insights, Megamachine, InOrbit | **Added now:** `GET /api/analytics?days=1\|7\|30` returns mission status mix, completion rate, daily telemetry volume, busiest robots and an explicitly-labelled estimated moving-sample share, with a definitions block. |
| **Audit log** | OTTO, InOrbit, Cogniteam | **Added now:** append-only `audit_log` with `GET /api/audit?limit=N`. Mission create, assign, cancel and complete plus zone-rule changes record actor, action, subject and detail. |

Supporting additions these features needed:

- `GET /api/missions/queue` — waiting missions in dispatch order (`app/queueing.py`: priority, then deadline, then creation order), so the dashboard shows the same "next" the dispatcher would pick.
- `POST /api/missions/{id}/complete` — a guarded completion transition that marks the mission done, sets progress to 100%, returns the robot to `waiting` only if it was still `moving`, and releases its corridor leases.
- Mission progress: 25% on assignment, 100% on completion. The dashboard mission table gained priority and progress columns and a confirm-gated "تکمیل" action.
- Dashboard panels: priority queue, operations analytics with a period selector and daily bar chart, and the audit table.

## Honest limitations

- Zone speed limits are stored and audited but not enforced; only `restricted` changes routing today, and the API response says so.
- The moving-sample share is an estimate from stored telemetry samples against a per-minute capacity assumption, not measured robot uptime. The payload labels it as such.
- Actor identity is a caller-supplied string defaulting to `operator`. Real role-based attribution depends on the authentication work in issue #1.
- The audit log is append-only by convention: no endpoint updates or deletes rows, but there is no tamper-evident chain.

## Sources

- [InOrbit overview](https://inorbit.ai/overview), [InOrbit missions](https://www.inorbit.ai/missions), [InOrbit RobOps Copilot](http://inorbit.ai/robopscopilot)
- [OTTO Fleet Manager](https://ottomotors.com/fleet-manager), [OTTO fleet-manager capabilities](https://ottomotors.com/blog/fleet-manager-capabilities-for-amr-scaling), [OTTO FMS docs](https://docs.ottomotors.com/en/30495-110581-about-fleet-manager.html)
- [MiR software](https://mobile-industrial-robots.com/products/software), [MiR Fleet reference guide](https://d18hjk6wpn1fl5.cloudfront.net/public/187/documents/Current-mir_fleet_reference_guide_1_4_en_pdf-187-50861-1.pdf)
- [Tonb robotics (EN)](https://en.tonbsoft.com/products/robotics), [Tonb robotics (FA)](https://tonbsoft.com/products/robotics), [IRIB report on TBOT-500](https://www.iranjib.ir/shownews/126307/)
- [Megamachine AMR/AGV](https://www.megamachinegroup.com/products/mobile-robot-industrial-iran), [Megamachine smart factory](https://www.megamachinegroup.com/mega-machine-smart-factory)
- [Navran](https://navran.ir/), [Pishgaman Asia](https://pishgamanasia.com/), [Pars Robot](https://pars-robot.com/)
- Review round-ups used only for orientation: [Zipdo](https://zipdo.co/best/robot-fleet-management-software), [WifiTalents](https://wifitalents.com/best/robot-fleet-management-software), [Gitnux](https://gitnux.org/best/robot-fleet-management-software/), [Cogniteam Nimbus round-up](https://wifitalents.com/best/robot-fleet-management-software)
