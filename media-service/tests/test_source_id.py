from pathlib import Path

from app.services.source_id import source_id_for_bytes, source_id_for_file, source_id_for_media


def test_media_id_is_12_hex_and_stable() -> None:
    a = source_id_for_media("youtube", "dQw4w9WgXcQ")
    b = source_id_for_media("Youtube ", "dQw4w9WgXcQ")
    assert a == b
    assert len(a) == 12
    assert int(a, 16) >= 0


def test_media_id_differs_by_extractor_and_id() -> None:
    assert source_id_for_media("youtube", "abc") != source_id_for_media("vk", "abc")
    assert source_id_for_media("youtube", "abc") != source_id_for_media("youtube", "abd")


def test_file_id_matches_bytes_id(tmp_path: Path) -> None:
    payload = b"RIFF" + bytes(range(256)) * 10
    f = tmp_path / "clip.wav"
    f.write_bytes(payload)
    assert source_id_for_file(f) == source_id_for_bytes([payload])
    assert source_id_for_file(f) == source_id_for_bytes([payload[:100], payload[100:]])
