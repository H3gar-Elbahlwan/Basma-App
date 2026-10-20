import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from confidence_gate import (  # noqa: E402
    Action, MedicineFrame, decide_currency, decide_medicine, parse_expiry,
)
from medicine_matcher import MatchResult  # noqa: E402

TODAY = date(2026, 10, 20)


def frame(best="Concor", score=100.0, second=60.0, text="EXP 03/2027"):
    return MedicineFrame(MatchResult(best=best, score=score, second_score=second), text)


def probs(top, p=0.95, labels=("5", "10", "20", "50", "100", "200", "not_money")):
    rest = (1 - p) / (len(labels) - 1)
    return {l: (p if l == top else rest) for l in labels}


class TestExpiryParsing(unittest.TestCase):
    def test_exp_keyword_wins_over_mfd(self):
        self.assertEqual(parse_expiry("MFD 03/2024 EXP 03/2027"), (2027, 3))

    def test_short_year(self):
        self.assertEqual(parse_expiry("EXP: 11-26"), (2026, 11))

    def test_year_first(self):
        self.assertEqual(parse_expiry("2027/05"), (2027, 5))

    def test_latest_when_no_keyword(self):
        self.assertEqual(parse_expiry("03/2024 06/2027"), (2027, 6))

    def test_no_date(self):
        self.assertIsNone(parse_expiry("Concor 5mg"))

    def test_impossible_year_rejected(self):
        self.assertIsNone(parse_expiry("12/03"))


class TestMedicineGate(unittest.TestCase):
    def test_accept_valid(self):
        d = decide_medicine([frame(), frame(), frame()], today=TODAY)
        self.assertEqual(d.action, Action.ACCEPT)
        self.assertIn("Concor", d.speech_ar)
        self.assertEqual(d.haptic, "success")

    def test_accept_expired_flags_error(self):
        frames = [frame(text="EXP 03/2025")] * 3
        d = decide_medicine(frames, today=TODAY)
        self.assertEqual(d.action, Action.ACCEPT)
        self.assertEqual(d.data["status"], "expired")
        self.assertEqual(d.haptic, "error")

    def test_expiring_this_month(self):
        frames = [frame(text="EXP 10/2026")] * 3
        d = decide_medicine(frames, today=TODAY)
        self.assertEqual(d.data["status"], "this_month")

    def test_name_ok_but_no_expiry_retries(self):
        frames = [frame(text="Concor 5mg")] * 3
        d = decide_medicine(frames, attempt=1, today=TODAY)
        self.assertEqual(d.action, Action.RETRY)
        self.assertIn("الصلاحية", d.speech_ar)

    def test_low_score_retries_then_handoff(self):
        frames = [frame(score=72, second=65)] * 3
        self.assertEqual(decide_medicine(frames, 1, TODAY).action, Action.RETRY)
        self.assertEqual(decide_medicine(frames, 3, TODAY).action, Action.HANDOFF_OFFER)

    def test_small_margin_is_not_accepted(self):
        frames = [frame(score=95, second=92)] * 3          # دوائين شبه بعض
        self.assertNotEqual(decide_medicine(frames, 1, TODAY).action, Action.ACCEPT)

    def test_disagreeing_frames_not_accepted(self):
        frames = [frame("Concor"), frame("Brufen"), frame("Lasix")]
        self.assertNotEqual(decide_medicine(frames, 1, TODAY).action, Action.ACCEPT)

    def test_single_frame_not_enough(self):
        self.assertNotEqual(decide_medicine([frame()], 1, TODAY).action, Action.ACCEPT)

    def test_no_frames(self):
        self.assertEqual(decide_medicine([], 1, TODAY).action, Action.RETRY)


class TestCurrencyGate(unittest.TestCase):
    def test_accept(self):
        d = decide_currency([probs("50")] * 4)
        self.assertEqual(d.action, Action.ACCEPT)
        self.assertEqual(d.data["denomination"], "50")
        self.assertIn("خمسين", d.speech_ar)

    def test_too_few_frames(self):
        self.assertEqual(decide_currency([probs("50")] * 2).action, Action.RETRY)

    def test_low_confidence_retries(self):
        d = decide_currency([probs("50", p=0.6)] * 4)
        self.assertEqual(d.action, Action.RETRY)

    def test_close_call_between_two_classes(self):
        two_way = {"5": 0.02, "10": 0.02, "20": 0.02, "50": 0.50, "100": 0.42,
                   "200": 0.01, "not_money": 0.01}
        self.assertNotEqual(decide_currency([two_way] * 4).action, Action.ACCEPT)

    def test_disagreeing_frames(self):
        frames = [probs("50"), probs("100"), probs("20"), probs("200")]
        self.assertNotEqual(decide_currency(frames).action, Action.ACCEPT)

    def test_not_money(self):
        d = decide_currency([probs("not_money")] * 4)
        self.assertEqual(d.action, Action.RETRY)
        self.assertIn("مش شايف", d.speech_ar)

    def test_handoff_after_attempts(self):
        d = decide_currency([probs("50", p=0.5)] * 4, attempt=3)
        self.assertEqual(d.action, Action.HANDOFF_OFFER)


if __name__ == "__main__":
    unittest.main()
