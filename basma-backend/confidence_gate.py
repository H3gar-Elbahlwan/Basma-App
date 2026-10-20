"""
بصمة - العضو C: بوابة الثقة (Confidence Gate)

القرار بيكون واحد من تلاتة:
    ACCEPT         -> انطق النتيجة للمستخدم
    RETRY          -> اطلب منه يصوّر تاني (مع إرشاد: قرّب / نوّر / ثبّت)
    HANDOFF_OFFER  -> اعرض عليه يتوصّل بمتطوع بشري (بعد عدة محاولات فاشلة)

مبادئ:
  * مفيش تخمين: أي معلومة طبية أو مالية لازم تعدّي كل الشروط، غير كده نرفض.
  * القرار مبني على أكتر من فريم (Multi-frame voting)، مش لقطة واحدة.
  * التطبيق بيقرا اللي مكتوب على العلبة بس. مفيش نصايح طبية أو جرعات.
  * كل الأرقام في GateConfig قيم ابتدائية: لازم تتظبط على Test Set حقيقي.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional, Sequence

from medicine_matcher import MatchResult


class Action(str, Enum):
    ACCEPT = "ACCEPT"
    RETRY = "RETRY"
    HANDOFF_OFFER = "HANDOFF_OFFER"


@dataclass
class GateConfig:
    # --- أدوية ---
    med_min_frames: int = 2            # أقل عدد فريمات متفقة
    med_agree_ratio: float = 0.6       # نسبة الفريمات المتفقة من الإجمالي
    med_name_min_score: float = 90.0   # أقل تشابه للاسم (0..100)
    med_name_min_margin: float = 10.0  # أقل فرق بين أول وتاني اسم
    # --- فلوس (أشد، لأن الغلط هنا بيتحوّل لخسارة فلوس) ---
    cur_min_frames: int = 3
    cur_agree_ratio: float = 0.6
    cur_min_mean_prob: float = 0.85
    cur_min_margin: float = 0.30       # الفرق بين أعلى احتمالين (متوسط)
    not_money_label: str = "not_money"
    # --- بعد كام محاولة فاشلة نعرض متطوع ---
    handoff_after_attempts: int = 3


@dataclass
class Decision:
    action: Action
    speech_ar: str
    reasons: list[str] = field(default_factory=list)   # للـ logging والتقرير (مش بتتنطق)
    haptic: str = "none"                               # success | warning | error | none
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Expiry date parsing
# ---------------------------------------------------------------------------
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

_MM_YY = re.compile(r"(?<!\d)(0?[1-9]|1[0-2])\s*[/\-.]\s*(20\d{2}|\d{2})(?!\d)")
_YYYY_MM = re.compile(r"(?<!\d)(20\d{2})\s*[/\-.]\s*(0?[1-9]|1[0-2])(?!\d)")


def parse_expiry(text: str) -> Optional[tuple[int, int]]:
    """
    بيرجّع (year, month) أو None.
    لو فيه كلمة EXP ناخد أول تاريخ بعدها، وإلا ناخد أحدث تاريخ في النص
    (تاريخ الصلاحية دايماً بعد تاريخ الإنتاج MFD).
    """
    t = text.lower()
    found: list[tuple[int, int, int]] = []     # (position, year, month)

    for m in _MM_YY.finditer(t):
        month, year = int(m.group(1)), int(m.group(2))
        year = year + 2000 if year < 100 else year
        found.append((m.start(), year, month))
    for m in _YYYY_MM.finditer(t):
        found.append((m.start(), int(m.group(1)), int(m.group(2))))

    found = [f for f in found if 2015 <= f[1] <= 2045]      # استبعاد القراءات المستحيلة
    if not found:
        return None

    exp_positions = [m.start() for m in re.finditer(r"exp", t)]
    if exp_positions:
        after = sorted(f for f in found if f[0] > exp_positions[-1])
        if after:
            return after[0][1], after[0][2]
    latest = max(found, key=lambda f: (f[1], f[2]))
    return latest[1], latest[2]


def expiry_status(expiry: tuple[int, int], today: date) -> str:
    """valid | this_month | expired  (الدواء صالح لحد آخر الشهر المكتوب)."""
    cur = (today.year, today.month)
    if expiry < cur:
        return "expired"
    if expiry == cur:
        return "this_month"
    return "valid"


def expiry_speech(expiry: tuple[int, int]) -> str:
    return f"{MONTHS_AR[expiry[1] - 1]} {expiry[0]}"


# ---------------------------------------------------------------------------
# Medicine gate
# ---------------------------------------------------------------------------
@dataclass
class MedicineFrame:
    match: MatchResult
    ocr_text: str = ""


def _majority(values: Sequence, total: int, min_count: int, ratio: float):
    """بيرجّع (القيمة, عدد الأصوات) لو عدّت شرطي العدد والنسبة، وإلا (None, count)."""
    if not values:
        return None, 0
    value, count = Counter(values).most_common(1)[0]
    if count >= min_count and count >= ratio * total:
        return value, count
    return None, count


def decide_medicine(
    frames: Sequence[MedicineFrame],
    attempt: int = 1,
    today: Optional[date] = None,
    cfg: GateConfig = GateConfig(),
) -> Decision:
    today = today or date.today()
    total = len(frames)
    reasons: list[str] = []

    # 1) الاسم: الفريمات اللي عدّت حدّي الدرجة والـ margin، وبعدين تصويت
    strong = [
        f.match.best
        for f in frames
        if f.match.best
        and f.match.score >= cfg.med_name_min_score
        and f.match.margin >= cfg.med_name_min_margin
    ]
    name, name_votes = _majority(strong, total, cfg.med_min_frames, cfg.med_agree_ratio)
    reasons.append(f"name_votes={name_votes}/{total} strong={len(strong)}")

    # 2) تاريخ الصلاحية: تصويت برضه
    expiries = [e for e in (parse_expiry(f.ocr_text) for f in frames) if e]
    expiry, exp_votes = _majority(expiries, total, cfg.med_min_frames, cfg.med_agree_ratio)
    reasons.append(f"expiry_votes={exp_votes}/{total}")

    give_up = attempt >= cfg.handoff_after_attempts

    # الحالة الناجحة
    if name and expiry:
        status = expiry_status(expiry, today)
        when = expiry_speech(expiry)
        data = {"name": name, "expiry": expiry, "status": status}
        if status == "expired":
            return Decision(Action.ACCEPT,
                            f"ده {name}. الصلاحية خلصت، مكتوب عليه {when}.",
                            reasons, "error", data)
        if status == "this_month":
            return Decision(Action.ACCEPT,
                            f"ده {name}. الصلاحية مكتوبة {when}، يعني بتنتهي الشهر ده.",
                            reasons, "warning", data)
        return Decision(Action.ACCEPT,
                        f"ده {name}. الصلاحية مكتوبة {when}.",
                        reasons, "success", data)

    # الاسم متأكد منه والتاريخ لأ
    if name and not expiry:
        if give_up:
            return _handoff(reasons, {"name": name})
        return Decision(
            Action.RETRY,
            f"شكله {name}، بس مش قادر أقرا تاريخ الصلاحية بوضوح. "
            "قرّب العلبة شوية ونوّر المكان وصوّر تاني.",
            reasons, "warning", {"name": name},
        )

    # مش متأكد من الاسم
    if give_up:
        return _handoff(reasons)
    return Decision(
        Action.RETRY,
        "مش متأكد من الدواء ده. قرّب العلبة، نوّر المكان، وصوّر تاني.",
        reasons, "warning",
    )


# ---------------------------------------------------------------------------
# Currency gate
# ---------------------------------------------------------------------------
CURRENCY_SPEECH = {
    "5": "خمسة جنيه", "10": "عشرة جنيه", "20": "عشرين جنيه",
    "50": "خمسين جنيه", "100": "مية جنيه", "200": "ميتين جنيه",
}


def decide_currency(
    frames: Sequence[dict[str, float]],
    attempt: int = 1,
    cfg: GateConfig = GateConfig(),
) -> Decision:
    """
    frames: لكل فريم قاموس {label: probability} من نموذج الـ TFLite.
    بنحسب التصويت + متوسط الاحتمالات + الفرق بين أول وتاني.
    """
    give_up = attempt >= cfg.handoff_after_attempts
    reasons: list[str] = []

    if len(frames) < cfg.cur_min_frames:
        reasons.append(f"frames={len(frames)}<{cfg.cur_min_frames}")
        return Decision(Action.RETRY, "ثبّت الكاميرا شوية وخلّيني أشوف تاني.",
                        reasons, "warning")

    votes = Counter(max(f, key=f.get) for f in frames)
    top_label, top_count = votes.most_common(1)[0]
    labels = frames[0].keys()
    mean = {l: sum(f[l] for f in frames) / len(frames) for l in labels}
    ranked = sorted(mean.values(), reverse=True)
    margin = ranked[0] - ranked[1] if len(ranked) > 1 else ranked[0]
    reasons.append(f"top={top_label} votes={top_count}/{len(frames)} "
                   f"mean={mean[top_label]:.2f} margin={margin:.2f}")

    agreed = top_count >= cfg.cur_agree_ratio * len(frames)

    if agreed and top_label == cfg.not_money_label and mean[top_label] >= 0.6:
        return Decision(Action.RETRY,
                        "مش شايف ورقة فلوس. وجّه الكاميرا ناحية الورقة وصوّر تاني.",
                        reasons, "warning")

    if (agreed
            and top_label in CURRENCY_SPEECH
            and mean[top_label] >= cfg.cur_min_mean_prob
            and margin >= cfg.cur_min_margin):
        return Decision(Action.ACCEPT, f"دي {CURRENCY_SPEECH[top_label]}.",
                        reasons, "success", {"denomination": top_label})

    if give_up:
        return _handoff(reasons)
    return Decision(
        Action.RETRY,
        "مش متأكد من الورقة دي. افردها كويس وخلّيها قدام الكاميرا ونوّر المكان وصوّر تاني.",
        reasons, "warning",
    )


# ---------------------------------------------------------------------------
def _handoff(reasons: list[str], data: Optional[dict] = None) -> Decision:
    return Decision(
        Action.HANDOFF_OFFER,
        "مش قادر أتأكد من القراءة. تحب أوصّلك بمتطوع يشوف معاك؟ قول أيوه أو لأ.",
        reasons, "warning", data or {},
    )
