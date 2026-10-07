import io
import zipfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import geopandas as gpd
from shapely.geometry import Point, Polygon

from app.main import app
from app.core.config import settings
from app.db.database import Base, get_db
from app.models.file import UploadedFile, FileStatus


@pytest.fixture
def test_setup(tmp_path, monkeypatch):
    """Set up isolated test database and test uploads directory for endpoint tests."""
    # 1. Override UPLOAD_DIR to use isolated temp directory
    test_upload_dir = tmp_path / "test_uploads"
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "UPLOAD_DIR", test_upload_dir)

    # 2. Setup isolated in-memory SQLite database with StaticPool so connections share the DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield client, test_upload_dir, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_valid_kml_upload_creates_db_record_and_file(test_setup, tmp_path):
    """Verify uploading a valid .kml file succeeds and completes processing."""
    client, upload_dir, SessionLocal = test_setup

    kml_path = tmp_path / "valid_test.kml"
    gdf = gpd.GeoDataFrame({"name": ["P1"]}, geometry=[Point(12.49, 41.89)], crs="EPSG:4326")
    gdf.to_file(kml_path, driver="KML", engine="pyogrio")
    kml_content = kml_path.read_bytes()

    response = client.post(
        "/api/files/",
        files={"file": ("survey_boundary.kml", kml_content, "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["filename"] == "survey_boundary.kml"
    assert data["file_type"] == "kml"
    assert data["status"] == "COMPLETED"

    file_id = data["id"]
    db = SessionLocal()
    file_record = db.query(UploadedFile).filter_by(id=file_id).first()
    assert file_record is not None
    assert file_record.filename == "survey_boundary.kml"
    assert file_record.file_type == "kml"
    assert file_record.status == FileStatus.COMPLETED.value
    assert Path(file_record.file_path).exists()
    db.close()


def test_valid_zip_shapefile_upload(test_setup, tmp_path):
    """Verify uploading a valid ZIP archive containing Shapefile (.shp, .shx, .dbf) succeeds and completes processing."""
    client, upload_dir, SessionLocal = test_setup

    shp_dir = tmp_path / "test_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "cadastral.shp"

    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])], crs="EPSG:32633")
    gdf.to_file(shp_path, engine="pyogrio")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for ext in [".shp", ".shx", ".dbf", ".prj"]:
            fpath = shp_dir / f"cadastral{ext}"
            if fpath.exists():
                zf.write(fpath, arcname=f"cadastral{ext}")

    zip_bytes = zip_buffer.getvalue()

    response = client.post(
        "/api/files/",
        files={"file": ("cadastral_survey.zip", zip_bytes, "application/zip")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "cadastral_survey.zip"
    assert data["file_type"] == "shapefile"
    assert data["status"] == "COMPLETED"

    file_id = data["id"]
    db = SessionLocal()
    file_record = db.query(UploadedFile).filter_by(id=file_id).first()
    assert file_record is not None
    extracted_dir = Path(file_record.file_path).parent / "extracted"
    assert extracted_dir.exists()
    assert (extracted_dir / "cadastral.shp").exists()
    db.close()


def test_unsupported_file_extension_rejected(test_setup):
    """Verify uploading an unsupported extension (.txt) returns 400 Bad Request."""
    client, _, _ = test_setup

    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"Plain text content", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_empty_file_upload_rejected(test_setup):
    """Verify uploading an empty 0-byte file returns 400 Bad Request."""
    client, _, _ = test_setup

    response = client.post(
        "/api/files/",
        files={"file": ("empty.kml", b"", "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_invalid_corrupt_zip_rejected(test_setup):
    """Verify uploading a corrupt non-ZIP file with .zip extension returns 400 Bad Request."""
    client, _, _ = test_setup

    response = client.post(
        "/api/files/",
        files={"file": ("corrupt.zip", b"Not a zip archive content", "application/zip")},
    )

    assert response.status_code == 400
    assert "corrupt" in response.json()["detail"].lower() or "zip" in response.json()["detail"].lower()


def test_zip_without_shp_rejected(test_setup):
    """Verify uploading a ZIP missing .shp file returns 400 Bad Request."""
    client, _, _ = test_setup

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("readme.txt", b"No shapefile here")

    response = client.post(
        "/api/files/",
        files={"file": ("noshape.zip", zip_buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "does not contain any .shp file" in response.json()["detail"]


def test_zip_path_traversal_rejected(test_setup):
    """Verify uploading a ZIP containing path traversal entries (..) returns 400 Bad Request."""
    client, _, _ = test_setup

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../malicious.txt", b"traversal content")
        zf.writestr("layer.shp", b"shp")
        zf.writestr("layer.shx", b"shx")
        zf.writestr("layer.dbf", b"dbf")

    response = client.post(
        "/api/files/",
        files={"file": ("traversal.zip", zip_buffer.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    assert "Security violation" in response.json()["detail"] or "path traversal" in response.json()["detail"].lower()
