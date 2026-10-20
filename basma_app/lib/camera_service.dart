import 'package:camera/camera.dart';

/// بيمتلك الـ CameraController وبيلتقط "رشقة" (Burst) لقطات متتالية.
///
/// ليه لقطات ثابتة مش Video Stream؟ لأنها أبسط وأثبت مع ML Kit (بيقرا من ملف)
/// وكافية لتصويت الـ Gate على 3 لقطات. لو احتجتوا أسرع بعدين، الحل هو
/// startImageStream مع تحويل YUV -> InputImage.
class CameraService {
  CameraController? controller;

  bool get isReady => controller?.value.isInitialized ?? false;

  Future<void> init() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) {
      throw CameraException('NoCamera', 'No camera found on this device');
    }
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    final c = CameraController(
      back,
      ResolutionPreset.medium, // أخف في الـ OCR والـ TFLite (الصور الكبيرة بتبطّأ)
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );
    await c.initialize();
    await c.setFlashMode(FlashMode.off);
    try {
      await c.setFocusMode(FocusMode.auto);
    } catch (_) {
      // بعض الأجهزة مابتدعمش تحديد وضع الفوكس
    }
    controller = c;
  }

  /// بيرجّع مسارات الصور. المتصل مسؤول عن حذفها بعد الاستخدام (خصوصية).
  Future<List<String>> captureBurst(
    int count,
    Duration gap, {
    void Function(int index)? onFrame,
  }) async {
    final c = controller;
    if (c == null || !c.value.isInitialized) {
      throw CameraException('NotReady', 'Camera is not initialized');
    }
    final paths = <String>[];
    for (var i = 0; i < count; i++) {
      final file = await c.takePicture();
      paths.add(file.path);
      onFrame?.call(i);
      if (i < count - 1) await Future.delayed(gap);
    }
    return paths;
  }

  Future<void> pause() async {
    final c = controller;
    controller = null;
    await c?.dispose();
  }

  Future<void> dispose() => pause();
}
