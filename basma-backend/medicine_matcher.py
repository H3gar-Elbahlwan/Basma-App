"""
بصمة - العضو C: مطابقة أسماء الأدوية القادمة من الـ OCR مع قاعدة الأدوية.

الفكرة:
  1) Normalization: نظّف نص الـ OCR ونصلّح الأخطاء المشهورة (0->o, 1->l, ...).
  2) Fuzzy Match: قارن كل جزء من النص بكل اسم في القاعدة بمقياس تشابه 0..100.
  3) رجّع أفضل نتيجة + تاني أفضل نتيجة + الفرق بينهم (margin).
     الـ Confidence Gate (في confidence_gate.py) هو اللي يقرر نقبل النتيجة ولا لأ.

المكتبة: بنستخدم RapidFuzz لو متسطّبة (pip install rapidfuzz)، ولو مش موجودة
بنرجع لـ difflib عشان الكود يشتغل في أي بيئة. الأرقام (thresholds) لازم تتظبط
على الـ backend اللي هتستخدموه فعلاً.
"""
from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    from rapidfuzz import fuzz

    def similarity(a: str, b: str) -> float:
        return float(fuzz.ratio(a, b))

    BACKEND = "rapidfuzz"
except ImportError:  # pragma: no cover
    def similarity(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0

    BACKEND = "difflib"


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
# رموز بتتقري غلط بدل حروف
SYMBOL_TO_LETTER = str.maketrans({"|": "l", "!": "i", "$": "s", "@": "a"})
# أرقام بتتقري بدل حروف (جوّه الكلمة بس)
DIGIT_TO_LETTER = str.maketrans(
    {"0": "o", "1": "l", "5": "s", "8": "b", "6": "g", "4": "a", "3": "e", "2": "z"}
)

_UNIT = r"(?:mg|mcg|ug|ml|g|iu|%)?"
_PURE_STRENGTH = re.compile(rf"^\d+(?:\.\d+)?{_UNIT}$")            # 5   5mg   500mg
_TRAILING_STRENGTH = re.compile(rf"^([a-z0-9]{{3,}}?)(\d+(?:\.\d+)?{_UNIT})$")  # concor5mg
# كلمات شائعة على العلب مالهاش علاقة باسم الدواء
_NOISE = {
    "mg", "mcg", "ug", "ml", "g", "iu", "tab", "tabs", "tablet", "tablets",
    "cap", "caps", "capsule", "capsules", "film", "coated", "exp", "mfd",
    "batch", "lot", "no", "bn",
}


def tokenize(raw: str) -> tuple[list[str], list[str]]:
    """
    بيرجّع (tokens, strengths).
      tokens   : كلمات الاسم بعد التطبيع
      strengths: التركيزات اللي لقيناها (5mg, 500mg ...) كمعلومة مساعدة فقط
    أمثلة:  "C0nc0r 5mg" -> (["concor"], ["5mg"])
    """
    text = raw.lower().translate(SYMBOL_TO_LETTER)
    text = re.sub(r"[^a-z0-9.%\s]", " ", text)

    tokens: list[str] = []
    strengths: list[str] = []
    for tok in text.split():
        tok = tok.strip(".")
        if not tok or tok in _NOISE:
            continue
        if _PURE_STRENGTH.match(tok):          # أرقام صافية = تركيز، مش اسم
            strengths.append(tok)
            continue
        m = _TRAILING_STRENGTH.match(tok)      # c0nc0r5mg -> c0nc0r + 5mg
        if m:
            tok, strength = m.group(1), m.group(2)
            strengths.append(strength)
        if any(ch.isalpha() for ch in tok):
            tok = tok.translate(DIGIT_TO_LETTER)   # c0nc0r -> concor
        if len(tok) >= 2:
            tokens.append(tok)
    return tokens, strengths


def normalize_name(raw: str) -> str:
    tokens, _ = tokenize(raw)
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
@dataclass
class MatchResult:
    best: Optional[str] = None            # الاسم من القاعدة (بشكله الأصلي)
    score: float = 0.0                    # 0..100
    second_score: float = 0.0             # أعلى درجة لاسم تاني مختلف
    candidates: list[tuple[str, float]] = field(default_factory=list)
    normalized_text: str = ""
    strength_hints: list[str] = field(default_factory=list)

    @property
    def margin(self) -> float:
        """الفرق بين الأول والتاني. صغير = غموض (ممكن يكون دوائين شبه بعض)."""
        return self.score - self.second_score


class MedicineMatcher:
    def __init__(self, names: Iterable[str]):
        self._index: list[tuple[str, str]] = []   # (normalized, display)
        seen = set()
        for display in names:
            norm = normalize_name(display)
            if norm and display not in seen:
                seen.add(display)
                self._index.append((norm, display))
        self._max_words = max((n.count(" ") + 1 for n, _ in self._index), default=1)

    @classmethod
    def from_csv(cls, path: str | Path, column: str = "trade_name") -> "MedicineMatcher":
        with open(path, newline="", encoding="utf-8") as f:
            return cls(row[column].strip() for row in csv.DictReader(f) if row.get(column))

    def _queries(self, tokens: list[str]) -> dict[int, set[str]]:
        """كل تتابع كلمات مقسّم حسب عدد الكلمات (1 = كلمة، 2 = كلمتين ...)."""
        queries: dict[int, set[str]] = {}
        for n in range(1, self._max_words + 1):
            for i in range(len(tokens) - n + 1):
                q = " ".join(tokens[i : i + n])
                if len(q) >= 3:
                    queries.setdefault(n, set()).add(q)
        return queries

    def match(self, raw_text: str, top_k: int = 3) -> MatchResult:
        tokens, strengths = tokenize(raw_text)
        norm = " ".join(tokens)
        queries = self._queries(tokens)
        if not queries:
            return MatchResult(normalized_text=norm, strength_hints=strengths)
        all_queries = set().union(*queries.values())

        scored = []   # (display, score, words)
        for name_norm, display in self._index:
            words = name_norm.count(" ") + 1
            # الاسم المركّب بيتقارن بتتابع كلمات بنفس عدد كلماته (لو موجود)
            pool = queries.get(words) or all_queries
            scored.append((display, max(similarity(q, name_norm) for q in pool), words))
        # عند التعادل نفضّل الاسم الأطول ('Panadol Extra' على 'Panadol')
        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
        scored = [(d, sc) for d, sc, _ in scored]

        return MatchResult(
            best=scored[0][0],
            score=scored[0][1],
            second_score=scored[1][1] if len(scored) > 1 else 0.0,
            candidates=scored[:top_k],
            normalized_text=norm,
            strength_hints=strengths,
        )


if __name__ == "__main__":
    here = Path(__file__).parent
    matcher = MedicineMatcher.from_csv(here / "data" / "medicines_sample.csv")
    print(f"backend: {BACKEND}")
    for text in ["C0nc0r 5mg", "Pan4dol", "MFD 03/2025 EXP 03/2027 Augmentln 1g", "xzqkw"]:
        r = matcher.match(text)
        print(f"{text!r:50} -> {r.best} (score={r.score:.0f}, margin={r.margin:.0f})")
