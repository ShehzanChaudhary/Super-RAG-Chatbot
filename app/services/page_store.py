import json
from pathlib import Path

from app.adapters.logger.logger import logger
from app.core.config import settings


class PageStore:
    """Exact page text and image records, read from the files the ingestion notebook wrote.

    The search index only knows chunks (page_start..page_end). This store gives us the
    real text of every single page, so answers can cite the exact page and be verified.
    """

    def __init__(self):
        self._pages: dict[str, dict[int, str]] = {}  # pdf stem -> {page number: text}
        self._images: dict[str, dict] | None = None

    @property
    def _output_dir(self) -> Path:
        return Path(settings.PROJECT_ROOT) / "output"

    def _load_pdf(self, stem: str) -> dict[int, str]:
        if stem not in self._pages:
            path = self._output_dir / "pages" / f"{stem}_pages.jsonl"
            pages = {}
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    rec = json.loads(line)
                    pages[rec["page_number"]] = rec["text"]
            else:
                logger.error(f"Pages file not found: {path}")
            self._pages[stem] = pages
        return self._pages[stem]

    def get_page(self, source_pdf: str, page: int) -> str | None:
        return self._load_pdf(Path(source_pdf).stem).get(page)

    def images(self) -> dict[str, dict]:
        """image_id -> record (source_pdf, page_number, image_path, description)."""
        if self._images is None:
            self._images = {}
            for path in (self._output_dir / "metadata").glob("*_images.jsonl"):
                for line in path.read_text(encoding="utf-8").splitlines():
                    rec = json.loads(line)
                    self._images[rec["image_id"]] = rec
        return self._images

    def image_file(self, image_id: str) -> Path | None:
        rec = self.images().get(image_id)
        return Path(settings.PROJECT_ROOT) / rec["image_path"] if rec else None


page_store = PageStore()