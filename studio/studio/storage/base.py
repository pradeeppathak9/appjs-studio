from pathlib import Path
from typing import Protocol

# Key layout, the same for every store:
#   assets/<job_id>/<attempt>-<idx>.<ext>  generated outputs
#   inputs/<job_id>/<slot>.<ext>           images uploaded with a template call
#   uploads/<upload_id>.<ext>              reference images uploaded by creators
# plus tmp/ on local disk (DATA_DIR/tmp) for downloads still in progress.


class AssetStore(Protocol):
    def temp_dir(self) -> Path: ...

    async def put(self, job_id: str, name: str, content: bytes | Path, ext: str) -> tuple[str, int]:
        """Store a generated asset; returns (relative path, size in bytes). A Path is moved, not copied."""
        ...

    async def put_input(self, job_id: str, slot: str, content: bytes, ext: str) -> str: ...

    async def put_upload(self, upload_id: str, content: bytes, ext: str) -> str: ...

    def local_path(self, rel_path: str) -> Path:
        """Where the file is on this machine (local store only)."""
        ...

    async def fetch_local(self, rel_path: str, job_id: str) -> Path:
        """A local copy of a stored file for a provider to read; drop it with release_local(job_id)."""
        ...

    async def release_local(self, job_id: str) -> None: ...

    def public_url(
        self, rel_path: str, mime_type: str | None = None, filename: str | None = None
    ) -> str | None:
        """A URL to redirect clients to instead of streaming the bytes; None = serve from local_path."""
        ...

    async def delete_job(self, job_id: str) -> None: ...

    async def delete_inputs(self, job_id: str) -> None: ...

    async def delete_paths(self, rel_paths: list[str]) -> None: ...

    def sweep_temp(self) -> int: ...
