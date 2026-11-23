import asyncio
import os
import shutil
import uuid
from pathlib import Path


class LocalAssetStore:
    """Files under one root:
    assets/<job_id>/<attempt>-<idx>.<ext>  generated outputs (per attempt, so a fenced-out attempt
                                          can delete its own files without touching the new owner's)
    inputs/<job_id>/<slot>.<ext>   images uploaded with a template call
    uploads/<upload_id>.<ext>      reference images uploaded by creators
    tmp/                           partial downloads, same filesystem so os.replace is atomic
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        for sub in ("assets", "inputs", "uploads", "tmp"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def temp_dir(self) -> Path:
        return self.root / "tmp"

    def _write(self, rel: str, content: bytes | Path) -> int:
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.part")
        if isinstance(content, Path):
            shutil.move(content, part)
        else:
            part.write_bytes(content)
        os.replace(part, dest)
        return dest.stat().st_size

    async def put(self, job_id: str, name: str, content: bytes | Path, ext: str) -> tuple[str, int]:
        rel = f"assets/{job_id}/{name}.{ext}"
        size = await asyncio.to_thread(self._write, rel, content)
        return rel, size

    async def put_input(self, job_id: str, slot: str, content: bytes, ext: str) -> str:
        rel = f"inputs/{job_id}/{slot}.{ext}"
        await asyncio.to_thread(self._write, rel, content)
        return rel

    async def put_upload(self, upload_id: str, content: bytes, ext: str) -> str:
        rel = f"uploads/{upload_id}.{ext}"
        await asyncio.to_thread(self._write, rel, content)
        return rel

    def local_path(self, rel_path: str) -> Path:
        path = (self.root / rel_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("path escapes the store root")
        return path

    def public_url(self, rel_path: str) -> str | None:
        return None

    async def delete_job(self, job_id: str) -> None:
        for sub in ("assets", "inputs"):
            await asyncio.to_thread(shutil.rmtree, self.root / sub / job_id, True)

    async def delete_paths(self, rel_paths: list[str]) -> None:
        for rel in rel_paths:
            await asyncio.to_thread(self.local_path(rel).unlink, True)

    async def delete_inputs(self, job_id: str) -> None:
        await asyncio.to_thread(shutil.rmtree, self.root / "inputs" / job_id, True)

    def sweep_temp(self) -> int:
        removed = 0
        for p in self.temp_dir().iterdir():
            p.unlink(missing_ok=True) if p.is_file() else shutil.rmtree(p, True)
            removed += 1
        for part in self.root.glob("*/**/*.part"):
            part.unlink(missing_ok=True)
            removed += 1
        return removed
