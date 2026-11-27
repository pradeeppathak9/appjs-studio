"""Assets in an S3-compatible bucket (Cloudflare R2, Backblaze B2, AWS S3, MinIO).

Same keys as LocalAssetStore (assets/, inputs/, uploads/). The bucket stays private: clients are
redirected to presigned GET URLs, or to S3_PUBLIC_BASE_URL/<key> for assets and uploads when a CDN
domain is set up. tmp/ stays on local disk (DATA_DIR/tmp): partial video downloads land there before
upload, and the worker copies a job's input photos there for providers to read.
"""

import asyncio
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3AssetStore:
    def __init__(
        self,
        bucket: str,
        temp_root: Path,
        *,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        public_base_url: str | None = None,
        url_expiry_s: int = 3600,
        client=None,
    ):
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self.url_expiry_s = url_expiry_s
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._tmp = temp_root.resolve() / "tmp"
        self._tmp.mkdir(parents=True, exist_ok=True)

    # ---- writes ---------------------------------------------------------------------------------
    def temp_dir(self) -> Path:
        return self._tmp

    def _upload(self, key: str, content: bytes | Path) -> int:
        extra = {"ContentType": mimetypes.guess_type(key)[0] or "application/octet-stream"}
        if isinstance(content, Path):
            size = content.stat().st_size
            self.client.upload_file(str(content), self.bucket, key, ExtraArgs=extra)
            content.unlink(missing_ok=True)
            return size
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, **extra)
        return len(content)

    async def put(self, job_id: str, name: str, content: bytes | Path, ext: str) -> tuple[str, int]:
        key = f"assets/{job_id}/{name}.{ext}"
        return key, await asyncio.to_thread(self._upload, key, content)

    async def put_input(self, job_id: str, slot: str, content: bytes, ext: str) -> str:
        key = f"inputs/{job_id}/{slot}.{ext}"
        await asyncio.to_thread(self._upload, key, content)
        return key

    async def put_upload(self, upload_id: str, content: bytes, ext: str) -> str:
        key = f"uploads/{upload_id}.{ext}"
        await asyncio.to_thread(self._upload, key, content)
        return key

    # ---- reads ----------------------------------------------------------------------------------
    @staticmethod
    def _check(rel_path: str) -> str:
        if rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise ValueError("path escapes the store root")
        return rel_path

    def local_path(self, rel_path: str) -> Path:
        raise NotImplementedError("files are in the bucket; use fetch_local or public_url")

    def _job_tmp(self, job_id: str) -> Path:
        return self._tmp / "jobs" / job_id

    async def fetch_local(self, rel_path: str, job_id: str) -> Path:
        key = self._check(rel_path)
        dest = self._job_tmp(job_id) / key.replace("/", "__")
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")

        def download():
            self.client.download_file(self.bucket, key, str(part))
            part.replace(dest)

        await asyncio.to_thread(download)
        return dest

    async def release_local(self, job_id: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self._job_tmp(job_id), True)

    def public_url(self, rel_path: str, mime_type: str | None = None, filename: str | None = None) -> str:
        key = self._check(rel_path)
        if self.public_base_url and not key.startswith("inputs/"):
            return f"{self.public_base_url}/{quote(key)}"
        params = {"Bucket": self.bucket, "Key": key}
        if mime_type:
            params["ResponseContentType"] = mime_type
        if filename:
            params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=self.url_expiry_s)

    # ---- deletes --------------------------------------------------------------------------------
    def _delete_keys(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            batch = [{"Key": k} for k in keys[i : i + 1000]]
            if batch:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})

    def _delete_prefix(self, prefix: str) -> None:
        keys: list[str] = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys += [o["Key"] for o in page.get("Contents", [])]
        self._delete_keys(keys)

    async def delete_job(self, job_id: str) -> None:
        for sub in ("assets", "inputs"):
            await asyncio.to_thread(self._delete_prefix, f"{sub}/{job_id}/")

    async def delete_inputs(self, job_id: str) -> None:
        await asyncio.to_thread(self._delete_prefix, f"inputs/{job_id}/")

    async def delete_paths(self, rel_paths: list[str]) -> None:
        if rel_paths:
            await asyncio.to_thread(self._delete_keys, [self._check(p) for p in rel_paths])

    def sweep_temp(self) -> int:
        removed = 0
        for p in self._tmp.iterdir():
            p.unlink(missing_ok=True) if p.is_file() else shutil.rmtree(p, True)
            removed += 1
        return removed

    def exists(self, rel_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._check(rel_path))
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
