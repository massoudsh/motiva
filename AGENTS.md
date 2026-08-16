# AGENTS.md — دستورالعمل نگهداری ویکی دانش پروژه

> هر ایجنت هوش مصنوعی که روی این ریپو کار می‌کند باید این فایل را قبل از شروع بخواند.

## ویکی دانش پروژه (فعال)
مسیر: `docs/wiki/`. این یک قانون اکید است، نه پیشنهاد.

### شروع هر مکالمه
- **اول** `docs/wiki/overview.md` و `docs/wiki/index.md` را بخوان (≤۸۰۰ توکن). از re-scan کل کدبیس خودداری کن.
- فقط صفحاتِ **مرتبط** (`docs/wiki/entities/*.md`, `docs/wiki/concepts/*.md`) را در صورتِ نیاز drill-down کن.

### به‌روزرسانی ویکی — یک‌بار در پایانِ هر تغییر معنایی
اگر تغییری معنایی در کد یا محتوای پروژه دادی (نه صرفاً typo/فرمت):
1. تشخیص بده این تغییر روی کدام entity/concept در `docs/wiki/` اثر می‌گذارد.
2. صفحه‌ی مربوطه را به‌روز کن (فیلد جدید، امضای تابع، route جدید، dependency جدید، edge case).
3. اگر entity/concept کاملاً جدید و مهم است (≥۳ جای دیگر به آن ارجاع می‌دهند)، صفحه جدید در `docs/wiki/entities/` یا `docs/wiki/concepts/` بساز و در `index.md` لینک بده.
4. یک خط در `docs/wiki/log.md` اضافه کن: `## [YYYY-MM-DD] update | <خلاصه>`.

### قراردادهای ساخت/لینک
- نام فایل‌ها lowercase + hyphen (مثال: `user-model.md`).
- لینک‌ها به سبک Obsidian: `[[entities/user]]` بدون `.md`.
- قواعد کامل در `docs/wiki/schema.md`.

### همگام‌سازی با GitHub Wiki
این ریپو یک GitHub Wiki فعال هم دارد (`https://github.com/massoudsh/motiva/wiki`) که آینه‌ای (flat) از `docs/wiki/` است. وقتی صفحه‌ای در `docs/wiki/` تغییر معنایی کرد، همان تغییر را در صفحه متناظر GitHub Wiki هم اعمال کن (نگاشت نام: `entities/x.md` → `Entity-X`, `concepts/y.md` → `Concept-Y`, بقیه صفحات با همان نام با حرف بزرگ اول).

منبع اصلی حقیقت همیشه `docs/wiki/` داخل خود ریپو است؛ GitHub Wiki فقط نسخه قابل‌مرور برای انسان‌هاست.
