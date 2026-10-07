from enum import Enum
from datetime import datetime, timezone
import uuid
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class FileStatus(str, Enum):
    """Lifecycle statuses for uploaded geospatial files."""
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class FeatureStatus(str, Enum):
    """Processing and measurement status per feature."""
    MEASURED = "MEASURED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class FileType(str, Enum):
    """Supported file formats."""
    KML = "kml"
    SHAPEFILE = "shapefile"


def generate_uuid() -> str:
    """Generate a unique hex string identifier."""
    return uuid.uuid4().hex[:12]


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class UploadedFile(Base):
    """Database model representing an uploaded geospatial file."""

    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crs: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=FileStatus.PROCESSING.value
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    # One-to-many relationship: One UploadedFile -> many FeatureMeasurements
    measurements: Mapped[List["FeatureMeasurement"]] = relationship(
        "FeatureMeasurement",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UploadedFile(id={self.id!r}, filename={self.filename!r}, status={self.status!r})>"


class FeatureMeasurement(Base):
    """Database model storing extracted feature geometry and measurement results."""

    __tablename__ = "feature_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    geometry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    properties_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    measurement_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    measurement_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measurement_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=FeatureStatus.MEASURED.value
    )
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship back to parent UploadedFile
    file: Mapped["UploadedFile"] = relationship("UploadedFile", back_populates="measurements")

    def __repr__(self) -> str:
        return (
            f"<FeatureMeasurement(id={self.id}, file_id={self.file_id!r}, "
            f"feature_id={self.feature_id}, geom_type={self.geometry_type!r}, status={self.status!r})>"
        )
