import io
import zipfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon

from app.main import app
from app.core.config import settings
from app.db.database import Base, get_db
from app.models.file import UploadedFile, FeatureMeasurement, FileStatus, FeatureStatus


@pytest.fixture
def integration_client(tmp_path, monkeypatch):
    """Set up isolated test database and test uploads directory for end-to-end integration tests."""
    test_upload_dir = tmp_path / "integration_uploads"
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "UPLOAD_DIR", test_upload_dir)

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

    yield client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_e2e_kml_upload_processing_and_get_endpoints(integration_client, tmp_path):
    """Verify uploading a valid EPSG:4326 KML processes automatically and populates GET endpoints."""
    client, SessionLocal = integration_client

    # Create real KML dataset with Point, LineString, and Polygon
    kml_file = tmp_path / "survey_city.kml"
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Rome Point", "Rome Street", "Rome Park"],
            "description": ["Center", "Via Appia", "Villa Borghese"],
        },
        geometry=[
            Point(12.4924, 41.8902),
            LineString([(12.4924, 41.8902), (12.4930, 41.8910)]),
            Polygon([(12.4920, 41.8900), (12.4940, 41.8900), (12.4940, 41.8920), (12.4920, 41.8920), (12.4920, 41.8900)]),
        ],
        crs="EPSG:4326",
    )
    gdf.to_file(kml_file, driver="KML", engine="pyogrio")
    kml_bytes = kml_file.read_bytes()

    # 1. POST /api/files/
    upload_resp = client.post(
        "/api/files/",
        files={"file": ("survey_city.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "COMPLETED"

    # 2. GET /api/files/{id}/
    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["id"] == file_id
    assert info_data["filename"] == "survey_city.kml"
    assert info_data["feature_count"] == 3
    assert "4326" in info_data["crs"]
    assert info_data["status"] == "COMPLETED"

    # 3. GET /api/files/{id}/measurements/
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["file_id"] == file_id
    assert meas_data["total_features"] == 3
    assert len(meas_data["measurements"]) == 3

    m0 = meas_data["measurements"][0]
    assert m0["geometry_type"] == "Point"
    assert m0["status"] == "NOT_REQUIRED"
    assert m0["measurement_value"] is None

    m1 = meas_data["measurements"][1]
    assert m1["geometry_type"] == "LineString"
    assert m1["measurement_type"] == "length"
    assert m1["measurement_unit"] == "meters"
    assert m1["measurement_value"] > 0
    assert m1["status"] == "MEASURED"

    m2 = meas_data["measurements"][2]
    assert m2["geometry_type"] == "Polygon"
    assert m2["measurement_type"] == "area"
    assert m2["measurement_unit"] == "sq_m"
    assert m2["measurement_value"] > 0
    assert m2["status"] == "MEASURED"


def test_e2e_shapefile_zip_upload_and_measurement(integration_client, tmp_path):
    """Verify uploading a projected Shapefile ZIP archive calculates correct metric measurements."""
    client, _ = integration_client

    # Create real projected Shapefile (EPSG:32633 UTM 33N)
    shp_dir = tmp_path / "cadastral_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "plots.shp"

    gdf = gpd.GeoDataFrame(
        {"plot_name": ["Plot 101"]},
        geometry=[Polygon([(500000, 4000000), (500010, 4000000), (500010, 4000010), (500000, 4000010), (500000, 4000000)])],
        crs="EPSG:32633",
    )
    gdf.to_file(shp_path, engine="pyogrio")

    # Zip shapefile components
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for ext in [".shp", ".shx", ".dbf", ".prj"]:
            fpath = shp_dir / f"plots{ext}"
            if fpath.exists():
                zf.write(fpath, arcname=f"plots{ext}")

    upload_resp = client.post(
        "/api/files/",
        files={"file": ("plots.zip", zip_buffer.getvalue(), "application/zip")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    m_data = meas_resp.json()
    assert m_data["total_features"] == 1
    poly_m = m_data["measurements"][0]
    assert poly_m["geometry_type"] == "Polygon"
    assert poly_m["measurement_type"] == "area"
    assert poly_m["measurement_value"] == 100.0  # 10m x 10m = 100 sq_m
    assert poly_m["measurement_unit"] == "sq_m"


def test_partial_feature_failure_results_in_completed_with_warnings(integration_client, tmp_path):
    """Verify dataset containing one invalid geometry finishes with COMPLETED_WITH_WARNINGS status."""
    client, _ = integration_client

    kml_file = tmp_path / "warning_dataset.kml"
    valid_poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    invalid_poly = Polygon([(0, 0), (0, 10), (10, 0), (10, 10), (0, 0)])  # Self-intersecting

    gdf = gpd.GeoDataFrame(
        {"name": ["Valid Square", "Invalid Bowtie"]},
        geometry=[valid_poly, invalid_poly],
        crs="EPSG:32633",
    )
    gdf.to_file(kml_file, driver="KML", engine="pyogrio")

    upload_resp = client.post(
        "/api/files/",
        files={"file": ("warning_dataset.kml", kml_file.read_bytes(), "application/vnd.google-earth.kml+xml")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "COMPLETED_WITH_WARNINGS"

    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.json()["status"] == "COMPLETED_WITH_WARNINGS"

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    meas_list = meas_resp.json()["measurements"]
    assert len(meas_list) == 2
    assert meas_list[0]["status"] == "MEASURED"
    assert meas_list[1]["status"] == "FAILED"
    assert "invalid" in meas_list[1]["message"].lower()


def test_missing_crs_causes_file_status_failed(integration_client, tmp_path):
    """Verify a Shapefile missing a CRS fails processing with status FAILED."""
    client, _ = integration_client

    shp_dir = tmp_path / "no_crs_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "nocrs.shp"

    gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(10, 20)], crs=None)
    gdf.to_file(shp_path, engine="pyogrio")

    # Zip without .prj
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for ext in [".shp", ".shx", ".dbf"]:
            fpath = shp_dir / f"nocrs{ext}"
            if fpath.exists():
                zf.write(fpath, arcname=f"nocrs{ext}")

    upload_resp = client.post(
        "/api/files/",
        files={"file": ("nocrs.zip", zip_buffer.getvalue(), "application/zip")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.json()["status"] == "FAILED"
    assert "no defined Coordinate Reference System" in info_resp.json()["error_message"]


def test_unknown_file_id_returns_404(integration_client):
    """Verify requesting an unknown file ID returns 404 Not Found."""
    client, _ = integration_client

    resp_info = client.get("/api/files/nonexistent_id_999/")
    assert resp_info.status_code == 404

    resp_meas = client.get("/api/files/nonexistent_id_999/measurements/")
    assert resp_meas.status_code == 404


def test_repeated_duplicate_uploads_isolated(integration_client, tmp_path):
    """Verify uploading the identical file repeatedly creates distinct records and storage paths."""
    client, SessionLocal = integration_client

    kml_file = tmp_path / "repeated.kml"
    gdf = gpd.GeoDataFrame(
        {"name": ["Station A"]},
        geometry=[Point(12.4924, 41.8902)],
        crs="EPSG:4326",
    )
    gdf.to_file(kml_file, driver="KML", engine="pyogrio")
    kml_bytes = kml_file.read_bytes()

    resp1 = client.post(
        "/api/files/",
        files={"file": ("repeated.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    resp2 = client.post(
        "/api/files/",
        files={"file": ("repeated.kml", kml_bytes, "application/vnd.google-earth.kml+xml")},
    )

    assert resp1.status_code == 201
    assert resp2.status_code == 201

    id1 = resp1.json()["id"]
    id2 = resp2.json()["id"]
    assert id1 != id2

    db = SessionLocal()
    rec1 = db.query(UploadedFile).filter_by(id=id1).first()
    rec2 = db.query(UploadedFile).filter_by(id=id2).first()
    assert rec1 is not None and rec2 is not None
    assert rec1.file_path != rec2.file_path
    db.close()


def test_large_feature_dataset_processing(integration_client, tmp_path):
    """Verify dataset with a large number of features (e.g. 50 polygons) processes correctly."""
    client, _ = integration_client

    # Generate 50 distinct square polygons
    polygons = []
    names = []
    for i in range(50):
        x = i * 20.0
        poly = Polygon([(x, 0), (x + 10, 0), (x + 10, 10), (x, 10), (x, 0)])
        polygons.append(poly)
        names.append(f"Parcel {i}")

    gdf = gpd.GeoDataFrame({"name": names}, geometry=polygons, crs="EPSG:32633")
    shp_dir = tmp_path / "large_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "parcels.shp"
    gdf.to_file(shp_path, engine="pyogrio")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for ext in [".shp", ".shx", ".dbf", ".prj"]:
            fpath = shp_dir / f"parcels{ext}"
            if fpath.exists():
                zf.write(fpath, arcname=f"parcels{ext}")

    upload_resp = client.post(
        "/api/files/",
        files={"file": ("parcels.zip", zip_buffer.getvalue(), "application/zip")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    m_data = meas_resp.json()
    assert m_data["total_features"] == 50
    assert len(m_data["measurements"]) == 50
    for m in m_data["measurements"]:
        assert m["status"] == "MEASURED"
        assert m["measurement_type"] == "area"
        assert m["measurement_value"] == 100.0


def test_malformed_kml_upload_marks_file_failed(integration_client):
    """Verify uploading a malformed/corrupt KML sets file status to FAILED and records error message."""
    client, _ = integration_client

    corrupt_kml_bytes = b"<?xml version='1.0'?><kml><corrupted_unclosed_tag>"

    upload_resp = client.post(
        "/api/files/",
        files={"file": ("broken.kml", corrupt_kml_bytes, "application/vnd.google-earth.kml+xml")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["status"] == "FAILED"
    assert info_data["error_message"] is not None

