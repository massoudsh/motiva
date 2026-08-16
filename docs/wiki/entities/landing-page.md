# Landing Page

> صفحه فرود بازاریابی محصول موجَک | Motiva.

## مسئولیت‌ها
- معرفی محصول، مسئله، راه‌حل، مسیر رشد و CTA درخواست دمو در یک صفحه اسکرول.
- بخش‌ها: Hero → Problem (#۰۸۴) → Solution (۴ ستون) → Growth path (۳ کارت) → CTA نهایی.

## پیاده‌سازی
فایل استاتیک تک‌صفحه‌ای، Tailwind CSS از CDN، بدون build step یا framework.

## وابستگی‌ها
- [[concepts/brand-identity]] — رنگ/فونت/لحن یکسان با پیچ‌دک و README

## قراردادها / Edge cases
- تمام کلاس‌های رنگ سفارشی (`bg-ink`, `text-signal`, `bg-action`, `bg-motion`) باید با مقادیر HEX تعریف‌شده در برند مطابق باشند؛ اگر رنگ جدید لازم شد، اول `brand/motiva-brand-identity.md` را آپدیت کن.
- زبان: فارسی، RTL.

## منابع کد
- `landing/index.html` — کل صفحه (۲۷۲ خط)
