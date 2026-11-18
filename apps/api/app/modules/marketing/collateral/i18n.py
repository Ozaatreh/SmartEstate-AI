"""Fixed English/Arabic wording for brochures and posters.

Only interface wording is translated here (headings, labels, unit-type names, month names). Project data — names,
descriptions, amenities, plan names — is printed exactly as stored, in its own language, and never machine-translated.
Numbers stay in Western digits in both languages so they can be checked against the database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

Lang = Literal["en", "ar"]

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
}

T: dict[str, dict[str, str]] = {
    "brand_tagline": {"en": "Real estate", "ar": "عقارات"},
    "starting_from": {"en": "Starting from", "ar": "تبدأ الأسعار من"},
    "overview": {"en": "Overview", "ar": "نظرة عامة"},
    "location": {"en": "Location", "ar": "الموقع"},
    "city": {"en": "City", "ar": "المدينة"},
    "district": {"en": "District", "ar": "الحي"},
    "status": {"en": "Status", "ar": "حالة المشروع"},
    "handover": {"en": "Handover", "ar": "التسليم"},
    "available_homes": {"en": "Homes available", "ar": "الوحدات المتاحة"},
    "amenities": {"en": "Amenities & facilities", "ar": "المرافق والخدمات"},
    "units": {"en": "Available homes", "ar": "الوحدات المتاحة"},
    "unit_type": {"en": "Type", "ar": "نوع الوحدة"},
    "area": {"en": "Area", "ar": "المساحة"},
    "available": {"en": "Available", "ar": "متاح"},
    "price_from": {"en": "From", "ar": "يبدأ من"},
    "payment_plans": {"en": "Payment plans", "ar": "خطط الدفع"},
    "down_payment": {"en": "Down payment", "ar": "الدفعة الأولى"},
    "installments": {"en": "Instalments", "ar": "الأقساط"},
    "on_handover": {"en": "On handover", "ar": "عند التسليم"},
    "contact": {"en": "Contact & enquiries", "ar": "التواصل والاستفسارات"},
    "phone": {"en": "Phone", "ar": "الهاتف"},
    "email": {"en": "Email", "ar": "البريد الإلكتروني"},
    "website": {"en": "Website", "ar": "الموقع الإلكتروني"},
    "enquire": {
        "en": "Prices and availability change. Please confirm with our sales team before making a decision.",
        "ar": "الأسعار والتوفر قابلة للتغيير. يرجى التأكد من فريق المبيعات قبل اتخاذ أي قرار.",
    },
    "demo_title": {"en": "Fictional demo project", "ar": "مشروع تجريبي وهمي"},
    "demo_body": {
        "en": "This project, its homes, prices and payment plans are fictional demonstration data. Nothing in this "
        "document is an offer for sale.",
        "ar": "هذا المشروع ووحداته وأسعاره وخطط الدفع فيه بيانات تجريبية وهمية لأغراض العرض فقط، ولا يُعد أي شيء في هذا المستند عرضاً للبيع.",
    },
    "demo_short": {"en": "Fictional demo project · not an offer for sale", "ar": "مشروع تجريبي وهمي · ليس عرضاً للبيع"},
    "as_of": {"en": "Figures as of", "ar": "الأرقام بتاريخ"},
    "price_note": {"en": "Prices are list prices in Saudi riyals.", "ar": "الأسعار المذكورة هي أسعار القائمة بالريال السعودي."},
    "image_placeholder": {"en": "Project imagery to follow", "ar": "صور المشروع قريباً"},
    "image_credit": {"en": "Image credits", "ar": "حقوق الصور"},
    "studio": {"en": "Studio", "ar": "استوديو"},
    "homes": {"en": "homes", "ar": "وحدة"},
}

STATUS = {
    "planning": {"en": "In planning", "ar": "قيد التخطيط"},
    "launched": {"en": "Launched", "ar": "تم الإطلاق"},
    "under_construction": {"en": "Under construction", "ar": "قيد الإنشاء"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
}

FREQUENCY = {
    "monthly": {"en": "monthly", "ar": "شهرية"},
    "quarterly": {"en": "quarterly", "ar": "ربع سنوية"},
    "semi_annual": {"en": "semi-annual", "ar": "نصف سنوية"},
    "annual": {"en": "annual", "ar": "سنوية"},
}

CTAS = {
    "book_viewing": {"en": "Book a viewing", "ar": "احجز موعد زيارة"},
    "register_interest": {"en": "Register your interest", "ar": "سجّل اهتمامك"},
    "enquire_now": {"en": "Enquire now", "ar": "استفسر الآن"},
    "visit_sales": {"en": "Visit our sales team", "ar": "تواصل مع فريق المبيعات"},
}


def t(key: str, lang: Lang) -> str:
    return T[key][lang]


def money(v: Decimal, lang: Lang) -> str:
    n = f"{int(v):,}" if v == v.to_integral_value() else f"{v:,.2f}"
    return f"SAR {n}" if lang == "en" else f"{n} ريال"


def number(v: Decimal | int) -> str:
    d = Decimal(v)
    return f"{int(d):,}" if d == d.to_integral_value() else f"{d.normalize():f}"


def pct(v: Decimal) -> str:
    return f"{number(v)}%"


def area_range(lo: Decimal, hi: Decimal, lang: Lang) -> str:
    unit = "m²" if lang == "en" else "م²"
    return f"{number(lo)} {unit}" if lo == hi else f"{number(lo)}–{number(hi)} {unit}"


def month_year(d: date, lang: Lang) -> str:
    return f"{MONTHS[lang][d.month - 1]} {d.year}"


def day_month_year(d: date, lang: Lang) -> str:
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def bedrooms(n: int, lang: Lang) -> str:
    if n == 0:
        return t("studio", lang)
    if lang == "en":
        return f"{n} bedroom" if n == 1 else f"{n} bedrooms"
    return {1: "غرفة نوم واحدة", 2: "غرفتا نوم"}.get(n, f"{n} غرف نوم")


def bedroom_span(options: list[int], lang: Lang) -> str:
    lo, hi = min(options), max(options)
    if lo == hi:
        return bedrooms(lo, lang)
    if lang == "en":
        first = t("studio", lang) if lo == 0 else str(lo)
        return f"{first} to {hi} bedrooms"
    first = t("studio", lang) if lo == 0 else str(lo)
    return f"من {first} إلى {hi} غرف نوم"


def plan_summary(down: Decimal, installments: int, frequency: str, handover: Decimal, lang: Lang) -> str:
    parts = [f"{pct(down)} {'down payment' if lang == 'en' else 'دفعة أولى'}"]
    if installments:
        freq = FREQUENCY[frequency][lang]
        parts.append(f"{installments} {freq} instalments" if lang == "en" else f"{installments} أقساط {freq}")
    if handover:
        parts.append(f"{pct(handover)} {'on handover' if lang == 'en' else 'عند التسليم'}")
    return " · ".join(parts)
