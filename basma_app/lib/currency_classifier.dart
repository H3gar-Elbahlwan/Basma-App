import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

import '../config.dart';

/// بيرجّع احتمالات كل فئة {"5": 0.01, "50": 0.97, "not_money": 0.0, ...}
abstract class CurrencyClassifier {
  Future<void> load();
  Future<Map<String, double>> classify(String imagePath);
  void dispose();
}

/// ⚠️ تجريبي: دايماً بيقول "50 جنيه" بثقة عالية. للاختبار بس لحد ما نموذج B يجهز.
class MockCurrencyClassifier implements CurrencyClassifier {
  static const _labels = ['10', '100', '20', '200', '5', '50', 'not_money'];

  @override
  Future<void> load() async {}

  @override
  Future<Map<String, double>> classify(String imagePath) async => {
        for (final l in _labels) l: l == '50' ? 0.94 : 0.01,
      };

  @override
  void dispose() {}
}

/// النموذج الحقيقي (TFLite) اللي عضو B بيطلّعه.
/// المدخل: [1, 224, 224, 3] float32 بقيم 0..255 (الـ Rescaling جوّه النموذج).
/// ترتيب الفئات بيتقرا من labels.txt (لازم يطابق ترتيب التدريب).
class TfliteCurrencyClassifier implements CurrencyClassifier {
  static const int _size = 224;
  late Interpreter _interpreter;
  late List<String> _labels;

  @override
  Future<void> load() async {
    _interpreter = await Interpreter.fromAsset(AppConfig.currencyModelAsset);
    final raw = await rootBundle.loadString(AppConfig.currencyLabelsAsset);
    _labels =
        raw.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
  }

  @override
  Future<Map<String, double>> classify(String imagePath) async {
    final bytes = await File(imagePath).readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) throw const FormatException('Cannot decode image');
    final resized = img.copyResize(decoded, width: _size, height: _size);

    final input = [
      List.generate(
        _size,
        (y) => List.generate(_size, (x) {
          final p = resized.getPixel(x, y);
          return [p.r.toDouble(), p.g.toDouble(), p.b.toDouble()];
        }),
      ),
    ];
    final output = [List<double>.filled(_labels.length, 0.0)];
    _interpreter.run(input, output);

    return {for (var i = 0; i < _labels.length; i++) _labels[i]: output[0][i]};
  }

  @override
  void dispose() => _interpreter.close();
}
