"""
بصمة - سيرفر تطوير بسيط (بدون أي مكتبات إضافية) يربط تطبيق Flutter بالـ Gate.

    python server.py            # يشتغل على 0.0.0.0:8000

Endpoints:
    GET  /health
    POST /medicine/decide
         {"frames": [{"ocr_text": "..."}, ...], "attempt": 1}
      -> {"action": "ACCEPT|RETRY|HANDOFF_OFFER", "speech_ar": "...",
          "haptic": "success|warning|error|none", "reasons": [...], "data": {...}}

ملاحظات:
  * الفلوس بتتقرر جوّه التطبيق نفسه (Offline)، فمفيش endpoint ليها هنا.
  * ده للتطوير والعرض بس: مفيش تشفير (HTTP) ولا مصادقة. قبل أي استخدام حقيقي
    انقلوه لـ HTTPS (أو FastAPI + reverse proxy) وأضيفوا مصادقة.
  * مابنسجّلش نصوص الـ OCR في الـ logs.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from confidence_gate import Decision, MedicineFrame, decide_medicine
from medicine_matcher import MedicineMatcher

MAX_FRAMES = 10
MAX_TEXT_LEN = 5000
MAX_BODY_BYTES = 200_000

_matcher = MedicineMatcher.from_csv(Path(__file__).parent / "data" / "medicines_sample.csv")


def decision_to_dict(d: Decision) -> dict:
    return {
        "action": d.action.value,
        "speech_ar": d.speech_ar,
        "haptic": d.haptic,
        "reasons": d.reasons,
        "data": d.data,
    }


def medicine_decide(payload: dict) -> dict:
    """بيتحقق من المدخلات ويرجّع قرار الـ Gate. بيرفع ValueError لو المدخلات غلط."""
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    raw_frames = payload.get("frames")
    if not isinstance(raw_frames, list) or not 1 <= len(raw_frames) <= MAX_FRAMES:
        raise ValueError(f"frames must be a list of 1..{MAX_FRAMES} items")
    attempt = payload.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or not 1 <= attempt <= 20:
        raise ValueError("attempt must be an integer between 1 and 20")

    frames = []
    for item in raw_frames:
        text = item.get("ocr_text", "") if isinstance(item, dict) else None
        if not isinstance(text, str) or len(text) > MAX_TEXT_LEN:
            raise ValueError("each frame needs an 'ocr_text' string")
        frames.append(MedicineFrame(match=_matcher.match(text), ocr_text=text))

    return decision_to_dict(decide_medicine(frames, attempt=attempt))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/medicine/decide":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("bad body size")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self._send(200, medicine_decide(payload))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send(400, {"error": str(e)})

    def log_message(self, fmt, *args):   # بدون logs لمحتوى الطلبات
        pass


if __name__ == "__main__":
    print("Basma dev server on http://0.0.0.0:8000  (Ctrl+C to stop)")
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
