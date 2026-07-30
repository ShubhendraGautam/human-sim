"""Atomic on-disk storage for service-owned resumable checkpoints."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Mapping, Tuple


class CheckpointStore:
    """One latest checkpoint per run, replaced atomically."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        run_id: str,
        checkpoint: Mapping[str, object],
    ) -> None:
        payload = dict(checkpoint)
        payload["service"] = {"run_id": run_id}
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        path = self._path(run_id)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load_all(self) -> List[Tuple[str, Dict[str, object]]]:
        """Read every complete checkpoint in stable path order."""

        restored = []
        for path in sorted(self.directory.glob("*.checkpoint.json")):
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError(f"{path} does not contain an object")
            service = payload.get("service")
            if not isinstance(service, dict):
                raise ValueError(f"{path} has no service metadata")
            run_id = service.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise ValueError(f"{path} has an invalid run id")
            if path != self._path(run_id):
                raise ValueError(f"{path} does not match run {run_id!r}")
            restored.append((run_id, payload))
        return restored

    def delete(self, run_id: str) -> None:
        self._path(run_id).unlink(missing_ok=True)

    def _path(self, run_id: str) -> Path:
        digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.checkpoint.json"
