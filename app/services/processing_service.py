import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.file import UploadedFile, FeatureMeasurement, FileStatus, FeatureStatus
from app.services.geospatial_service import GeospatialService, GeospatialProcessingError
from app.services.crs_service import CRSService, CRSError
from app.services.measurement_service import MeasurementService


class ProcessingService:
    """Orchestrator linking geospatial file reading, CRS transformation, feature measurement, and database persistence."""

    @classmethod
    def process_file(cls, file_id: str, db: Session) -> UploadedFile:
        """
        Orchestrate end-to-end file processing:
        1. Read stored geospatial file
        2. Validate and reproject CRS
        3. Calculate feature measurements
        4. Bulk-persist measurement records
        5. Update parent file status and metadata
        """
        file_record = db.query(UploadedFile).filter_by(id=file_id).first()
        if not file_record:
            raise ValueError(f"UploadedFile record with ID '{file_id}' not found.")

        try:
            # 1. Read geospatial vector dataset into normalized GeoDataFrame
            gdf = GeospatialService.read_geospatial_file(file_record.file_path, file_record.file_type)

            # 2. Check and reproject CRS if necessary (raises MissingCRSError if CRS is None)
            crs_result = CRSService.prepare_for_measurement(gdf)

            # 3. Calculate spatial metrics across all features
            measurement_results = MeasurementService.calculate_dataset_measurements(
                crs_result.transformed_gdf
            )

            # 4. Prepare ORM objects in memory for bulk insertion
            orm_measurements = []
            has_warnings = False

            for res in measurement_results:
                if res.status in [FeatureStatus.UNSUPPORTED.value, FeatureStatus.FAILED.value]:
                    has_warnings = True

                source_id = None
                if res.properties_json:
                    try:
                        props_dict = json.loads(res.properties_json)
                        val = props_dict.get("name") or props_dict.get("id") or props_dict.get("zone_id") or props_dict.get("Name")
                        if val is not None:
                            source_id = str(val)
                    except Exception:
                        pass

                m_orm = FeatureMeasurement(
                    file_id=file_record.id,
                    feature_id=res.feature_id,
                    source_id=source_id,
                    geometry_type=res.geometry_type,
                    geometry_geojson=res.geometry_geojson,
                    properties_json=res.properties_json,
                    measurement_type=res.measurement_type,
                    measurement_value=res.measurement_value,
                    measurement_unit=res.measurement_unit,
                    status=res.status,
                    message=res.message,
                )
                orm_measurements.append(m_orm)

            # 5. Bulk insert FeatureMeasurement records
            db.add_all(orm_measurements)

            # 6. Determine final file status
            final_status = (
                FileStatus.COMPLETED_WITH_WARNINGS.value
                if has_warnings
                else FileStatus.COMPLETED.value
            )

            # 7. Update UploadedFile metadata
            file_record.feature_count = len(measurement_results)
            file_record.crs = crs_result.source_crs
            file_record.status = final_status
            file_record.error_message = None
            file_record.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(file_record)
            return file_record

        except (GeospatialProcessingError, CRSError, Exception) as e:
            # Handle fatal file-level failures safely
            db.rollback()

            file_record = db.query(UploadedFile).filter_by(id=file_id).first()
            if file_record:
                file_record.status = FileStatus.FAILED.value
                file_record.error_message = str(e)
                file_record.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(file_record)

            return file_record
