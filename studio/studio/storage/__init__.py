from studio.config import Settings
from studio.storage.base import AssetStore
from studio.storage.local import LocalAssetStore


def make_store(settings: Settings) -> AssetStore:
    """ASSET_STORE=local (DATA_DIR, the default) or s3 (an S3-compatible bucket, see docs/STORAGE.md)."""
    if settings.asset_store == "local":
        return LocalAssetStore(settings.data_dir)
    from studio.storage.s3 import S3AssetStore

    if not settings.s3_bucket:
        raise RuntimeError("ASSET_STORE=s3 needs S3_BUCKET (and usually S3_ENDPOINT_URL and keys)")

    def secret(v):
        return v.get_secret_value() if v else None

    return S3AssetStore(
        settings.s3_bucket,
        settings.data_dir,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key_id=secret(settings.s3_access_key_id),
        secret_access_key=secret(settings.s3_secret_access_key),
        public_base_url=settings.s3_public_base_url,
        url_expiry_s=settings.s3_url_expiry_s,
    )
