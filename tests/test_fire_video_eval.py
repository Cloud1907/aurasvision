"""Saha videosu yangın kabul raporunun saf karar mantığı."""
from scripts.fire_video_eval import degerlendir, zaman_coz


def test_zaman_coz_saniye_ve_saat_bicimlerini_kabul_eder():
    assert zaman_coz("476") == 476.0
    assert zaman_coz("07:56") == 476.0
    assert zaman_coz("01:02:03.5") == 3723.5


def test_stabil_alarm_kabul_edilir():
    rapor = degerlendir(
        tespit_anlari=[476 + i for i in range(409)],
        alarm_anlari=[482.0, 602.0, 722.0, 842.0],
        pozitif=(476.0, 884.0), negatifler=[(0.0, 475.0)],
        azami_alarm_gecikmesi=10.0, azami_tespit_boslugu=2.0)
    assert rapor["passed"] is True
    assert rapor["first_alarm_latency_seconds"] == 6.0
    assert rapor["max_detection_gap_seconds"] == 1.0


def test_gec_alarm_reddedilir():
    rapor = degerlendir(
        tespit_anlari=[476 + i for i in range(409)], alarm_anlari=[490.0],
        pozitif=(476.0, 884.0), negatifler=[], azami_alarm_gecikmesi=10.0,
        azami_tespit_boslugu=2.0)
    assert rapor["passed"] is False
    assert any("gecikmesi" in n for n in rapor["failures"])


def test_uzun_tespit_boslugu_reddedilir():
    rapor = degerlendir(
        tespit_anlari=[476.0, 477.0, 500.0, 884.0], alarm_anlari=[480.0],
        pozitif=(476.0, 884.0), negatifler=[], azami_alarm_gecikmesi=10.0,
        azami_tespit_boslugu=2.0)
    assert rapor["passed"] is False
    assert any("tespit boşluğu" in n for n in rapor["failures"])


def test_yangin_oncesi_alarm_reddedilir():
    rapor = degerlendir(
        tespit_anlari=[476 + i for i in range(409)],
        alarm_anlari=[300.0, 480.0], pozitif=(476.0, 884.0),
        negatifler=[(0.0, 475.0)], azami_alarm_gecikmesi=10.0,
        azami_tespit_boslugu=2.0)
    assert rapor["passed"] is False
    assert rapor["negative_interval_alarms"] == [300.0]
