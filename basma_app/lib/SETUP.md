# basma_app — خطوات الإعداد

## 1) المكتبات
من جوّه فولدر المشروع (بيسحب آخر إصدار لكل مكتبة):

    flutter pub add camera flutter_tts vibration http image \
        google_mlkit_text_recognition tflite_flutter

وفي `pubspec.yaml` تحت `flutter:` ضيفوا:

    flutter:
      assets:
        - assets/models/

## 2) android/app/src/main/AndroidManifest.xml (قبل <application>)

    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.CAMERA"/>
    <uses-permission android:name="android.permission.VIBRATE"/>
    <queries>
      <intent><action android:name="android.intent.action.TTS_SERVICE"/></intent>
    </queries>

وجوّه وسم <application> ضيفوا (للتطوير فقط، لأن السيرفر HTTP مش HTTPS):

    android:usesCleartextTraffic="true"

## 3) android/app/build.gradle
`minSdkVersion` على 24 أو أعلى (لو الـ build اشتكى ارفعوه، tflite_flutter أحياناً بتطلب 26).

## 4) تشغيل الباك إند
    cd basma_backend && python server.py
- المحاكي: AppConfig.backendUrl = http://10.0.2.2:8000 (الافتراضي)
- موبايل حقيقي: حطوا IP الكمبيوتر على نفس الواي فاي، مثلاً http://192.168.1.20:8000
  (وتأكدوا إن الـ Firewall بيسمح بالمنفذ 8000)

## 5) لما عضو B يسلّم النموذج
حطوا currency_model.tflite و labels.txt في assets/models/ وغيّروا
AppConfig.useMockCurrency إلى false.
