import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models/gate_decision.dart';

class BackendException implements Exception {
  BackendException(this.message);
  final String message;
  @override
  String toString() => 'BackendException: $message';
}

/// بيكلّم سيرفر الباك إند (server.py) ويرجّع قرار الـ Confidence Gate للأدوية.
class BackendClient {
  BackendClient({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Future<GateDecision> decideMedicine({
    required List<String> ocrTexts,
    required int attempt,
  }) async {
    final uri = Uri.parse('${AppConfig.backendUrl}/medicine/decide');
    final body = jsonEncode({
      'frames': [
        for (final t in ocrTexts) {'ocr_text': t}
      ],
      'attempt': attempt,
    });
    try {
      final res = await _client
          .post(uri,
              headers: {'Content-Type': 'application/json; charset=utf-8'},
              body: body)
          .timeout(AppConfig.requestTimeout);
      if (res.statusCode != 200) {
        throw BackendException('HTTP ${res.statusCode}');
      }
      final json = jsonDecode(utf8.decode(res.bodyBytes));
      return GateDecision.fromJson(json as Map<String, dynamic>);
    } on BackendException {
      rethrow;
    } catch (e) {
      // Timeout / SocketException / FormatException ...
      throw BackendException(e.toString());
    }
  }
}
