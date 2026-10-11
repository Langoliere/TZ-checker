from uuid import UUID

from celery import Celery

from tz_checker.config import get_settings
from tz_checker.models.db import Document
from tz_checker.repositories.database import SessionLocal
from tz_checker.repositories.storage import LocalStorage
from tz_checker.services.processing import process_document

settings = get_settings()
celery_app = Celery("tz_checker", broker=settings.redis_url, backend=settings.redis_url)
# Позднее подтверждение и единичный prefetch не теряют долгую задачу при остановке worker.
celery_app.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)


# Повторяем только инфраструктурные сбои соединения; ошибки документа должны стать failed.
@celery_app.task(bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def process_document_task(self, document_id: str) -> None:
    with SessionLocal() as session:
        document = session.get(Document, UUID(document_id))
        if document is None:
            return
        process_document(session, document.id, LocalStorage().path(document.storage_key))
