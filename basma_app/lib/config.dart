/// إعدادات التطبيق في مكان واحد.
class AppConfig {
  /// المحاكي (Android Emulator) -> 10.0.2.2
  /// موبايل حقيقي -> عنوان IP بتاع الكمبيوتر على الشبكة، مثلاً http://192.168.1.20:8000
  static const String backendUrl = 'http://10.0.2.2:8000';
  static const Duration requestTimeout = Duration(seconds: 12);

  /// عدد اللقطات المتتالية في كل محاولة (الـ Gate بيقرر بالتصويت بينهم)
  static const int burstFrames = 3;
  static const Duration burstGap = Duration(milliseconds: 250);

  /// true = نموذج تجريبي بيرد دايماً "50 جنيه" (للاختبار بس!)
  /// غيّرها لـ false لما عضو B يسلّم currency_model.tflite + labels.txt
  static const bool useMockCurrency = true;
  static const String currencyModelAsset = 'assets/models/currency_model.tflite';
  static const String currencyLabelsAsset = 'assets/models/labels.txt';
}
