// بَصمة (Basma) - Walking Skeleton - Member A (Mobile/UX)
import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

List<CameraDescription> _cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    _cameras = await availableCameras();
  } on CameraException {
    _cameras = [];
  }
  runApp(const BasmaApp());
}

class BasmaApp extends StatelessWidget {
  const BasmaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'بصمة',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFFFFC107),
        useMaterial3: true,
      ),
      builder: (context, child) =>
          Directionality(textDirection: TextDirection.rtl, child: child!),
      home: const HomeScreen(),
    );
  }
}

class VoiceService {
  final FlutterTts _tts = FlutterTts();

  Future<void> init() async {
    final egAvailable = await _tts.isLanguageAvailable('ar-EG');
    await _tts.setLanguage(egAvailable == true ? 'ar-EG' : 'ar');
    await _tts.setSpeechRate(0.45);
    await _tts.setPitch(1.0);
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(true);
  }

  Future<void> speak(String text) async {
    await _tts.stop();
    await _tts.speak(text);
  }

  Future<void> stop() => _tts.stop();
}

class Haptics {
  static Future<void> tap() => HapticFeedback.selectionClick();
  static Future<void> capture() => HapticFeedback.mediumImpact();
  static Future<void> success() async {
    await HapticFeedback.lightImpact();
    await Future.delayed(const Duration(milliseconds: 120));
    await HapticFeedback.lightImpact();
  }

  static Future<void> error() async {
    await HapticFeedback.heavyImpact();
    await Future.delayed(const Duration(milliseconds: 200));
    await HapticFeedback.heavyImpact();
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  final VoiceService _voice = VoiceService();
  CameraController? _controller;
  bool _busy = false;
  String _lastResult = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _voice.init();
    await _initCamera();
    await _voice.speak(
      'أهلاً بيك في بصمة. وجّه الكاميرا ناحية الحاجة، '
      'وبعدين دوس على الزرار الكبير اللي تحت عشان تصوّر.',
    );
  }

  Future<void> _initCamera() async {
    if (_cameras.isEmpty) {
      await Haptics.error();
      await _voice.speak('مش لاقي كاميرا على الجهاز.');
      return;
    }
    final controller = CameraController(
      _cameras.first,
      ResolutionPreset.high,
      enableAudio: false,
    );
    try {
      await controller.initialize();
      if (!mounted) return;
      setState(() => _controller = controller);
    } on CameraException catch (e) {
      await Haptics.error();
      if (e.code == 'CameraAccessDenied') {
        await _voice.speak('محتاج إذن الكاميرا عشان أشتغل.');
      } else {
        await _voice.speak('حصلت مشكلة في تشغيل الكاميرا.');
      }
    }
  }

  Future<void> _onCapture() async {
    final c = _controller;
    if (_busy || c == null || !c.value.isInitialized) return;
    setState(() => _busy = true);

    try {
      await Haptics.capture();
      final XFile photo = await c.takePicture();
      await _voice.speak('جاري التحليل.');
      final result = await _mockAnalyze(photo);

      _lastResult = result;
      await Haptics.success();
      await _voice.speak(result);
    } on CameraException {
      await Haptics.error();
      await _voice.speak('معرفتش أصوّر. جرّب تاني.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String> _mockAnalyze(XFile photo) async {
    await Future.delayed(const Duration(milliseconds: 800));
    return 'ده كونكور خمسة ملّي. الصلاحية مكتوب عليها مارس ألفين وسبعة وعشرين.';
  }

  Future<void> _onRepeat() async {
    await Haptics.tap();
    if (_lastResult.isEmpty) {
      await _voice.speak('لسه مفيش نتيجة. صوّر الأول.');
    } else {
      await _voice.speak(_lastResult);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    _voice.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Column(
        children: [
          Expanded(
            flex: 7,
            child: _buildPreview(),
          ),
          Expanded(
            flex: 2,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFFFC107),
                minimumSize: const Size.fromHeight(50),
              ),
              onPressed: _onCapture,
              icon: const Icon(Icons.camera_alt, color: Colors.black, size: 35),
              label: Text(
                _busy ? 'جاري التحليل...' : 'صوّر',
                style: const TextStyle(color: Colors.black, fontSize: 28),
              ),
            ),
          ),
          Expanded(
            flex: 1,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF263238),
                minimumSize: const Size.fromHeight(50),
              ),
              onPressed: _onRepeat,
              icon: const Icon(Icons.replay, color: Colors.white, size: 30),
              label: const Text(
                'اسمع تاني',
                style: TextStyle(color: Colors.white, fontSize: 22),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreview() {
    final c = _controller;
    if (c == null || !c.value.isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }
    return CameraPreview(c);
  }
}
