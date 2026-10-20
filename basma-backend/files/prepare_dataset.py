"""
بصمة - العضو B: تجهيز داتا الجنيه المصري

الشكل المتوقع للداتا الخام (raw_data):

    raw_data/
        5/          10/        20/
        50/         100/       200/
        not_money/            <- مهم جداً: صور خلفيات وأيادي وأوراق عادية

أسماء الملفات (يُفضّل): {الفئة}_{رقم الجلسة}_{رقم الصورة}.jpg
    مثال:  50_s03_0012.jpg   (فئة 50، جلسة تصوير رقم s03، الصورة 12)

ليه رقم الجلسة مهم؟
    الصور المتتالية من نفس الورقة بتبقى شبه بعض جداً. لو وزّعناها عشوائياً على
    train و test، النموذج هيبان دقيق جداً وهو في الحقيقة حافظ الصور (Data Leakage).
    عشان كده السكربت بيقسّم حسب الجلسة: الجلسة كلها تروح لمجموعة واحدة بس.

الاستخدام:
    python prepare_dataset.py --raw raw_data --out dataset
"""
import argparse
import random
import shutil
from collections import defaultdict
from pathlib import Path

CLASSES = ["5", "10", "20", "50", "100", "200", "not_money"]
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
SPLITS = {"train": 0.70, "val": 0.15, "test": 0.15}


def session_of(path: Path) -> str:
    """الجلسة = الجزء التاني في اسم الملف. لو مش موجود، كل صورة جلسة لوحدها."""
    parts = path.stem.split("_")
    return parts[1] if len(parts) >= 3 else path.stem


def is_valid_image(path: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def split_groups(groups: dict, rng: random.Random) -> dict:
    """بيوزّع الجلسات على train/val/test بحيث نسب عدد الصور تقرّب من 70/15/15."""
    keys = list(groups)
    rng.shuffle(keys)
    total = sum(len(groups[k]) for k in keys)
    counts = {s: 0 for s in SPLITS}
    assigned = {s: [] for s in SPLITS}
    running = 0
    for k in keys:
        size = len(groups[k])
        running += size
        # نختار المجموعة اللي أبعد عن هدفها
        best = max(SPLITS, key=lambda s: SPLITS[s] * running - counts[s])
        counts[best] += size
        assigned[best].extend(groups[k])
    assert sum(counts.values()) == total
    return assigned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="raw_data")
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-per-class", type=int, default=150,
                    help="تحذير لو عدد صور الفئة أقل من كده")
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    rng = random.Random(args.seed)
    if out.exists():
        shutil.rmtree(out)

    summary = {}
    for cls in CLASSES:
        folder = raw / cls
        if not folder.is_dir():
            print(f"[!] الفولدر ده مش موجود: {folder}")
            continue

        groups, bad = defaultdict(list), 0
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in IMG_EXT:
                continue
            if not is_valid_image(p):
                bad += 1
                continue
            groups[session_of(p)].append(p)

        n_images = sum(len(v) for v in groups.values())
        if n_images < args.min_per_class:
            print(f"[!] الفئة {cls}: {n_images} صورة بس (المطلوب {args.min_per_class}+)")
        if len(groups) < 6:
            print(f"[!] الفئة {cls}: {len(groups)} جلسة بس. صوّروا في جلسات أكتر "
                  f"(أماكن/إضاءات/أوراق مختلفة).")

        assigned = split_groups(groups, rng)
        for split, files in assigned.items():
            dest = out / split / cls
            dest.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.copy2(f, dest / f.name)
        summary[cls] = {s: len(f) for s, f in assigned.items()} | {"corrupt": bad}

    print(f"\n{'class':<10}{'train':>8}{'val':>8}{'test':>8}{'corrupt':>9}")
    for cls, c in summary.items():
        print(f"{cls:<10}{c['train']:>8}{c['val']:>8}{c['test']:>8}{c['corrupt']:>9}")


if __name__ == "__main__":
    main()
