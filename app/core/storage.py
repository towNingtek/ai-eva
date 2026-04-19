"""
Local filesystem storage client for Chainlit's SQLAlchemyDataLayer.

Without a storage_provider, Chainlit 2.x silently fails element persistence
and reload can't re-render the thread → input box disappears.
This minimal provider writes blobs to a mounted dir and serves them via
Chainlit's /public/ static route.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from chainlit.data.storage_clients.base import BaseStorageClient

logger = logging.getLogger(__name__)


class LocalStorageClient(BaseStorageClient):
    def __init__(self, root_dir: str | Path, public_url_prefix: str = "/public/elements"):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.url_prefix = public_url_prefix.rstrip("/")

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = self.root / object_key
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not overwrite:
            raise FileExistsError(object_key)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8")
        else:
            p.write_bytes(data)
        return {"object_key": object_key, "url": f"{self.url_prefix}/{object_key}"}

    async def delete_file(self, object_key: str) -> bool:
        p = self.root / object_key
        if p.exists():
            p.unlink()
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"{self.url_prefix}/{object_key}"

    async def close(self) -> None:
        pass
