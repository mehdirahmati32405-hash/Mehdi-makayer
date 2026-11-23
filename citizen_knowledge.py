"""جست‌وجوی سبک و محلی در بانک دانش دستیار شهروندی ملایر.

محتوای این نسخه از فایل‌های آموزشی و شرح وظایف موجود پروژه تغذیه می‌شود.
تعرفه‌ها، نشانی مراکز و مقررات جزئی تا زمان ورود منبع رسمی، عمداً داده قطعی ندارند.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from education_content import TOPICS as EDUCATION_TOPICS
from services_content import DUTIES_TEXT


@dataclass(frozen=True)
class KnowledgeDocument:
    key: str
    title: str
    keywords: tuple[str, ...]
    content: str
    source: str


DOCUMENTS = [
    KnowledgeDocument(
        "waste", "تفکیک و دفع پسماند",
        ("زباله", "پسماند", "تفکیک", "بازیافت", "زباله تر", "زباله خشک", "سطل", "جمع آوری"),
        EDUCATION_TOPICS["waste"][1] + "\n\n" + EDUCATION_TOPICS["no_plastic"][1],
        "محتوای آموزشی شهروندی ربات",
    ),
    KnowledgeDocument(
        "debris", "نخاله ساختمانی",
        ("نخاله", "ساختمان", "آجر", "بتن", "گچ", "خاک", "جوی آب", "ضایعات ساختمانی"),
        EDUCATION_TOPICS["debris"][1],
        "محتوای آموزشی شهروندی ربات",
    ),
    KnowledgeDocument(
        "rats", "کنترل موش و آفات شهری",
        ("موش", "موش فاضلابی", "لانه موش", "جوندگان", "آفت", "سم", "تله"),
        EDUCATION_TOPICS["rats"][1],
        "محتوای آموزشی شهروندی ربات",
    ),
    KnowledgeDocument(
        "stray_dogs", "حیوانات بلاصاحب",
        ("سگ", "سگ بلاصاحب", "حیوان بلاصاحب", "گازگرفتگی", "هاری"),
        EDUCATION_TOPICS["stray_dogs"][1],
        "محتوای آموزشی شهروندی ربات",
    ),
    KnowledgeDocument(
        "plastic", "کاهش مصرف پلاستیک",
        ("پلاستیک", "کیسه پلاستیکی", "ظروف یکبار مصرف", "نه به پلاستیک"),
        EDUCATION_TOPICS["no_plastic"][1],
        "محتوای آموزشی شهروندی ربات",
    ),
    KnowledgeDocument(
        "municipal_duties", "وظایف معاونت خدمات شهری",
        ("وظایف شهرداری", "خدمات شهری", "نظافت", "فضای سبز", "سد معبر", "کانال", "مسیل", "جمع آوری پسماند"),
        DUTIES_TEXT,
        "شرح وظایف درج‌شده در پروژه",
    ),
]


def _normalize(value: str) -> str:
    value = (value or "").replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ").replace("‌", " ")
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def retrieve_knowledge(question: str, limit: int = 3) -> str:
    """Return the most relevant local knowledge excerpts; empty when no match."""
    query = _normalize(question)
    if not query:
        return ""

    scored = []
    for document in DOCUMENTS:
        keywords = [_normalize(word) for word in document.keywords]
        score = sum(2 if keyword in query else 0 for keyword in keywords if keyword)
        # Token overlap helps with natural phrasing and inflections.
        query_tokens = set(query.split())
        keyword_tokens = set(" ".join(keywords).split())
        score += len(query_tokens & keyword_tokens)
        if score:
            scored.append((score, document))

    scored.sort(key=lambda item: item[0], reverse=True)
    excerpts = []
    for _score, document in scored[:max(1, limit)]:
        excerpts.append(
            f"موضوع: {document.title}\n"
            f"منبع: {document.source}\n"
            f"محتوا:\n{document.content.strip()}"
        )

    if not excerpts:
        return ""
    return "\n\n---\n\n".join(excerpts)


def knowledge_status() -> dict[str, int]:
    """Small summary for tests and future admin diagnostics."""
    return {"documents": len(DOCUMENTS)}
