"""Tests for image_io helpers."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from pipeworks_character_forge.core import image_io


def _png_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = Image.new("RGB", (32, 32), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class TestNormalizeRgb:
    def test_passthrough_when_already_rgb(self) -> None:
        image = Image.new("RGB", (4, 4))
        assert image_io.normalize_rgb(image) is image

    def test_converts_rgba_to_rgb(self) -> None:
        image = Image.new("RGBA", (4, 4))
        result = image_io.normalize_rgb(image)
        assert result.mode == "RGB"


class TestMakeSourceId:
    def test_format_is_timestamp_underscore_5char_hash(self) -> None:
        source_id = image_io.make_source_id(b"hello")
        assert "_" in source_id
        prefix, digest = source_id.rsplit("_", 1)
        assert len(digest) == 5
        assert prefix.count("-") >= 3  # YYYY-MM-DDTHH-MM

    def test_distinct_payloads_yield_distinct_ids(self) -> None:
        a = image_io.make_source_id(b"a" * 32)
        b = image_io.make_source_id(b"b" * 32)
        assert a != b


class TestLoadImageBytes:
    def test_loads_png_to_rgb(self) -> None:
        image = image_io.load_image_bytes(_png_bytes())
        assert image.mode == "RGB"
        assert image.size == (32, 32)


class TestSavePng:
    def test_creates_parent_dirs(self, tmp_path) -> None:
        target = tmp_path / "nested" / "out.png"
        image = Image.new("RGB", (8, 8))
        image_io.save_png(image, target)
        assert target.is_file()
