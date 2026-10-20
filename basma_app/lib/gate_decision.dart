/// نفس عقد (contract) الـ Confidence Gate في الباك إند.
enum GateAction { accept, retry, handoffOffer }

enum HapticKind { success, warning, error, none }

class GateDecision {
  const GateDecision({
    required this.action,
    required this.speechAr,
    this.haptic = HapticKind.none,
    this.reasons = const [],
    this.data = const {},
  });

  final GateAction action;
  final String speechAr; // الجملة اللي بتتنطق بالمصري
  final HapticKind haptic;
  final List<String> reasons; // للـ debugging فقط، مش بتتنطق
  final Map<String, dynamic> data;

  factory GateDecision.fromJson(Map<String, dynamic> json) {
    return GateDecision(
      action: _parseAction(json['action'] as String),
      speechAr: json['speech_ar'] as String,
      haptic: _parseHaptic((json['haptic'] as String?) ?? 'none'),
      reasons: ((json['reasons'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      data: Map<String, dynamic>.from((json['data'] as Map?) ?? const {}),
    );
  }

  static GateAction _parseAction(String s) {
    switch (s) {
      case 'ACCEPT':
        return GateAction.accept;
      case 'RETRY':
        return GateAction.retry;
      case 'HANDOFF_OFFER':
        return GateAction.handoffOffer;
    }
    throw FormatException('Unknown gate action: $s');
  }

  static HapticKind _parseHaptic(String s) {
    switch (s) {
      case 'success':
        return HapticKind.success;
      case 'warning':
        return HapticKind.warning;
      case 'error':
        return HapticKind.error;
      default:
        return HapticKind.none;
    }
  }
}
