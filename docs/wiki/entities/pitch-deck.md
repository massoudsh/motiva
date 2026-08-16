# Pitch Deck

> پیچ‌دک ۹ اسلایدی موجَک | Motiva برای جذب سرمایه/design partner.

## مسئولیت‌ها
اسلایدها به ترتیب: کاور → مسئله #۰۸۴ → چرا الان (AGV vs AMR) → راه‌حل (۴ ستون) → معماری → مسیر رشد محصول (۳ فاز) → بازار و مدل کسب‌وکار → دفاع‌پذیری رقابتی (نمودار جابه‌جایی ارزش) → چشم‌انداز و CTA.

## پیاده‌سازی
- سورس ویرایش‌پذیر: `pitch/motiva-pitch-deck.html` (HTML/CSS تک‌فایل، هر `<section class="slide">` یک اسلاید ثابت‌اندازه برای رندر به تصویر).
- خروجی نهایی از طریق رندر هر اسلاید به تصویر full-bleed:
  - `outputs/motiva-pitch-deck.pdf`
  - `outputs/motiva-pitch-deck.pptx` (هر اسلاید = یک تصویر داخل PowerPoint، قابل ویرایش با جایگزینی تصویر)

## وابستگی‌ها
- [[concepts/brand-identity]] — پالت/فونت/گرادیان امضا
- [[concepts/dev-roadmap]] — فاز‌های مسیر رشد محصول (اسلاید ۶) مبنای milestoneهای GitHub شدند

## قراردادها / Edge cases
- **باگ حل‌شده:** گرادیان روی متن چندخطی (`grad-text` با `-webkit-background-clip: text`) در اسلاید آخر باعث آرتیفکت جعبه‌ای دور متن می‌شد. راه‌حل: روی متن چندخطی گرادیان را حذف و تک‌رنگ کن؛ گرادیان فقط برای متن **تک‌خطی** امن است.
- **باگ حل‌شده:** بج (badge) کاور به‌اشتباه کل عرض اسلاید را می‌گرفت — با محدود کردن `width`/`display:inline-flex` رفع شد.
- برای هر تغییر اسلاید، بعد از ویرایش HTML باید دوباره رندر (PDF/PPTX) و QA بصری کامل انجام شود.

## منابع کد
- `pitch/motiva-pitch-deck.html:53` — بج کاور
- `pitch/motiva-pitch-deck.html:120-149` — اسلاید راه‌حل (۴ ستون)
- `pitch/motiva-pitch-deck.html:151-175` — اسلاید معماری
- `pitch/motiva-pitch-deck.html:177-199` — اسلاید مسیر رشد محصول
- `pitch/motiva-pitch-deck.html:231-` — اسلاید دفاع‌پذیری رقابتی (نمودار SVG)
