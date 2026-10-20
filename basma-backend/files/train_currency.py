"""
بصمة - العضو B: تدريب نموذج تصنيف فئات الجنيه المصري (MobileNetV2 + Transfer Learning)
ثم تحويله لـ TFLite عشان يشتغل Offline على الموبايل.

الاستخدام:
    python train_currency.py --data dataset --out build

المخرجات (في فولدر build):
    currency_model.keras      النموذج الكامل
    currency_model.tflite     النموذج للموبايل (ده اللي هيروح لعضو A)
    labels.txt                ترتيب الفئات - لازم نفس الترتيب في التطبيق!
    model_meta.json           مقاييس + مواصفات الإدخال
    confusion_matrix.csv      مصفوفة الالتباس على الـ test set

ملاحظات تصميم:
  * الـ Augmentation والـ Rescaling جوّه النموذج نفسه، فالموبايل يبعت صورة
    خام (float32 بقيم 0-255) ومايحتاجش معالجة تانية.
  * مفيش Horizontal Flip: الورقة المقلوبة مرآة عمرها ما هتظهر في الواقع.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

IMG_SIZE = (224, 224)
BATCH = 32
SEED = 42


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_split(root: Path, split: str, shuffle: bool):
    return keras.utils.image_dataset_from_directory(
        root / split,
        image_size=IMG_SIZE,
        batch_size=BATCH,
        label_mode="int",
        shuffle=shuffle,
        seed=SEED,
    )


def class_weights_from_dir(root: Path, class_names):
    """أوزان عكسية للفئات اللي صورها أقل."""
    counts = np.array(
        [len(list((root / c).glob("*"))) for c in class_names], dtype=np.float64
    )
    weights = counts.sum() / (len(counts) * counts)
    return {i: float(w) for i, w in enumerate(weights)}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def build_model(num_classes: int):
    augmentation = keras.Sequential(
        [
            layers.RandomRotation(0.08),                  # ميل بسيط (~±29°)
            layers.RandomZoom((-0.25, 0.15)),             # قريب/بعيد
            layers.RandomTranslation(0.10, 0.10),         # ورقة مش في النص
            layers.RandomBrightness(0.30),                # إضاءة ضعيفة/قوية
            layers.RandomContrast(0.30),
        ],
        name="augmentation",
    )

    base = keras.applications.MobileNetV2(
        input_shape=IMG_SIZE + (3,), include_top=False, weights="imagenet"
    )
    base.trainable = False

    inputs = keras.Input(shape=IMG_SIZE + (3,), name="image")   # float32, 0..255
    x = augmentation(inputs)                                    # شغّال وقت التدريب بس
    x = layers.Rescaling(1.0 / 127.5, offset=-1.0)(x)           # نفس preprocess بتاع MobileNetV2
    x = base(x, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax", name="probs")(x)
    return keras.Model(inputs, outputs, name="basma_currency"), base


def compile_model(model, lr):
    model.compile(
        optimizer=keras.optimizers.Adam(lr),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------
def evaluate_keras(model, ds, class_names, out_dir: Path):
    y_true, y_pred = [], []
    for images, labels in ds:
        probs = model.predict(images, verbose=0)
        y_true.extend(labels.numpy().tolist())
        y_pred.extend(np.argmax(probs, axis=1).tolist())
    y_true, y_pred = np.array(y_true), np.array(y_pred)

    cm = tf.math.confusion_matrix(y_true, y_pred, num_classes=len(class_names)).numpy()
    np.savetxt(
        out_dir / "confusion_matrix.csv", cm, fmt="%d", delimiter=",",
        header=",".join(class_names), comments="",
    )

    acc = float((y_true == y_pred).mean())
    print(f"\nTest accuracy (Keras): {acc:.4f}")
    print(f"{'class':<12}{'recall':>8}{'support':>9}")
    for i, name in enumerate(class_names):
        support = cm[i].sum()
        recall = cm[i, i] / support if support else float("nan")
        print(f"{name:<12}{recall:>8.3f}{support:>9}")
    return acc, cm


def evaluate_tflite(tflite_path: Path, ds):
    interpreter = tf.lite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()
    inp = interpreter.get_input_details()[0]
    out = interpreter.get_output_details()[0]

    correct = total = 0
    for images, labels in ds.unbatch().batch(1):
        interpreter.set_tensor(inp["index"], images.numpy().astype(np.float32))
        interpreter.invoke()
        pred = int(np.argmax(interpreter.get_tensor(out["index"])[0]))
        correct += int(pred == int(labels.numpy()[0]))
        total += 1
    acc = correct / total
    print(f"Test accuracy (TFLite): {acc:.4f}")
    return acc


def export_tflite(model, path: Path):
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    # Dynamic-range quantization: الأوزان int8 -> الحجم أصغر ~4x، والإدخال/الإخراج يفضلوا float32
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    path.write_bytes(converter.convert())
    print(f"TFLite saved: {path} ({path.stat().st_size / 1e6:.2f} MB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="dataset")
    ap.add_argument("--out", default="build")
    ap.add_argument("--epochs-head", type=int, default=10)
    ap.add_argument("--epochs-finetune", type=int, default=10)
    ap.add_argument("--unfreeze-last", type=int, default=30,
                    help="عدد آخر طبقات MobileNetV2 اللي هنفكها في الـ fine-tuning")
    args = ap.parse_args()

    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tf.keras.utils.set_random_seed(SEED)

    train_ds = load_split(data, "train", shuffle=True)
    val_ds = load_split(data, "val", shuffle=False)
    test_ds = load_split(data, "test", shuffle=False)
    class_names = train_ds.class_names          # ترتيب أبجدي: 10,100,20,200,5,50,not_money
    print("Classes:", class_names)
    (out / "labels.txt").write_text("\n".join(class_names), encoding="utf-8")

    cw = class_weights_from_dir(data / "train", class_names)
    AUTOTUNE = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(AUTOTUNE)
    val_ds = val_ds.prefetch(AUTOTUNE)

    model, base = build_model(len(class_names))
    callbacks = [
        keras.callbacks.EarlyStopping(patience=4, restore_best_weights=True,
                                      monitor="val_accuracy"),
        keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=2),
    ]

    # --- المرحلة 1: ندرّب الـ head بس (القاعدة مجمّدة) ---
    compile_model(model, 1e-3)
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs_head,
              class_weight=cw, callbacks=callbacks)

    # --- المرحلة 2: Fine-tuning لآخر طبقات القاعدة بمعدل تعلّم صغير ---
    base.trainable = True
    for layer in base.layers[: -args.unfreeze_last]:
        layer.trainable = False
    for layer in base.layers:                      # BatchNorm يفضل مجمّد
        if isinstance(layer, layers.BatchNormalization):
            layer.trainable = False
    compile_model(model, 1e-5)
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs_finetune,
              class_weight=cw, callbacks=callbacks)

    # --- التقييم على test (الصور اللي النموذج ماشافهاش) ---
    acc_keras, _ = evaluate_keras(model, test_ds, class_names, out)

    model.save(out / "currency_model.keras")
    tflite_path = out / "currency_model.tflite"
    export_tflite(model, tflite_path)
    acc_tflite = evaluate_tflite(tflite_path, test_ds)

    meta = {
        "input_size": list(IMG_SIZE),
        "input_dtype": "float32",
        "input_range": "0..255 (raw pixels, no preprocessing needed)",
        "classes": class_names,
        "test_accuracy_keras": acc_keras,
        "test_accuracy_tflite": acc_tflite,
    }
    (out / "model_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nDone. ابعتوا currency_model.tflite + labels.txt لعضو A.")


if __name__ == "__main__":
    main()
