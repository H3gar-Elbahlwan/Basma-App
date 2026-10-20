import '../models/gate_decision.dart';

/// نسخة Dart من decide_currency في الباك إند (confidence_gate.py).
/// الفلوس بتتقرر على الجهاز عشان تشتغل Offline.
/// ⚠️ أي تغيير في الأرقام هنا لازم يتعمل في الباك إند والعكس (نفس القيم الابتدائية).
class CurrencyGateConfig {
  const CurrencyGateConfig({
    this.minFrames = 3,
    this.agreeRatio = 0.6,
    this.minMeanProb = 0.85,
    this.minMargin = 0.30,
    this.notMoneyLabel = 'not_money',
    this.handoffAfterAttempts = 3,
  });

  final int minFrames;
  final double agreeRatio;
  final double minMeanProb;
  final double minMargin;
  final String notMoneyLabel;
  final int handoffAfterAttempts;
}

const Map<String, String> kCurrencySpeech = {
  '5': 'خمسة جنيه',
  '10': 'عشرة جنيه',
  '20': 'عشرين جنيه',
  '50': 'خمسين جنيه',
  '100': 'مية جنيه',
  '200': 'ميتين جنيه',
};

const String _handoffSpeech =
    'مش قادر أتأكد من القراءة. تحب أوصّلك بمتطوع يشوف معاك؟ دوس على أيوه أو لأ.';

String _argmax(Map<String, double> f) {
  var best = f.keys.first;
  for (final e in f.entries) {
    if (e.value > f[best]!) best = e.key;
  }
  return best;
}

GateDecision decideCurrency(
  List<Map<String, double>> frames, {
  int attempt = 1,
  CurrencyGateConfig cfg = const CurrencyGateConfig(),
}) {
  final giveUp = attempt >= cfg.handoffAfterAttempts;

  if (frames.length < cfg.minFrames) {
    return GateDecision(
      action: GateAction.retry,
      speechAr: 'ثبّت الكاميرا شوية وخلّيني أشوف تاني.',
      haptic: HapticKind.warning,
      reasons: ['frames=${frames.length}<${cfg.minFrames}'],
    );
  }

  // تصويت: أكتر فئة طلعت في الفريمات
  final votes = <String, int>{};
  for (final f in frames) {
    final l = _argmax(f);
    votes[l] = (votes[l] ?? 0) + 1;
  }
  var topLabel = votes.keys.first;
  for (final e in votes.entries) {
    if (e.value > votes[topLabel]!) topLabel = e.key;
  }
  final topCount = votes[topLabel]!;

  // متوسط الاحتمالات + الفرق بين أول وتاني فئة
  final mean = <String, double>{
    for (final l in frames.first.keys)
      l: frames.map((f) => f[l] ?? 0.0).reduce((a, b) => a + b) / frames.length,
  };
  final ranked = mean.values.toList()..sort((a, b) => b.compareTo(a));
  final margin = ranked.length > 1 ? ranked[0] - ranked[1] : ranked[0];

  final reasons = [
    'top=$topLabel votes=$topCount/${frames.length} '
        'mean=${mean[topLabel]!.toStringAsFixed(2)} '
        'margin=${margin.toStringAsFixed(2)}',
  ];
  final agreed = topCount >= cfg.agreeRatio * frames.length;

  if (agreed && topLabel == cfg.notMoneyLabel && mean[topLabel]! >= 0.6) {
    return GateDecision(
      action: GateAction.retry,
      speechAr: 'مش شايف ورقة فلوس. وجّه الكاميرا ناحية الورقة وصوّر تاني.',
      haptic: HapticKind.warning,
      reasons: reasons,
    );
  }

  if (agreed &&
      kCurrencySpeech.containsKey(topLabel) &&
      mean[topLabel]! >= cfg.minMeanProb &&
      margin >= cfg.minMargin) {
    return GateDecision(
      action: GateAction.accept,
      speechAr: 'دي ${kCurrencySpeech[topLabel]}.',
      haptic: HapticKind.success,
      reasons: reasons,
      data: {'denomination': topLabel},
    );
  }

  if (giveUp) {
    return GateDecision(
      action: GateAction.handoffOffer,
      speechAr: _handoffSpeech,
      haptic: HapticKind.warning,
      reasons: reasons,
    );
  }
  return GateDecision(
    action: GateAction.retry,
    speechAr:
        'مش متأكد من الورقة دي. افردها كويس وخلّيها قدام الكاميرا ونوّر المكان وصوّر تاني.',
    haptic: HapticKind.warning,
    reasons: reasons,
  );
}
