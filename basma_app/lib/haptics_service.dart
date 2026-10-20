import 'package:flutter/services.dart';
import 'package:vibration/vibration.dart';

import '../models/gate_decision.dart';

/// لغة الاهتزاز في بصمة (المستخدم يفهم الحالة من غير ما يسمع):
///
///   tick       نبضة قصيرة جداً       تأكيد ضغطة / كل لقطة بتتاخد
///   retry      اهتزازة خفيفة واحدة   محتاج يصوّر تاني
///   success    اهتزازتين قويتين      نجاح التحقق
///   attention  3 نبضات متوسطة        تحذير / عرض متطوع
///   expired    اهتزازة طويلة قوية    الدواء منتهي الصلاحية
///
/// لو الجهاز مفيهوش vibrator أو التحكم في الشدة، بنرجع لـ HapticFeedback العادي.
class HapticsService {
  bool _hasVibrator = false;

  Future<void> init() async {
    _hasVibrator = (await Vibration.hasVibrator()) == true;
  }

  Future<void> _buzz({
    int duration = 100,
    int amplitude = -1,
    List<int> pattern = const [],
    List<int> intensities = const [],
    required Future<void> Function() fallback,
  }) async {
    if (!_hasVibrator) return fallback();
    if (pattern.isNotEmpty) {
      await Vibration.vibrate(pattern: pattern, intensities: intensities);
    } else {
      await Vibration.vibrate(duration: duration, amplitude: amplitude);
    }
  }

  Future<void> tick() => _buzz(
        duration: 25,
        amplitude: 120,
        fallback: HapticFeedback.selectionClick,
      );

  Future<void> retry() => _buzz(
        duration: 70,
        amplitude: 90,
        fallback: HapticFeedback.lightImpact,
      );

  Future<void> success() => _buzz(
        pattern: const [0, 300, 120, 300],
        intensities: const [0, 255, 0, 255],
        fallback: () async {
          await HapticFeedback.heavyImpact();
          await Future.delayed(const Duration(milliseconds: 150));
          await HapticFeedback.heavyImpact();
        },
      );

  Future<void> attention() => _buzz(
        pattern: const [0, 140, 100, 140, 100, 140],
        intensities: const [0, 180, 0, 180, 0, 180],
        fallback: () async {
          for (var i = 0; i < 3; i++) {
            await HapticFeedback.mediumImpact();
            await Future.delayed(const Duration(milliseconds: 120));
          }
        },
      );

  Future<void> expired() => _buzz(
        duration: 700,
        amplitude: 255,
        fallback: () async {
          for (var i = 0; i < 3; i++) {
            await HapticFeedback.heavyImpact();
            await Future.delayed(const Duration(milliseconds: 150));
          }
        },
      );

  /// الربط الأساسي: حالة الـ Gate -> نمط الاهتزاز.
  Future<void> forDecision(GateDecision d) {
    switch (d.action) {
      case GateAction.accept:
        switch (d.haptic) {
          case HapticKind.error:
            return expired(); // مقبول بس الدواء منتهي
          case HapticKind.warning:
            return attention(); // بينتهي الشهر ده
          default:
            return success();
        }
      case GateAction.retry:
        return retry();
      case GateAction.handoffOffer:
        return attention();
    }
  }
}
