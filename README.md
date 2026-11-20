<div align="center">

# موجَک | Motiva

### هوش پشت هر حرکت

**پلتفرم هوشمند مدیریت ناوگان ربات‌های خودران (AMR) و اتوماسیون لجستیک داخلی کارخانه و انبار**

[![Landing Page](https://img.shields.io/badge/Landing-Page-22D3EE?style=flat-square)](./landing/index.html)
[![Operations App](https://img.shields.io/badge/Operations-App-34D399?style=flat-square)](./app/index.html)
[![Pitch Deck](https://img.shields.io/badge/Pitch-Deck-6366F1?style=flat-square)](./outputs/motiva-pitch-deck.pdf)
[![Brand Identity](https://img.shields.io/badge/Brand-Identity-F59E0B?style=flat-square)](./brand/motiva-brand-identity.md)

</div>

---

## درباره پروژه

جابه‌جایی داخلی در کارخانه و انبار هنوز عمدتاً **دستی** یا وابسته به **AGV با مسیر ثابت** انجام می‌شود؛ راه‌حلی کند، غیرمنعطف و ناسازگار با تغییرات چیدمان.

**موجَک (Motiva)** یک لایه هوشمند بالای ناوگان ربات‌های خودران (AMR) قرار می‌گیرد و بدون مسیر ثابت، مسیر بهینه را در لحظه تشخیص می‌دهد، جریان مواد را بهینه می‌کند، ده‌ها ربات را هماهنگ مدیریت می‌کند و مستقیم به سیستم‌های سازمانی (ERP/WMS/MES) متصل می‌شود.

> پلتفرم هوش مصنوعی برای ناوبری، هماهنگی و بهینه‌سازی ناوگان ربات‌های خودران در کارخانه و انبار — بدون مسیر ثابت، با یادگیری از محیط پویا.

## چهار ستون هوشمندی

| # | ستون | توضیح |
|---|---|---|
| ۱ | **ناوبری خودران پویا** | حرکت بدون مسیر ثابت، تشخیص لحظه‌ای موانع و بازطراحی مسیر |
| ۲ | **بهینه‌سازی جریان مواد** | شناسایی گلوگاه‌ها و بازتخصیص هوشمند مأموریت‌ها |
| ۳ | **مدیریت ناوگان** | هماهنگی هم‌زمان صدها ربات و زمان‌بندی شارژ و بار عملیاتی |
| ۴ | **یکپارچگی ERP/WMS/MES** | اتصال مستقیم به سیستم‌های موجود کارخانه |

## معماری کلی

```
🤖 ناوگان AMR  →  🧠 هسته هوشمند موجَک  →  🏭 سیستم‌های کارخانه
(سنسور، لیدار،      (ناوبری · بهینه‌سازی      (ERP · WMS · MES)
 دوربین هر ربات)      جریان · مدیریت ناوگان)
```

## مسیر رشد محصول

1. **استقرار با Design Partner** — شروع با یک کارخانه واقعی؛ اثبات کاهش زمان و هزینه لجستیک داخلی
2. **مقیاس‌گیری ناوگان** — افزایش تعداد ربات‌ها و صنایع؛ حرکت ارزش به سمت لایه نرم‌افزار
3. **پلتفرم جامع لجستیک** — سیستم مدیریت لجستیک داخلی با Digital Twin و یکپارچگی کامل با ERP/WMS/MES

نقشه‌راه فنی دقیق‌تر در بخش [Issues](../../issues) این ریپو پیگیری می‌شود.

## بازار هدف

FMCG و خودروسازی · فولاد و معدن · دارو و لجستیک سلامت · لجستیک و تجارت الکترونیک

مدل کسب‌وکار: **Enterprise (سخت‌افزار + SaaS)** با درآمد تکرارشونده از لایه نرم‌افزار.

## ساختار ریپو

```
brand/     هویت بصری — لوگو، پالت رنگ، تایپوگرافی، لحن برند
landing/   صفحه فرود محصول (index.html)
app/       داشبورد عملیات و API محلی fleet (prototype)
pitch/     سورس HTML پیچ‌دک قابل ویرایش
outputs/   خروجی نهایی پیچ‌دک (PDF و PPTX)
docs/wiki/ ویکی دانش زنده پروژه (overview، roadmap، entityها)
```

## Docker

The image runs the operations API and dashboard. The landing page is served by an nginx container, and the ADR-001 target stack (TimescaleDB, EMQX, Keycloak) is available as an optional Compose profile.

```bash
cp .env.example .env          # optional: set secrets and host ports
docker compose up -d --build  # app (API + dashboard) and landing page
docker compose ps             # health and published ports
```

| URL | Service |
|---|---|
| http://localhost:8787 | Operations dashboard and API |
| http://localhost:8787/api/health | API health check |
| http://localhost:8080 | Landing page (nginx) |

Without Compose, the image can be run directly:

```bash
docker build -t motiva:local .
docker run --rm -p 8787:8787 -v motiva-data:/data motiva:local
```

Optional target-stack services (not consumed by the prototype yet):

```bash
docker compose --profile platform up -d
```

| URL / port | Service |
|---|---|
| localhost:5432 | TimescaleDB (`motiva` / `motiva`) |
| localhost:1883, localhost:8083 | EMQX MQTT and WebSocket |
| http://localhost:18083 | EMQX dashboard |
| http://localhost:8081 | Keycloak admin console |

Operational commands:

```bash
docker compose logs -f app      # follow application logs
docker compose stop app         # stop one service
docker compose down             # stop and remove containers (volumes kept)
docker compose down -v          # remove containers and data volumes
```

The SQLite database lives in the `motiva-data` volume at `/data/motiva.sqlite3`. The app listens on `0.0.0.0:8787` inside the container and runs as a non-root user. `POST /api/integrations/events` returns `503` until `MOTIVA_WEBHOOK_SECRET` is set.

## Robot telemetry (VDA 5050)

`app/vda5050.py` translates VDA 5050 state and connection messages. An MQTT gateway subscribed to `state/{agv_id}` and `connection/{agv_id}` forwards them to:

```bash
curl -X POST http://localhost:8787/api/integrations/vda5050 \
  -H 'Content-Type: application/json' \
  -d '{"agv_id":"R-07","message_type":"state","payload":{"batteryState":{"batteryCharge":62},"agvPosition":{"x":30,"y":40,"positionInitialized":true},"orderId":""}}'
```

A robot counts as offline once its last heartbeat is older than `MOTIVA_HEARTBEAT_TIMEOUT_SECONDS` (default 30), and a stale robot can't be assigned missions. Vehicle coordinates are metres on the robot's own map, scaled to `MOTIVA_MAP_EXTENT_METRES` for the dashboard grid.

**Not wired:** nothing publishes orders back to `order/{agv_id}`. `order_message()` builds a valid VDA order, but no command reaches a robot yet. VDA 5050 also defines no traffic coordination, routing or functional safety — those stay fleet-manager work.

## Auto-dispatch

`GET /api/missions/{id}/dispatch` is a dry run that returns who would be chosen, why, and which robots were excluded:

```bash
curl http://localhost:8787/api/missions/2046/dispatch
```

`POST /api/missions/{id}/assign` with `{"auto": true}` performs the choice. Robots that are offline, charging, below 20% or unreported are excluded with a reason; the rest are scored on battery, workload and (when the origin names a placed map node) distance. Weights are renormalised when a signal is missing, and `distance_used` says plainly whether proximity was actually considered.

## Traffic reservations

`POST /api/map/route` can plan around other robots and lease the corridor it intends to use:

```bash
curl -X POST http://localhost:8787/api/map/route \
  -H 'Content-Type: application/json' \
  -d '{"start":"A","goal":"C","robot":"R-01","reserve":true}'
```

Only transit nodes are exclusive — a mission's start and goal are shared stations. If another robot holds the corridor, the response routes around it and reports `traffic_applied` with `reserved_by`; if nothing else is available it returns `409 blocked_by_traffic` rather than pretending the map is broken. Leases expire, one holder per node is enforced by the database, and `GET /api/map` lists active reservations.

This is vertex-level, time-boxed reservation, not full traffic management: there is no deadlock-resolution loop and no per-segment time window.

## Charger allocation

Register bays, then send a low robot to charge:

```bash
curl -X POST http://localhost:8787/api/chargers \
  -H 'Content-Type: application/json' -d '{"id":"C1","name":"Bay 1","x":20,"y":20}'

curl http://localhost:8787/api/robots/R-01/charge        # dry run: should it charge, and where?
curl -X POST http://localhost:8787/api/robots/R-01/charge -H 'Content-Type: application/json' -d '{}'
```

A robot is sent to charge at or below 25% (5% is flagged critical), and never while offline, already charging, or with an unknown battery. The nearest free bay wins; requesting an occupied one returns `charger_unavailable` rather than silently reassigning it. Leaving the bay — reporting `moving` or `waiting` over HTTP or VDA 5050 — releases it immediately.

A robot refused because every bay is busy is queued rather than forgotten. `GET /api/chargers` returns `waiting` and `admit_now`: critical robots go first, then anyone waiting past 10 minutes, then lowest battery. A critical or starving waiter raises a `charger_queue_stuck` alert with its reason and wait time.

Dispatch uses the same threshold: a robot at or below 25% is not offered new missions, so it cannot keep deferring the charge it needs.

## معماری و توسعه

- [معماری فنی](./ARCHITECTURE.md)
- [تنظیمات محلی نمونه](./.env.example)
- تست‌ها: `python -m unittest discover -s app -p 'test_*.py'`


## مستندات

- [هویت برند](./brand/motiva-brand-identity.md)
- [پیچ‌دک (PDF)](./outputs/motiva-pitch-deck.pdf)
- [پیچ‌دک (PPTX — قابل ویرایش)](./outputs/motiva-pitch-deck.pptx)
- [سورس پیچ‌دک (HTML)](./pitch/motiva-pitch-deck.html)

## ویکی دانش پروژه

مستندات فنی زنده (overview، نقشه‌راه، entityها) در [`docs/wiki/`](./docs/wiki/) نگهداری می‌شود و با رشد پروژه به‌روزرسانی می‌گردد؛ نسخه قابل‌مرور همان محتوا روی [GitHub Wiki](../../wiki) هم منتشر شده. قوانین نگهداری در [`AGENTS.md`](./AGENTS.md).

---

<div align="center">

**موجَک | Motiva** — زیرساخت هوشمند Industrial Mobility

</div>
