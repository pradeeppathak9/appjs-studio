"""S3AssetStore against moto's S3 server (a local stand-in for R2 / S3; no network, no keys)."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from studio.config import Settings
from studio.storage import make_store
from studio.storage.local import LocalAssetStore
from studio.storage.s3 import S3AssetStore


@pytest.fixture
def store(s3_server, tmp_path) -> S3AssetStore:
    return S3AssetStore(
        "studio-test",
        tmp_path,
        endpoint_url=s3_server,
        region="us-east-1",
        access_key_id="test",
        secret_access_key="test",
        url_expiry_s=600,
    )


async def keys(store: S3AssetStore, prefix: str) -> list[str]:
    page = store.client.list_objects_v2(Bucket=store.bucket, Prefix=prefix)
    return sorted(o["Key"] for o in page.get("Contents", []))


async def test_s3_store_keeps_the_local_key_layout(store):
    rel, size = await store.put("job-a", "1-0", b"abc", "png")
    assert (rel, size) == ("assets/job-a/1-0.png", 3)
    assert await store.put_input("job-a", "photo", b"me", "jpg") == "inputs/job-a/photo.jpg"
    assert await store.put_upload("up-1", b"ref", "webp") == "uploads/up-1.webp"
    head = store.client.head_object(Bucket="studio-test", Key=rel)
    assert head["ContentType"] == "image/png"
    assert store.exists(rel) and not store.exists("assets/job-a/nope.png")


async def test_s3_store_moves_a_downloaded_file_into_the_bucket(store):
    src = store.temp_dir() / "video.download"
    src.write_bytes(b"movie")
    rel, size = await store.put("job-b", "1-0", src, "mp4")
    assert rel == "assets/job-b/1-0.mp4" and size == 5 and not src.exists()
    body = store.client.get_object(Bucket="studio-test", Key=rel)["Body"].read()
    assert body == b"movie"


async def test_s3_store_fetches_inputs_locally_and_releases_them(store):
    rel = await store.put_input("job-c", "photo", b"face", "jpg")
    path = await store.fetch_local(rel, "job-c")
    assert path.read_bytes() == b"face" and path.is_relative_to(store.temp_dir())
    await store.release_local("job-c")
    assert not path.exists()
    with pytest.raises(ValueError):
        await store.fetch_local("../../etc/passwd", "job-c")
    with pytest.raises(NotImplementedError):
        store.local_path(rel)


async def test_s3_store_deletes_paths_jobs_and_inputs(store):
    await store.put("job-d", "1-0", b"a", "png")
    await store.put("job-d", "1-1", b"b", "png")
    await store.put_input("job-d", "photo", b"c", "jpg")
    await store.delete_paths(["assets/job-d/1-0.png"])
    assert await keys(store, "assets/job-d/") == ["assets/job-d/1-1.png"]
    await store.delete_inputs("job-d")
    assert await keys(store, "inputs/job-d/") == []
    await store.put_input("job-d", "photo", b"c", "jpg")
    await store.delete_job("job-d")
    assert await keys(store, "assets/job-d/") == [] and await keys(store, "inputs/job-d/") == []
    await store.delete_paths([])  # no-op


async def test_presigned_urls_serve_the_file_inline(store):
    rel, _ = await store.put("job-e", "1-0", b"pixels", "png")
    url = store.public_url(rel, "image/png", "job-e-0.png")
    q = parse_qs(urlparse(url).query)
    assert q["X-Amz-Expires"] == ["600"] and "X-Amz-Signature" in q
    async with httpx.AsyncClient() as http:
        r = await http.get(url)
    assert r.status_code == 200 and r.content == b"pixels"
    assert r.headers["content-type"] == "image/png"
    assert r.headers["content-disposition"] == 'inline; filename="job-e-0.png"'
    async with httpx.AsyncClient() as http:  # the bucket itself is private
        assert (await http.get(url.split("?")[0])).status_code == 403


async def test_cdn_base_url_is_used_for_assets_and_uploads_but_not_inputs(store):
    store.public_base_url = "https://img.example.com"
    assert store.public_url("assets/j/1-0.png") == "https://img.example.com/assets/j/1-0.png"
    assert store.public_url("uploads/u.webp") == "https://img.example.com/uploads/u.webp"
    assert "X-Amz-Signature" in store.public_url("inputs/j/photo.jpg")


async def test_sweep_temp_clears_leftovers(store):
    (store.temp_dir() / "x.download").write_bytes(b"1")
    (store.temp_dir() / "jobs" / "j").mkdir(parents=True)
    assert store.sweep_temp() == 2 and not list(store.temp_dir().iterdir())


def test_make_store_picks_the_configured_store(tmp_path, s3_server):
    assert isinstance(make_store(Settings(_env_file=None, data_dir=tmp_path)), LocalAssetStore)
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        make_store(Settings(_env_file=None, data_dir=tmp_path, asset_store="s3"))
    s3 = make_store(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            asset_store="s3",
            s3_bucket="studio-test",
            s3_endpoint_url=s3_server,
            s3_access_key_id="test",
            s3_secret_access_key="test",
            s3_public_base_url="https://img.example.com/",
        )
    )
    assert isinstance(s3, S3AssetStore) and s3.public_base_url == "https://img.example.com"
    assert (tmp_path / "tmp").is_dir()
