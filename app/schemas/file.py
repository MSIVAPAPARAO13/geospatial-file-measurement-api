from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, ConfigDict


class FileStatusEnum(str, Enum):
    """Pydantic status enum for file processing state."""
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class FeatureStatusEnum(str, Enum):
    """Pydantic status enum for feature measurement state."""
    MEASURED = "MEASURED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class FileUploadResponse(BaseModel):
    """API response schema returned immediately upon uploading a file (POST /api/files/)."""

    id: str
    filename: str
    file_type: str
    status: FileStatusEnum

    model_config = ConfigDict(from_attributes=True)


class UploadedFileResponse(BaseModel):
    """API response schema for uploaded file metadata (GET /api/files/{id}/)."""

    id: str
    filename: str
    file_type: str
    feature_count: Optional[int] = None
    crs: Optional[str] = None
    status: FileStatusEnum
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeatureMeasurementResponse(BaseModel):
    """API response schema for an individual feature measurement."""

    id: int
    feature_id: int
    source_id: Optional[str] = None
    geometry_type: str
    geometry: Optional[Dict[str, Any]] = Field(
        default=None, description="GeoJSON geometry object"
    )
    properties: Optional[Dict[str, Any]] = Field(
        default=None, description="Feature attributes dictionary"
    )
    measurement_type: Optional[str] = Field(
        default=None, description="Type of measurement e.g. area, length"
    )
    measurement_value: Optional[float] = Field(
        default=None, description="Numerical value of calculated measurement"
    )
    measurement_unit: Optional[str] = Field(
        default=None, description="Unit of measurement e.g. sq_m, meters"
    )
    status: FeatureStatusEnum
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FileMeasurementsResponse(BaseModel):
    """API response schema for file measurement list (GET /api/files/{id}/measurements/)."""

    file_id: str
    filename: str
    status: FileStatusEnum
    crs: Optional[str] = None
    total_features: int
    measurements: List[FeatureMeasurementResponse]

    model_config = ConfigDict(from_attributes=True)
