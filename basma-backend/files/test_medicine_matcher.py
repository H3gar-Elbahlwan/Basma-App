import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from medicine_matcher import MedicineMatcher, normalize_name, tokenize  # noqa: E402


class TestNormalization(unittest.TestCase):
    def test_digits_to_letters(self):
        self.assertEqual(normalize_name("C0nc0r"), "concor")

    def test_strength_is_separated(self):
        tokens, strengths = tokenize("Concor 5 mg")
        self.assertEqual(tokens, ["concor"])
        self.assertEqual(strengths, ["5"])

    def test_glued_strength(self):
        tokens, strengths = tokenize("C0nc0r5mg")
        self.assertEqual(tokens, ["concor"])
        self.assertEqual(strengths, ["5mg"])

    def test_symbols_and_noise(self):
        self.assertEqual(normalize_name("|ASIX TAB."), "lasix")


class TestMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = MedicineMatcher.from_csv(ROOT / "data" / "medicines_sample.csv")

    def assert_matches(self, text, expected, min_score=85):
        r = self.m.match(text)
        self.assertEqual(r.best, expected, f"{text!r} -> {r.best} ({r.score:.0f})")
        self.assertGreaterEqual(r.score, min_score)

    # الـ 5 حالات المطلوبة + إضافات
    def test_1_exact(self):
        self.assert_matches("Concor", "Concor", 100)

    def test_2_zeros_for_o(self):
        self.assert_matches("C0nc0r", "Concor", 100)

    def test_3_digit_for_letter_with_strength(self):
        self.assert_matches("Pan4dol 500mg", "Panadol", 100)

    def test_4_one_for_l(self):
        self.assert_matches("Cataf1am", "Cataflam", 100)

    def test_5_misread_letter(self):
        self.assert_matches("Augmentln", "Augmentin")

    def test_6_noisy_full_box_text(self):
        self.assert_matches("MFD 03/2025 EXP 03/2027 C0nc0r 5 mg Merck", "Concor", 100)

    def test_7_multiword_name(self):
        self.assert_matches("PANAD0L EXTRA", "Panadol Extra", 100)

    def test_8_garbage_has_low_score(self):
        r = self.m.match("xzqkw")
        self.assertLess(r.score, 70)

    def test_9_empty_text(self):
        r = self.m.match("")
        self.assertIsNone(r.best)
        self.assertEqual(r.score, 0)

    def test_10_similar_names_have_small_margin(self):
        # "Panadol" لوحده قريب من "Panadol Extra" لكن لازم يفضّل الأقصر
        r = self.m.match("Panadol")
        self.assertEqual(r.best, "Panadol")
        self.assertGreater(r.margin, 10)


if __name__ == "__main__":
    unittest.main()
