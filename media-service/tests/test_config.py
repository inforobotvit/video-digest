from pathlib import Path

from app.config import Settings


def test_empty_optional_env_values_become_none(tmp_path: Path) -> None:
    s = Settings(_env_file=None, data_dir=tmp_path, ytdlp_cookies_file="", ytdlp_proxy="  ")
    assert s.ytdlp_cookies_file is None
    assert s.ytdlp_proxy is None


def test_optional_env_values_kept(tmp_path: Path) -> None:
    s = Settings(_env_file=None, data_dir=tmp_path, ytdlp_cookies_file="/c.txt", ytdlp_proxy="x")
    assert s.ytdlp_cookies_file == Path("/c.txt")
    assert s.ytdlp_proxy == "x"
