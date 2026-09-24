"""Persistenza applicativa locale SQLite e blob content-addressed."""

from ntruth.storage.blobs import (
    BlobIntegrityError,
    BlobRecord,
    BlobStore,
    BlobStoreError,
    BlobWriteResult,
    InvalidDigest,
    hash_file,
)
from ntruth.storage.database import (
    AuditEventRecord,
    PlanExecutionStorageRecord,
    RevisionRecord,
    StorageDatabase,
    StorageIntegrityError,
)
from ntruth.storage.migrations import (
    MIGRATIONS,
    Migration,
    StorageMigrationError,
    apply_migrations,
)

__all__ = [
    "MIGRATIONS",
    "AuditEventRecord",
    "BlobIntegrityError",
    "BlobRecord",
    "BlobStore",
    "BlobStoreError",
    "BlobWriteResult",
    "InvalidDigest",
    "Migration",
    "PlanExecutionStorageRecord",
    "RevisionRecord",
    "StorageDatabase",
    "StorageIntegrityError",
    "StorageMigrationError",
    "apply_migrations",
    "hash_file",
]
