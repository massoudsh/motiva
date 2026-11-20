# Operations dashboard

> داشبورد RTL و API محلی برای پایش ناوگان AMR و مدیریت مأموریت‌های نمونه.

## مسئولیت‌ها
- نمایش شمارش واقعی ربات‌های آنلاین، میانگین باتری و مأموریت‌های فعال.
- نمایش موقعیت نسبی ربات‌ها و جدول آخرین telemetry ذخیره‌شده.
- نمایش هشدارهای باتری کم، آفلاین بودن ربات و مأموریت‌های در صف.
- جست‌وجو و فیلتر مأموریت‌های اخیر، فرم native برای ایجاد/تخصیص/لغو.
- نمایش metadata حمل مأموریت شامل بار، اولویت، deadline و منبع manual/WMS.
- ارائهٔ نقشهٔ گرافی، مسیر کوتاه و مانع موقت از API.
- دریافت eventهای نسخه‌دار WMS با امضای HMAC و idempotency.
- دریافت پیام‌های VDA 5050 (state و connection) از gateway و محاسبهٔ آفلاین از تازگی heartbeat.
- نمایش توقف اضطراری و ورود به میدان حفاظتی به‌عنوان هشدار.
- ارائهٔ گزارش پایهٔ مأموریت، ناوگان و تعداد نمونه‌های telemetry.
- نمایش صادقانه وضعیت prototype و نبود اتصال مستقیم سخت‌افزار.

## قراردادهای API
- `GET /api/alerts` — هشدارهای عملیاتی فعلی.
- `GET /api/reports` — KPIهای پایهٔ تجمعی.
- `GET /api/map` — گره‌ها، یال‌ها و موانع فعال.
- `POST /api/map/nodes|edges|obstacles|route` — مدیریت گراف و محاسبهٔ مسیر.
- `POST /api/integrations/events` — event نسخهٔ ۱ با `X-Motiva-Signature`؛ برای event تکراری مأموریت جدید ساخته نمی‌شود.
- `POST /api/integrations/vda5050` — پیام `state` یا `connection` با `agv_id`؛ بدون secret (سطح جداگانه از webhook WMS) و فقط ورودی.

## قراردادها / Edge cases
- API محلی از SQLite استفاده می‌کند؛ داده‌های ناوگان نمونه و مأموریت‌ها production نیستند.
- KPIهای کل از کل جدول محاسبه می‌شوند؛ جدول مأموریت فقط ۱۰ رکورد اخیر را نشان می‌دهد.
- در قطع API، عملیات غیرفعال و تازگی آخرین داده به کاربر اعلام می‌شود.
- مسیر در گراف بدون جهت محاسبه می‌شود و گره‌های دارای مانع فعال کنار گذاشته می‌شوند.
- webhook بدون secret پیکربندی‌شده یا signature معتبر پذیرفته نمی‌شود.
- ربات وقتی آفلاین است که heartbeat قدیمی‌تر از `MOTIVA_HEARTBEAT_TIMEOUT_SECONDS` داشته باشد یا هیچ heartbeat نداشته باشد؛ `status` گزارش‌شده جدا از `status` مشتق‌شده برگردانده می‌شود.
- ربات stale آنلاین شمرده نمی‌شود، هشدار باتری کم برایش جای هشدار آفلاین را نمی‌گیرد و مأموریت نمی‌گیرد.
- مختصات VDA بر حسب متر روی نقشهٔ ربات است و با `MOTIVA_MAP_EXTENT_METRES` به شبکهٔ ۰ تا ۱۰۰ تبدیل و clamp می‌شود.
- ساخت order خروجی VDA پیاده‌سازی شده اما هیچ چیزی روی `order/{agv_id}` منتشر نمی‌شود؛ هیچ endpoint ادعای ارسال فرمان به ربات ندارد.
- `MOTIVA_HOST` و `MOTIVA_PORT` قابل تنظیم‌اند (پیش‌فرض `127.0.0.1:8787`)؛ در کانتینر روی `0.0.0.0:8787` اجرا می‌شود و مسیر پوشهٔ دیتابیس را می‌سازد.
- `docker compose up -d --build` سرویس `app` و صفحهٔ فرود nginx را بالا می‌آورد؛ TimescaleDB، EMQX و Keycloak فقط با پروفایل `platform` فعال می‌شوند و کد فعلی از آن‌ها استفاده نمی‌کند.

## منابع کد
- `app/index.html` — رابط RTL، هشدارها، dialogهای native، فیلترها و وضعیت اتصال.
- `app/server.py` — API health/overview/robots/telemetry/missions/map/alerts/reports/integrations.
- `app/navigation.py` — مسیر کوتاه و رزرو گره‌های متعارض.
- `app/integration.py` — قرارداد event و HMAC.
- `app/test_server.py` و `app/test_integration.py` — تست‌های API و قرارداد integration.
- `Dockerfile`، `docker-compose.yml` و `.github/workflows/quality.yml` — بسته‌بندی کانتینر و بیلد/اسموک‌تست تصویر در CI.
