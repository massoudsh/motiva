# Spike: ingestion تله‌متری ۵۰ ربات

> برای #18 (ADR-001)، گزینه B: Python. کد یکبارمصرف برای اعتبارسنجی تصمیم؛ کد تولیدی نیست.

## اجرا
```bash
cd spikes/telemetry
pip install -r requirements.txt
python spike.py 50 10 20     # robots hz seconds [db_path]
python spike.py 500 10 15    # stress
```
خروجی یک خط JSON با throughput، latency (p50/p95/p99/max)، CPU، RAM، زمان تشخیص offline و حجم DB است.

## چه چیزی شبیه‌سازی می‌شود
- هر ربات ۱۰ پیام در ثانیه: موقعیت، heading، zone، باتری، وضعیت، لیدار، seq
- اعتبارسنجی pydantic؛ ۰.۱٪ پیام‌ها عمداً معیوب (باتری > ۱۰۰)
- batch insert (پنجره ۵۰ms / حداکثر ۵۰۰) + upsert جدول `robot_state`
- یک push وضعیت coalesced به UI به‌ازای هر batch
- watchdog با heartbeat timeout ۳ ثانیه؛ `amr-007` و `amr-023` در نیمه اجرا قطع می‌شوند

## نتایج (2026-10-04)
| ربات | پیام/ثانیه | p50 | p95 | p99 | max | CPU (یک هسته) | RAM |
|---|---|---|---|---|---|---|---|
| **۵۰** | ۴۸۶ | ۳۳ms | ۵۷ms | ۶۱ms | ۷۶ms | ۴.۴٪ | ۳۵MB |
| ۲۰۰ | ۱۹۶۹ | ۳۴ms | ۵۹ms | ۶۵ms | ۷۱ms | ۸.۹٪ | ۳۷MB |
| ۵۰۰ | ۴۹۲۷ | ۴۰ms | ۶۷ms | ۷۵ms | ۸۲ms | ۱۹٪ | ۴۰MB |

- بیشتر latency از پنجره batch ۵۰ms است (عمدی)
- تشخیص offline: ۳.۰ تا ۳.۵ ثانیه پس از قطع
- همه پیام‌های معیوب رد شدند
- ذخیره‌سازی: ۵۰ ربات × ۱۰Hz ≈ ۴۳ میلیون ردیف/روز ≈ ۴GB/روز فشرده‌نشده → سیاست retention در #15

## محدودیت‌ها
- صف in-process جای بروکر MQTT (EMQX) و SQLite (WAL) جای TimescaleDB. این spike مسیر ingestion پایتون را می‌سنجد، نه بروکر/DB.
- شبکه واقعی، ارسال مجدد و قطع/وصل Wi-Fi صنعتی شبیه‌سازی نشده‌اند.

## گام بعدی
- [ ] تکرار با EMQX + TimescaleDB واقعی (Docker Compose)
- [ ] اندازه‌گیری حجم بعد از compression

مرتبط: #18 · #15 · [[concepts/dev-roadmap]]
