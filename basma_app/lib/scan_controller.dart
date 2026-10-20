import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';

import '../config.dart';
import '../models/gate_decision.dart';
import '../services/backend_client.dart';
import '../services/camera_service.dart';
import '../services/currency_classifier.dart';
import '../services/haptics_service.dart';
import '../services/ocr_service.dart';
import '../services/voice_service.dart';
import 'currency_gate.dart';

enum ScanMode { medicine, currency }

enum ScanState { idle, capturing, analyzing, awaitingHandoff }

/// قلب التطبيق: لقطات -> تحليل -> قرار الـ Gate -> كلام + اهتزاز.
///
/// الدواء  : OCR على الجهاز ثم الباك إند يطابق ويقرر.
/// الفلوس : نموذج TFLite على الجهاز ثم currency_gate.dart (Offline بالكامل).
class ScanController extends ChangeNotifier {
  ScanController({
    required this.camera,
    required this.voice,
    required this.haptics,
    required this.backend,
    required this.ocr,
    required this.currency,
  });

  final CameraService camera;
  final VoiceService voice;
  final HapticsService haptics;
  final BackendClient backend;
  final OcrService ocr;
  final CurrencyClassifier currency;

  ScanState _state = ScanState.idle;
  ScanState get state => _state;
  bool get busy =>
      _state == ScanState.capturing || _state == ScanState.analyzing;

  int _attempt = 1; // رقم المحاولة الحالية (الـ Gate بيعرض متطوع عند 3)
  ScanMode? _lastMode;
  String _lastSpeech = '';

  void _setState(ScanState s) {
    _state = s;
    notifyListeners();
  }

  /// الدالة الرئيسية. بتتنادى من زرار "اقرا الدواء" أو "اعرف الفلوس".
  Future<void> scan(ScanMode mode) async {
    if (_state != ScanState.idle) return;
    if (_lastMode != mode) {
      _attempt = 1; // غيّر النوع = ابدأ عدّ المحاولات من الأول
      _lastMode = mode;
    }

    _setState(ScanState.capturing);
    var paths = <String>[];
    try {
      await haptics.tick();
      unawaited(voice.speak('ثبّت إيدك.')); // من غير انتظار عشان ماتأخرش التصوير
      paths = await camera.captureBurst(
        AppConfig.burstFrames,
        AppConfig.burstGap,
        onFrame: (_) => haptics.tick(), // نبضة مع كل لقطة
      );

      _setState(ScanState.analyzing);
      final decision = mode == ScanMode.medicine
          ? await _decideMedicine(paths)
          : await _decideCurrency(paths);
      await _handle(decision);
    } on CameraException catch (e) {
      await _fail(e.code == 'CameraAccessDenied'
          ? 'محتاج إذن الكاميرا عشان أشتغل. فعّله من إعدادات الموبايل.'
          : 'معرفتش أصوّر. جرّب تاني.');
    } on BackendException catch (e) {
      debugPrint('Backend error: $e');
      await _fail('مش قادر أوصل للسيرفر. اتأكد من الاتصال وجرّب تاني.');
    } catch (e, st) {
      debugPrint('Scan error: $e\n$st');
      await _fail('حصلت مشكلة غير متوقعة. جرّب تاني.');
    } finally {
      await _deleteFiles(paths); // خصوصية: مانسيبش صور المستخدم على الجهاز
      if (_state != ScanState.awaitingHandoff) _setState(ScanState.idle);
    }
  }

  Future<GateDecision> _decideMedicine(List<String> paths) async {
    final texts = <String>[];
    for (final p in paths) {
      texts.add(await ocr.readText(p));
    }
    return backend.decideMedicine(ocrTexts: texts, attempt: _attempt);
  }

  Future<GateDecision> _decideCurrency(List<String> paths) async {
    final frames = <Map<String, double>>[];
    for (final p in paths) {
      frames.add(await currency.classify(p));
    }
    return decideCurrency(frames, attempt: _attempt);
  }

  /// معالجة قرار الـ Gate: اهتزاز + كلام بالتوازي.
  Future<void> _handle(GateDecision d) async {
    debugPrint('Gate: ${d.action} | ${d.reasons}');
    _lastSpeech = d.speechAr;

    switch (d.action) {
      case GateAction.accept:
        _attempt = 1;
        break;
      case GateAction.retry:
        _attempt++;
        break;
      case GateAction.handoffOffer:
        _setState(ScanState.awaitingHandoff); // الواجهة تعرض أيوه / لأ
        break;
    }

    unawaited(haptics.forDecision(d));
    await voice.speak(d.speechAr);
  }

  Future<void> _fail(String message) async {
    await haptics.retry();
    _lastSpeech = message;
    await voice.speak(message);
  }

  /// رد المستخدم على عرض المتطوع.
  Future<void> answerHandoff({required bool accepted}) async {
    if (_state != ScanState.awaitingHandoff) return;
    await haptics.tick();
    _attempt = 1;
    _setState(ScanState.idle);
    if (accepted) {
      await requestHumanHelp();
    } else {
      await voice.speak('تمام. لو عايز تجرّب تاني دوس على الزرار.');
    }
  }

  /// TODO (الأسبوع 5): اربطوها بالـ Live Assist (WebRTC) أو بالاتصال بشخص موثوق.
  /// دلوقتي بتقول الحقيقة للمستخدم بدل ما تتظاهر إن الخدمة شغالة.
  Future<void> requestHumanHelp() async {
    _lastSpeech =
        'خدمة المتطوعين لسه مش متاحة في النسخة دي. اطلب مساعدة من حد قريب منك.';
    await haptics.retry();
    await voice.speak(_lastSpeech);
  }

  Future<void> repeatLast() async {
    await haptics.tick();
    await voice.speak(
        _lastSpeech.isEmpty ? 'لسه مفيش نتيجة. صوّر الأول.' : _lastSpeech);
  }

  Future<void> _deleteFiles(List<String> paths) async {
    for (final p in paths) {
      try {
        await File(p).delete();
      } catch (_) {}
    }
  }
}
