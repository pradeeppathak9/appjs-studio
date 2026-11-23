import io

import pytest
from PIL import Image

from studio.media.images import InvalidImage, normalize_image
from studio.storage.local import LocalAssetStore
from tests.conftest import image_bytes

LIMITS = {"max_pixels": 40_000_000, "max_side": 2048}


def test_exif_orientation_is_applied_and_metadata_dropped():
    raw = image_bytes((300, 200), exif_orientation=6)  # stored landscape, "rotate 90" in EXIF
    clean = normalize_image(raw, **LIMITS)
    assert (clean.width, clean.height) == (200, 300)
    with Image.open(io.BytesIO(clean.data)) as img:
        assert not img.getexif()


def test_large_images_are_downscaled():
    clean = normalize_image(image_bytes((4000, 1000), fmt="PNG"), **LIMITS)
    assert (clean.width, clean.height) == (2048, 512)
    assert clean.mime_type == "image/png" and clean.ext == "png"


@pytest.mark.parametrize("data", [b"", b"plain text", image_bytes(fmt="GIF")])
def test_non_images_and_other_formats_are_rejected(data):
    with pytest.raises(InvalidImage):
        normalize_image(data, **LIMITS)


def test_too_many_pixels_is_rejected_before_decoding():
    with pytest.raises(InvalidImage):
        normalize_image(image_bytes((3000, 3000), fmt="PNG"), max_pixels=1_000_000, max_side=2048)


async def test_store_writes_atomically_and_refuses_path_escape(tmp_path):
    store = LocalAssetStore(tmp_path)
    rel, size = await store.put("job1", "1-0", b"abc", "png")
    assert rel == "assets/job1/1-0.png" and size == 3
    assert store.local_path(rel).read_bytes() == b"abc"
    assert not list(tmp_path.rglob("*.part"))
    with pytest.raises(ValueError):
        store.local_path("../../etc/passwd")
    src = store.temp_dir() / "video.download"
    src.write_bytes(b"movie")
    rel, _ = await store.put("job1", "1-1", src, "mp4")
    assert not src.exists() and store.local_path(rel).read_bytes() == b"movie"
    await store.delete_paths(["assets/job1/1-0.png"])
    assert not (tmp_path / "assets/job1/1-0.png").exists()
    await store.delete_job("job1")
    assert not (tmp_path / "assets/job1").exists()
