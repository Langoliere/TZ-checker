import re
from pathlib import Path
from uuid import UUID

from tz_checker.config import get_settings


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().storage_path
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, document_id: UUID, filename: str, content: bytes, prefix: str = "documents") -> str:
        # basename и белый список символов исключают внедрение пути через имя файла.
        safe_name = re.sub(r"[^A-Za-zА-Яа-я0-9_.-]", "_", Path(filename).name)
        key = f"{prefix}/{document_id}/{safe_name}"
        path = (self.root / key).resolve()
        # Проверяем итоговый абсолютный путь, а не только исходную строку ключа.
        if self.root.resolve() not in path.parents:
            raise ValueError("Unsafe storage path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return key

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Проверяем итоговый абсолютный путь, а не только исходную строку ключа.
        if self.root.resolve() not in path.parents:
            raise ValueError("Unsafe storage key")
        return path
