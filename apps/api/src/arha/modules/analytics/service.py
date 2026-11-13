"""Per question summaries (F-ANA-01) and cookie free funnel (F-ANA-02)."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arha.modules.submissions.models import Submission

STOPWORDS = set("""le la les un une des de du et ou en au aux a à ce ces cet cette je tu il elle nous vous ils elles
on que qui quoi dont pour par sur dans avec sans pas ne plus est sont été être avoir ai as avons avez ont mon ma mes
ton ta tes son sa ses notre nos votre vos leur leurs se sa y the a an and or of to in on for with is are was were be
it this that i you he she we they my your our their not no yes oui non très tres bien""".split())


async def completed(db: AsyncSession, form_id: uuid.UUID, limit: int = 100_000) -> list[Submission]:
    stmt = (select(Submission).where(Submission.form_id == form_id, Submission.is_partial.is_(False),
                                     Submission.deleted_at.is_(None), Submission.submitted_at.is_not(None))
            .order_by(Submission.submitted_at).limit(limit))
    return list((await db.execute(stmt)).scalars())


def _label(node: dict[str, Any], locale: str) -> str:
    lab = node.get("label") or {}
    return str(lab.get(locale) or lab.get("fr") or lab.get("en") or node.get("id"))


def summarize(schema: dict[str, Any], subs: list[Submission], locale: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in schema.get("pages", []):
        for b in page.get("blocks", []):
            t, bid = b["type"], b["id"]
            values = [(s.answers or {}).get(bid) for s in subs]
            answered = [v for v in values if v not in (None, "", [], {})]
            item: dict[str, Any] = {"id": bid, "type": t, "label": _label(b, locale), "answered": len(answered),
                                    "total": len(subs)}
            if t in ("single_choice", "dropdown", "multi_choice"):
                counts: Counter[str] = Counter()
                for v in answered:
                    counts.update(v if isinstance(v, list) else [v])
                item["chart"] = "bar"
                item["data"] = [{"key": o["id"], "label": _label(o, locale), "count": counts.get(o["id"], 0)}
                                for o in b.get("options") or []]
            elif t == "yes_no":
                item["chart"] = "bar"
                item["data"] = [{"key": "yes", "label": "Oui" if locale == "fr" else "Yes",
                                 "count": sum(1 for v in answered if v is True)},
                                {"key": "no", "label": "Non" if locale == "fr" else "No",
                                 "count": sum(1 for v in answered if v is False)}]
            elif t in ("number", "rating", "linear_scale", "nps", "payment_open"):
                nums = sorted(float(v) for v in answered if isinstance(v, int | float) and not isinstance(v, bool))
                item["chart"] = "histogram"
                item["stats"] = _stats(nums)
                item["data"] = _histogram(nums, discrete=t in ("rating", "linear_scale", "nps"))
                if t == "nps" and nums:
                    promoters = sum(1 for n in nums if n >= 9)
                    detractors = sum(1 for n in nums if n <= 6)
                    item["nps"] = round((promoters - detractors) * 100 / len(nums))
            elif t in ("short_text", "long_text") and not b.get("identifying"):
                words: Counter[str] = Counter()
                for v in answered:
                    words.update(w for w in re.findall(r"[a-zà-ÿ']{3,}", str(v).lower()) if w not in STOPWORDS)
                item["chart"] = "words"
                item["data"] = [{"word": w, "count": c} for w, c in words.most_common(40)]
            elif t in ("product_choice", "ticket_choice"):
                qty: Counter[str] = Counter()
                for v in answered:
                    if isinstance(v, dict):
                        qty.update({k: int(q) for k, q in v.items() if isinstance(q, int)})
                item["chart"] = "bar"
                item["data"] = [{"key": o["id"], "label": _label(o, locale), "count": qty.get(o["id"], 0)}
                                for o in b.get("options") or []]
            else:
                continue
            out.append(item)
    return out


def _stats(nums: list[float]) -> dict[str, float | None]:
    if not nums:
        return {"min": None, "max": None, "mean": None, "median": None}
    n = len(nums)
    median = nums[n // 2] if n % 2 else (nums[n // 2 - 1] + nums[n // 2]) / 2
    return {"min": nums[0], "max": nums[-1], "mean": round(sum(nums) / n, 2), "median": median}


def _histogram(nums: list[float], *, discrete: bool, bins: int = 10) -> list[dict[str, Any]]:
    if not nums:
        return []
    if discrete:
        c = Counter(int(n) for n in nums)
        return [{"key": str(k), "label": str(k), "count": c[k]} for k in range(int(nums[0]), int(nums[-1]) + 1)]
    lo, hi = nums[0], nums[-1]
    if lo == hi:
        return [{"key": str(lo), "label": f"{lo:g}", "count": len(nums)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for n in nums:
        counts[min(bins - 1, int((n - lo) / width))] += 1
    return [{"key": str(i), "label": f"{lo + i * width:g} - {lo + (i + 1) * width:g}", "count": c}
            for i, c in enumerate(counts)]


def funnel_view(raw: dict[str, int], schema: dict[str, Any], locale: str) -> dict[str, Any]:
    fields = []
    for page in schema.get("pages", []):
        for b in page.get("blocks", []):
            key = f"field:{b['id']}"
            if key in raw:
                fields.append({"id": b["id"], "label": _label(b, locale), "reached": raw[key]})
    return {"views": raw.get("view", 0), "starts": raw.get("start", 0), "completes": raw.get("complete", 0),
            "fields": fields}
