"""Telemetry ingestion spike for #18 (ADR-001, option B: Python).

Simulates N AMRs publishing telemetry at HZ for DUR seconds into an in-process
queue (stand-in for MQTT), validates with pydantic, batch-inserts into SQLite
(stand-in for TimescaleDB), upserts latest robot state and runs a heartbeat
watchdog. Two robots (amr-007, amr-023) drop offline halfway through.

Usage: python spike.py <robots> <hz> <seconds> [db_path]
Example: python spike.py 50 10 20
"""
import asyncio, json, time, random, sqlite3, sys, os, resource
from pydantic import BaseModel, Field

class Telemetry(BaseModel):
    robot_id: str
    ts: float
    x: float; y: float; heading: float
    zone: str
    battery: float = Field(ge=0, le=100)
    status: str
    lidar_min_m: float
    seq: int

N = int(sys.argv[1]); HZ = float(sys.argv[2]); DUR = float(sys.argv[3])
KILL = set(f"amr-{i:03d}" for i in (7, 23))  # simulate 2 robots dropping offline
KILL_AT = DUR*0.5; HEARTBEAT_TIMEOUT = 3.0
STATUSES = ["idle","on-mission","charging"]

DB_PATH = sys.argv[4] if len(sys.argv) > 4 else "spike-telemetry.db"
if os.path.exists(DB_PATH): os.remove(DB_PATH)
db = sqlite3.connect(DB_PATH); db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=NORMAL")
db.execute("DROP TABLE IF EXISTS telemetry"); db.execute("DROP TABLE IF EXISTS robot_state")
db.execute("CREATE TABLE telemetry(robot_id TEXT, ts REAL, x REAL, y REAL, heading REAL, zone TEXT, battery REAL, status TEXT, lidar REAL, seq INT)")
db.execute("CREATE INDEX ix ON telemetry(robot_id, ts)")
db.execute("CREATE TABLE robot_state(robot_id TEXT PRIMARY KEY, ts REAL, x REAL, y REAL, battery REAL, status TEXT)")

q = asyncio.Queue()
lat = []; sent = 0; stored = 0; invalid = 0; last_seen = {}; offline_detect = {}; ws_pushes = 0
start = None

async def robot(rid):
    global sent
    seq = 0; x, y, b = random.uniform(0,100), random.uniform(0,60), random.uniform(40,100)
    period = 1/HZ
    await asyncio.sleep(random.random()*period)
    while time.perf_counter()-start < DUR:
        if rid in KILL and time.perf_counter()-start > KILL_AT: return
        x += random.uniform(-.3,.3); y += random.uniform(-.3,.3); b = max(0, b-0.001)
        msg = {"robot_id":rid,"ts":time.time(),"x":x,"y":y,"heading":random.uniform(0,360),
               "zone":f"Z{int(x//25)}","battery":b,"status":random.choice(STATUSES),"lidar_min_m":random.uniform(.2,8),"seq":seq}
        if random.random() < 0.001: msg["battery"] = 140  # malformed
        await q.put((json.dumps(msg).encode(), time.perf_counter())); sent += 1; seq += 1
        await asyncio.sleep(period)

async def ingest():
    global stored, invalid, ws_pushes
    while True:
        batch = [await q.get()]
        t0 = time.perf_counter()
        while len(batch) < 500 and time.perf_counter()-t0 < 0.05:
            try: batch.append(q.get_nowait())
            except asyncio.QueueEmpty: await asyncio.sleep(0.005)
        rows=[]; state={}
        for raw, tpub in batch:
            try: t = Telemetry.model_validate_json(raw)
            except Exception: invalid += 1; continue
            rows.append((t.robot_id,t.ts,t.x,t.y,t.heading,t.zone,t.battery,t.status,t.lidar_min_m,t.seq))
            state[t.robot_id]=(t.robot_id,t.ts,t.x,t.y,t.battery,t.status); last_seen[t.robot_id]=time.perf_counter()
        db.executemany("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO robot_state VALUES (?,?,?,?,?,?) ON CONFLICT(robot_id) DO UPDATE SET ts=excluded.ts,x=excluded.x,y=excluded.y,battery=excluded.battery,status=excluded.status", list(state.values()))
        db.commit()
        ws_pushes += 1  # one coalesced state diff pushed to UI per batch
        now = time.perf_counter()
        for _, tpub in batch: lat.append((now-tpub)*1000)
        stored += len(rows)

async def watchdog():
    while time.perf_counter()-start < DUR:
        await asyncio.sleep(0.5)
        now = time.perf_counter()
        for rid, ls in last_seen.items():
            if rid not in offline_detect and now-ls > HEARTBEAT_TIMEOUT:
                offline_detect[rid] = now-start-KILL_AT

async def main():
    global start
    start = time.perf_counter(); c0 = time.process_time()
    tasks=[asyncio.create_task(ingest()), asyncio.create_task(watchdog())]
    await asyncio.gather(*[robot(f"amr-{i:03d}") for i in range(N)])
    await asyncio.sleep(0.5)  # drain the last batch
    wall = time.perf_counter()-start; cpu = time.process_time()-c0
    for t in tasks: t.cancel()
    lat.sort()
    p = lambda k: lat[min(len(lat)-1,int(len(lat)*k))]
    print(json.dumps({"robots":N,"hz":HZ,"duration_s":DUR,"sent":sent,"stored":stored,"invalid_rejected":invalid,
      "msgs_per_s":round(stored/DUR,1),"lat_p50_ms":round(p(.5),1),"lat_p95_ms":round(p(.95),1),"lat_p99_ms":round(p(.99),1),"lat_max_ms":round(lat[-1],1),
      "cpu_pct_one_core":round(100*cpu/wall,1),"max_rss_mb":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
      "offline_detected_after_drop_s":{k:round(v,2) for k,v in offline_detect.items()},
      "db_rows":db.execute("select count(*) from telemetry").fetchone()[0],"db_mb":round(os.path.getsize(DB_PATH)/1e6,1),
      "ui_pushes_per_s":round(ws_pushes/wall,1)}))
asyncio.run(main())
