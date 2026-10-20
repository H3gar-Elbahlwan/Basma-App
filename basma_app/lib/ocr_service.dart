import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

/// OCR على الجهاز (Offline) للحروف اللاتينية: أسماء الأدوية والتواريخ.
class OcrService {
  final TextRecognizer _recognizer =
      TextRecognizer(script: TextRecognitionScript.latin);

  Future<String> readText(String imagePath) async {
    final result =
        await _recognizer.processImage(InputImage.fromFilePath(imagePath));
    return result.text;
  }

  Future<void> dispose() => _recognizer.close();
}
