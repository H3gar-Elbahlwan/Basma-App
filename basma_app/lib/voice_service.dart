import 'package:flutter_tts/flutter_tts.dart';

/// النطق بالعربي (بنحاول لهجة مصر، ولو مش متاحة نرجع للعربي العام).
class VoiceService {
  final FlutterTts _tts = FlutterTts();

  Future<void> init() async {
    final eg = await _tts.isLanguageAvailable('ar-EG');
    await _tts.setLanguage(eg == true ? 'ar-EG' : 'ar');
    await _tts.setSpeechRate(0.45);
    await _tts.setPitch(1.0);
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(true); // الـ await يستنى لحد ما الكلام يخلص
  }

  /// بيوقف أي كلام شغال الأول، وبعدين يقول الجملة الجديدة.
  Future<void> speak(String text) async {
    await _tts.stop();
    await _tts.speak(text);
  }

  Future<void> stop() => _tts.stop();
}
