import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../config.dart';
import '../logic/scan_controller.dart';
import '../services/backend_client.dart';
import '../services/camera_service.dart';
import '../services/currency_classifier.dart';
import '../services/haptics_service.dart';
import '../services/ocr_service.dart';
import '../services/voice_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  final _voice = VoiceService();
  final _haptics = HapticsService();
  final _camera = CameraService();
  final _backend = BackendClient();
  final _ocr = OcrService();
  late final CurrencyClassifier _currency = AppConfig.useMockCurrency
      ? MockCurrencyClassifier()
      : TfliteCurrencyClassifier();
  late final ScanController _scan = ScanController(
    camera: _camera,
    voice: _voice,
    haptics: _haptics,
    backend: _backend,
    ocr: _ocr,
    currency: _currency,
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _voice.init();
    await _haptics.init();
    try {
      await _currency.load();
    } catch (e) {
      debugPrint('Currency model load failed: $e');
      await _voice.speak('نموذج الفلوس مش متاح. قراءة الدواء لسه شغالة.');
    }
    await _startCamera();
    await _voice.speak(
      'أهلاً بيك في بصمة. دوس على اقرا الدواء، أو اعرف الفلوس، '
      'وبعدين ثبّت الموبايل على الحاجة.',
    );
  }

  Future<void> _startCamera() async {
    try {
      await _camera.init();
      if (mounted) setState(() {});
    } on CameraException catch (e) {
      await _voice.speak(e.code == 'CameraAccessDenied'
          ? 'محتاج إذن الكاميرا عشان أشتغل. فعّله من إعدادات الموبايل.'
          : 'مش لاقي كاميرا شغالة على الجهاز.');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive) {
      _camera.pause().then((_) {
        if (mounted) setState(() {});
      });
    } else if (state == AppLifecycleState.resumed && !_camera.isReady) {
      _startCamera();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _scan.dispose();
    _camera.dispose();
    _ocr.dispose();
    _currency.dispose();
    _voice.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: ListenableBuilder(
          listenable: _scan,
          builder: (context, _) {
            final handoff = _scan.state == ScanState.awaitingHandoff;
            final busy = _scan.busy;
            return Column(
              children: [
                Expanded(
                  flex: 6,
                  child: Semantics(label: 'معاينة الكاميرا', child: _preview()),
                ),
                Expanded(
                  flex: 3,
                  child: handoff ? _handoffButtons() : _scanButtons(busy),
                ),
                Expanded(
                  flex: 1,
                  child: _BigButton(
                    label: 'اسمع تاني',
                    semantics: 'زرار إعادة سماع آخر نتيجة.',
                    icon: Icons.replay_rounded,
                    color: const Color(0xFF263238),
                    textColor: Colors.white,
                    onPressed: busy ? null : _scan.repeatLast,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _scanButtons(bool busy) {
    return Row(
      children: [
        Expanded(
          child: _BigButton(
            label: busy ? 'استنى...' : 'اقرا الدواء',
            semantics: 'زرار قراءة الدواء. دوس مرتين عشان تبدأ.',
            icon: Icons.medication_rounded,
            color: const Color(0xFFFFC107),
            textColor: Colors.black,
            onPressed: busy ? null : () => _scan.scan(ScanMode.medicine),
          ),
        ),
        Expanded(
          child: _BigButton(
            label: busy ? 'استنى...' : 'اعرف الفلوس',
            semantics: 'زرار التعرف على الفلوس. دوس مرتين عشان تبدأ.',
            icon: Icons.payments_rounded,
            color: const Color(0xFF66BB6A),
            textColor: Colors.black,
            onPressed: busy ? null : () => _scan.scan(ScanMode.currency),
          ),
        ),
      ],
    );
  }

  Widget _handoffButtons() {
    return Row(
      children: [
        Expanded(
          child: _BigButton(
            label: 'أيوه',
            semantics: 'أيوه، وصّلني بمتطوع.',
            icon: Icons.check_rounded,
            color: const Color(0xFF42A5F5),
            textColor: Colors.black,
            onPressed: () => _scan.answerHandoff(accepted: true),
          ),
        ),
        Expanded(
          child: _BigButton(
            label: 'لأ',
            semantics: 'لأ، شكراً.',
            icon: Icons.close_rounded,
            color: const Color(0xFF546E7A),
            textColor: Colors.white,
            onPressed: () => _scan.answerHandoff(accepted: false),
          ),
        ),
      ],
    );
  }

  Widget _preview() {
    final c = _camera.controller;
    if (c == null || !c.value.isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }
    return ClipRect(
      child: SizedBox.expand(
        child: FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: c.value.previewSize!.height,
            height: c.value.previewSize!.width,
            child: CameraPreview(c),
          ),
        ),
      ),
    );
  }
}

class _BigButton extends StatelessWidget {
  const _BigButton({
    required this.label,
    required this.semantics,
    required this.icon,
    required this.color,
    required this.textColor,
    required this.onPressed,
  });

  final String label;
  final String semantics;
  final IconData icon;
  final Color color;
  final Color textColor;
  final VoidCallback? onPressed; // null = متعطّل

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return Semantics(
      button: true,
      enabled: enabled,
      label: semantics,
      excludeSemantics: true, // TalkBack يقرا الـ label ده بس
      child: Material(
        color: enabled ? color : color.withOpacity(0.4),
        child: InkWell(
          onTap: onPressed,
          child: SizedBox.expand(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 40, color: textColor),
                const SizedBox(height: 6),
                Text(
                  label,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: textColor,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
