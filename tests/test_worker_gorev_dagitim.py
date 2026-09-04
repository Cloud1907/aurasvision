"""Worker'ın canlı-kaynak + çoklu-görev dispatch mantığı.

Neden test ediliyor: kamera-204 (count+plate, RTSP) üretimde plate_events HİÇ
satır üretmedi çünkü count()'un yolo.track(stream=True) generator'ı asla
dönmüyor — aynı thread'de sıradaki görev sonsuza dek bekliyordu. Fix, canlı +
birden çok görev olduğunda her görevi AYRI thread'de çalıştırıyor
(src/worker.py:_run_camera). Burada gerçek model/RTSP olmadan test edilebilen
iki parça: (1) hangi kaynak "canlı" sayılır, (2) bir görevin hatası diğer
görev thread'ini veya kamerayı düşürmüyor mu.
"""
import unittest
from unittest.mock import patch

from src.worker import _canli_kaynak, _gorev_thread_calistir


class CanliKaynakTest(unittest.TestCase):
    def test_rtsp_canli_sayilir(self):
        self.assertTrue(_canli_kaynak("rtsp://admin:x@192.168.1.10:554/stream"))

    def test_http_canli_sayilir(self):
        self.assertTrue(_canli_kaynak("https://ornek.com/live.m3u8"))

    def test_buyuk_harf_de_yakalanir(self):
        self.assertTrue(_canli_kaynak("RTSP://192.168.1.10/stream"))

    def test_dosya_yolu_canli_degildir(self):
        self.assertFalse(_canli_kaynak("data/videos/people-detection.mp4"))

    def test_windows_mutlak_yol_canli_degildir(self):
        self.assertFalse(_canli_kaynak(r"C:\videos\kayit.mp4"))


class GorevThreadIzolasyonuTest(unittest.TestCase):
    def test_bir_gorevin_hatasi_disariya_sizmaz(self):
        """_gorev_thread_calistir threading.Thread(target=...) olarak çağrılır —
        burada patlarsa sessizce loglanıp yutulmalı, aksi hâlde thread ölür ama
        kimse haberdar olmaz ve diğer eşzamanlı görev thread'i etkilenmemeli."""
        with patch("src.worker._gorev_calistir", side_effect=RuntimeError("kamera koptu")):
            try:
                _gorev_thread_calistir("plate", "rtsp://x", None, None, "kamera-204", None, [])
            except Exception as e:  # noqa: BLE001 — burada YAKALANMAMASI test başarısızlığıdır
                self.fail(f"_gorev_thread_calistir hatayı dışarı sızdırdı: {e}")

    def test_hatasiz_gorev_normal_calisir(self):
        with patch("src.worker._gorev_calistir") as m:
            _gorev_thread_calistir("count", "rtsp://x", None, None, "kamera-204", None, [])
            m.assert_called_once_with("count", "rtsp://x", None, None, "kamera-204", None, [], None)


if __name__ == "__main__":
    unittest.main()
