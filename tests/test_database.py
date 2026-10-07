import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.db.database import Base, get_db
from app.models.file import UploadedFile, FeatureMeasurement, FileStatus, FeatureStatus, FileType


@pytest.fixture
def db_session():
    """Fixture providing an isolated in-memory SQLite database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_database_initializes_successfully(db_session):
    """Verify that tables are created and session query succeeds."""
    files_count = db_session.query(UploadedFile).count()
    measurements_count = db_session.query(FeatureMeasurement).count()
    assert files_count == 0
    assert measurements_count == 0


def test_create_uploaded_file(db_session):
    """Verify UploadedFile creation and persistence."""
    file_record = UploadedFile(
        filename="test_map.kml",
        file_type=FileType.KML.value,
        file_path="/uploads/test_map.kml",
        crs="EPSG:4326",
        status=FileStatus.PROCESSING.value,
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    assert file_record.id is not None
    assert len(file_record.id) > 0
    assert file_record.filename == "test_map.kml"
    assert file_record.status == FileStatus.PROCESSING.value
    assert file_record.created_at is not None


def test_create_feature_measurement(db_session):
    """Verify FeatureMeasurement creation and direct foreign key linkage."""
    file_record = UploadedFile(
        filename="survey.zip",
        file_type=FileType.SHAPEFILE.value,
        file_path="/uploads/survey.zip",
        crs="EPSG:32644",
        status=FileStatus.COMPLETED.value,
    )
    db_session.add(file_record)
    db_session.commit()

    measurement = FeatureMeasurement(
        file_id=file_record.id,
        feature_id=0,
        source_id="poly_101",
        geometry_type="Polygon",
        geometry_geojson='{"type": "Polygon", "coordinates": []}',
        properties_json='{"name": "Zone A"}',
        measurement_type="area",
        measurement_value=1250.75,
        measurement_unit="sq_m",
        status=FeatureStatus.MEASURED.value,
    )
    db_session.add(measurement)
    db_session.commit()
    db_session.refresh(measurement)

    assert measurement.id is not None
    assert measurement.file_id == file_record.id
    assert measurement.measurement_value == 1250.75
    assert measurement.status == FeatureStatus.MEASURED.value


def test_uploaded_file_relationship(db_session):
    """Verify the one-to-many relationship from UploadedFile to FeatureMeasurement."""
    file_record = UploadedFile(
        filename="boundaries.kml",
        file_type=FileType.KML.value,
        file_path="/uploads/boundaries.kml",
        feature_count=2,
        crs="EPSG:4326",
        status=FileStatus.COMPLETED.value,
    )

    m1 = FeatureMeasurement(
        feature_id=0,
        geometry_type="Polygon",
        measurement_type="area",
        measurement_value=500.0,
        measurement_unit="sq_m",
        status=FeatureStatus.MEASURED.value,
    )
    m2 = FeatureMeasurement(
        feature_id=1,
        geometry_type="LineString",
        measurement_type="length",
        measurement_value=120.5,
        measurement_unit="meters",
        status=FeatureStatus.MEASURED.value,
    )

    file_record.measurements.extend([m1, m2])
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    assert len(file_record.measurements) == 2
    assert file_record.measurements[0].geometry_type == "Polygon"
    assert file_record.measurements[1].geometry_type == "LineString"
    assert m1.file.filename == "boundaries.kml"


def test_parent_deletion_cascades_to_measurements(db_session):
    """Verify that deleting an UploadedFile cascades to delete associated FeatureMeasurements."""
    file_record = UploadedFile(
        filename="cascade_test.kml",
        file_type=FileType.KML.value,
        file_path="/uploads/cascade_test.kml",
        status=FileStatus.COMPLETED.value,
    )
    m1 = FeatureMeasurement(
        feature_id=0,
        geometry_type="Point",
        status=FeatureStatus.NOT_REQUIRED.value,
    )
    file_record.measurements.append(m1)
    db_session.add(file_record)
    db_session.commit()

    file_id = file_record.id
    assert db_session.query(FeatureMeasurement).filter_by(file_id=file_id).count() == 1

    # Delete parent
    db_session.delete(file_record)
    db_session.commit()

    # Child measurements should be automatically deleted
    assert db_session.query(FeatureMeasurement).filter_by(file_id=file_id).count() == 0


def test_get_db_session_lifecycle():
    """Verify get_db dependency yields a valid session and closes cleanly."""
    gen = get_db()
    db = next(gen)
    assert db.is_active
    try:
        next(gen)
    except StopIteration:
        pass
    # After generator closes, db session resources are cleaned up
