import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.file import UploadedFile, FeatureMeasurement, FileStatus, generate_uuid
from app.schemas.file import (
    FileUploadResponse,
    UploadedFileResponse,
    FileMeasurementsResponse,
    FeatureMeasurementResponse,
    FileStatusEnum,
    FeatureStatusEnum,
)
from app.services.storage_service import StorageService
from app.services.processing_service import ProcessingService

router = APIRouter()


@router.post(
    "/files/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a geospatial file (.kml or .zip Shapefile)",
    description="Accepts a .kml file or a .zip containing a Shapefile, validates, stores, and processes it.",
)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> FileUploadResponse:
    """Thin API route delegating storage and pipeline orchestration to domain services."""
    file_id = generate_uuid()

    # 1. Delegate validation, streaming, and safe disk storage to StorageService
    filename, file_type, stored_path = await StorageService.save_uploaded_file(file, file_id)

    # 2. Persist initial file record with status PROCESSING
    file_record = UploadedFile(
        id=file_id,
        filename=filename,
        file_type=file_type,
        file_path=str(stored_path),
        status=FileStatus.PROCESSING.value,
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    # 3. Trigger synchronous processing pipeline (reading, CRS handling, measurement, DB persistence)
    processed_record = ProcessingService.process_file(file_record.id, db)

    return FileUploadResponse(
        id=processed_record.id,
        filename=processed_record.filename,
        file_type=processed_record.file_type,
        status=FileStatusEnum(processed_record.status),
    )


@router.get(
    "/files/{id}/",
    response_model=UploadedFileResponse,
    summary="Get uploaded file metadata and status",
    description="Returns metadata, feature count, CRS, and processing status for an uploaded file.",
)
def get_file_info(id: str, db: Session = Depends(get_db)) -> UploadedFileResponse:
    """Retrieve metadata information for a specific uploaded file."""
    file_record = db.query(UploadedFile).filter_by(id=id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Uploaded file with ID '{id}' not found.",
        )
    return UploadedFileResponse.model_validate(file_record)


@router.get(
    "/files/{id}/measurements/",
    response_model=FileMeasurementsResponse,
    summary="Get calculated measurements for features in an uploaded file",
    description="Returns spatial measurement results (area, length) for all features in the file.",
)
def get_file_measurements(id: str, db: Session = Depends(get_db)) -> FileMeasurementsResponse:
    """Retrieve persistent measurement records for features in a specific uploaded file."""
    file_record = db.query(UploadedFile).filter_by(id=id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Uploaded file with ID '{id}' not found.",
        )

    measurements = (
        db.query(FeatureMeasurement)
        .filter_by(file_id=id)
        .order_by(FeatureMeasurement.feature_id.asc())
        .all()
    )

    measurement_responses = []
    for m in measurements:
        geom_dict = json.loads(m.geometry_geojson) if m.geometry_geojson else None
        props_dict = json.loads(m.properties_json) if m.properties_json else None

        m_resp = FeatureMeasurementResponse(
            id=m.id,
            feature_id=m.feature_id,
            source_id=m.source_id,
            geometry_type=m.geometry_type,
            geometry=geom_dict,
            properties=props_dict,
            measurement_type=m.measurement_type,
            measurement_value=m.measurement_value,
            measurement_unit=m.measurement_unit,
            status=FeatureStatusEnum(m.status),
            message=m.message,
        )
        measurement_responses.append(m_resp)

    return FileMeasurementsResponse(
        file_id=file_record.id,
        filename=file_record.filename,
        status=FileStatusEnum(file_record.status),
        crs=file_record.crs,
        total_features=len(measurement_responses),
        measurements=measurement_responses,
    )
