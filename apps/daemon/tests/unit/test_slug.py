from datetime import date

from youtube_clipper.slug import (
    build_clip_id,
    build_job_dir_name,
    next_clip_suffix,
    slugify,
)


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_unicode():
    assert slugify("Café Münchner") == "cafe-munchner"


def test_slugify_empty():
    assert slugify("") == "untitled"


def test_slugify_only_punctuation():
    assert slugify("!!!???") == "untitled"


def test_slugify_truncates():
    assert len(slugify("a" * 80)) == 40


def test_next_clip_suffix_empty(tmp_path):
    assert next_clip_suffix(tmp_path, date(2026, 5, 17)) == 1


def test_next_clip_suffix_existing(tmp_path):
    (tmp_path / "2026-05-17_a_b_001").mkdir()
    (tmp_path / "2026-05-17_c_d_002").mkdir()
    (tmp_path / "2026-05-16_x_y_001").mkdir()  # different day, must be ignored
    (tmp_path / "not-a-clip-folder").mkdir()
    assert next_clip_suffix(tmp_path, date(2026, 5, 17)) == 3


def test_build_clip_id():
    assert build_clip_id(date(2026, 5, 17), 7) == "2026-05-17-007"


def test_build_job_dir_name():
    name = build_job_dir_name(
        date(2026, 5, 17), 1, "Andrej Karpathy", "Agents Have Arrived"
    )
    assert name == "2026-05-17_andrej-karpathy_agents-have-arrived_001"
