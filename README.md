# Geospatial File Measurement API

A robust, production-ready FastAPI service designed to ingest, validate, project, and calculate spatial metrics (polygon area, line length) from vector geospatial files (.kml and Shapefile .zip archives).

---

## 1. Problem Statement

Geospatial data formats such as Shapefiles and KML files are widely used in urban planning, logistics, civil surveying, and environmental monitoring. However, raw uploaded spatial files present several architectural and domain hurdles:
- Incompatible geometry representations across heterogeneous file formats.
- Data provided in unprojected angular coordinate reference systems (latitude/longitude in degrees, e.g., WGS 84 / EPSG:4326), where naive planar Euclidean measurements yield scientifically meaningless numbers (degrees² or degrees instead of square meters or meters).
- Security risks from malicious archive files (Zip Slip attacks, path traversal, decompression bombs).
- Partial data corruption where one malformed feature crashes an entire dataset ingestion.

The goal of this project is to provide a clean, self-contained REST API that securely ingests geospatial files, validates their Coordinate Reference System (CRS), computes accurate metric measurements in projected coordinate space, and exposes queryable file and measurement endpoints.

---

## 2. Why the Project Exists

This backend service exists to solve three core problems:
1. **Format Normalization**: Ingest both Google Earth KML files and ESRI Shapefiles (packaged as ZIP archives) into a unified internal representation.
2. **Metric Integrity**: Ensure spatial measurements are calculated strictly in metric units (square meters for polygons, meters for lines) by detecting geographic coordinates and dynamically projecting them to local Universal Transverse Mercator (UTM) zones.
3. **Resilience & Fault Isolation**: Ensure that individual geometry defects (self-intersecting polygons, invalid topologies, unsupported geometries) are handled gracefully at the feature level without aborting the entire dataset ingestion.

---

## 3. Key Features

- **Dual Format Support**: Ingest `.kml` and `.zip` Shapefile archives.
- **Strict Archive Security**: Comprehensive Zip Slip prevention, path traversal rejection, absolute path blocking, and validation of required Shapefile companion files (`.shp`, `.shx`, `.dbf`).
- **Safe Streaming & Size Limits**: Configurable file size guard (default 50 MB) with chunked disk streaming and automatic garbage collection on failed uploads.
- **Defensive CRS Strategy**: Automatic inspection of source CRS. Datasets in geographic coordinates (`EPSG:4326`) are reprojected using centroid-based UTM zone estimation. Missing CRS is never guessed and triggers clean failure.
- **Granular Feature Measurements**:
  - `Polygon` / `MultiPolygon`: Area computed in square meters (`sq_m`).
  - `LineString` / `MultiLineString`: Length computed in meters (`meters`).
  - `Point` / `MultiPoint`: Marked as `NOT_REQUIRED` with null measurements.
  - Unsupported types (e.g., `GeometryCollection`): Isolated as `UNSUPPORTED`.
  - Topology errors: Isolated as `FAILED` with descriptive diagnostic messages.
- **Status Lifecycle Tracking**: Datasets transition through `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, or `FAILED`.
- **Relational Persistence**: SQLAlchemy 2.x relational schema linking file metadata to granular per-feature measurements with cascading delete.
- **RESTful Endpoints**: Dedicated endpoints for file upload, file metadata inspection, and measurement retrieval.
- **Self-Documenting API**: Interactive OpenAPI Swagger documentation available at `/docs`.

---

## 4. Tech Stack

- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) (0.110+)
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/)
- **Configuration & Validation**: [Pydantic v2](https://docs.pydantic.dev/) & [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Database & ORM**: [SQLAlchemy 2.x](https://www.sqlalchemy.org/) with SQLite (local development)
- **Geospatial Processing Engine**:
  - [GeoPandas](https://geopandas.org/): Vector dataset management and CRS handling
  - [Shapely](https://shapely.readthedocs.io/): Planar geometry analysis and spatial calculations
  - [PyProj](https://pyproj4.github.io/pyproj/): Coordinate Reference System projection and UTM zone estimation
  - [PyOgrio](https://pyogrio.readthedocs.io/): High-performance GDAL vector file I/O
- **Testing**: [pytest](https://docs.pytest.org/) and [HTTPX](https://www.python-httpx.org/) TestClient

---

## 5. Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                  CLIENT (HTTP)                                    |
+-----------------------------------------------------------------------------------+
           | POST /api/files/               | GET /api/files/{id}/        | GET .../measurements/
           v                                v                             v
+-----------------------------------------------------------------------------------+
|                            FASTAPI ROUTER LAYER                                   |
|                          (app/api/v1/endpoints/files.py)                          |
+-----------------------------------------------------------------------------------+
           |                                |                             |
           v                                |                             |
+----------------------+                    |                             |
|    STORAGE SERVICE   |                    |                             |
| - Sanitize filename  |                    |                             |
| - 50MB Stream guard  |                    |                             |
| - ZIP Slip & Traversal|                   |                             |
| - Validate .shp/.shx |                    |                             |
+----------------------+                    |                             |
           |                                |                             |
           v                                |                             |
+----------------------------------------------------+                    |
|                PROCESSING SERVICE                  |                    |
|        (Pipeline Coordinator / Orchestrator)       |                    |
+----------------------------------------------------+                    |
    |                   |                   |                             |
    v                   v                   v                             |
+---------------+ +---------------+ +------------------+                  |
|  GEOSPATIAL   | |  CRS SERVICE  | |   MEASUREMENT    |                  |
|    SERVICE    | | - Missing CRS | |     SERVICE      |                  |
| - KML Parser  | |   Rejection   | | - Polygon Area   |                  |
| - SHP Parser  | | - UTM Auto-   | | - Line Length    |                  |
| - Normalize to| |   Projection  | | - Point Ignore   |                  |
|   GeoDataFrame| | - Metric Units| | - Fault Barrier  |                  |
+---------------+ +---------------+ +------------------+                  |
    |                   |                   |                             |
    +-------------------+-------------------+                             |
                        |                                                 |
                        v                                                 v
+-----------------------------------------------------------------------------------+
|                              DATABASE ORM LAYER                                   |
|                             (SQLAlchemy 2.x / SQLite)                             |
|                                                                                   |
|  +--------------------+                   +----------------------------------+    |
|  |   UploadedFile     | 1 ------------- * |       FeatureMeasurement         |    |
|  | (id, status, crs)  |  (CASCADE DELETE) | (feature_id, geom_type, val, msg)|    |
|  +--------------------+                   +----------------------------------+    |
+-----------------------------------------------------------------------------------+
```

---

## 6. Project Structure

```
geospatial-file-measurement-api/
├── .env.example                     # Environment template for local deployment
├── .gitignore                       # Git exclusion rules (.env, *.db, uploads/, venv/)
├── README.md                        # Production documentation and project guide
├── requirements.txt                 # Pinned dependencies
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI application bootstrap & lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py            # Aggregated v1 API routing
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           └── files.py         # POST upload & GET retrieval route handlers
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py                # Pydantic Settings centralized configuration
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py              # SQLite engine, SessionLocal, Base, foreign key pragma
│   ├── models/
│   │   ├── __init__.py
│   │   └── file.py                  # SQLAlchemy ORM models: UploadedFile & FeatureMeasurement
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── file.py                  # Pydantic serialization & request/response schemas
│   └── services/
│       ├── __init__.py
│       ├── crs_service.py           # CRS detection, validation & UTM reprojection
│       ├── geospatial_service.py    # Vector file reading & GeoDataFrame normalization
│       ├── measurement_service.py   # Spatial metric calculation engine & fault barrier
│       ├── processing_service.py    # Pipeline coordinator & database persistence
│       └── storage_service.py       # Secure streaming upload & Zip Slip protection
└── tests/
    ├── __init__.py
    ├── test_crs_service.py          # Unit tests for CRS validation and reprojection
    ├── test_database.py             # Database models, relationships, cascading deletion
    ├── test_geospatial_reader.py    # KML & Shapefile ingestion, driver checks, corrupt files
    ├── test_health.py               # Application healthcheck endpoint verification
    ├── test_integration.py         # End-to-end API workflows, edge cases, 404s, batch tests
    ├── test_measurement_service.py  # Unit tests for area, length, points, invalid topologies
    └── test_upload.py               # Security tests: Zip Slip, traversal, extensions, size limits
```

---

## 7. Complete File-Processing Flow

When a user submits a geospatial file, the following pipeline executes:

1. **Ingest & Sanitize (`StorageService`)**:
   - The file extension is checked against `.kml` and `.zip`.
   - The file is streamed in 1 MB chunks to disk up to `MAX_FILE_SIZE_BYTES` (50 MB).
   - If `.zip`, all member filenames are evaluated for Zip Slip (`..`, absolute paths, drive letters).
   - Archive is verified to contain a `.shp` file and corresponding `.shx` and `.dbf` companion files.
   - Archive contents are extracted into an isolated UUID-scoped directory.

2. **Persistence Initiation (`ProcessingService`)**:
   - An `UploadedFile` record is written to SQLite with `status = "PROCESSING"`.

3. **Geospatial Normalization (`GeospatialService`)**:
   - Vector data is read into a normalized GeoPandas `GeoDataFrame` using `pyogrio`.
   - Non-geometry columns and attribute tables are preserved.

4. **CRS Verification & Reprojection (`CRSService`)**:
   - Source CRS is inspected.
   - If missing (`crs is None`), processing halts; file status is marked `FAILED` with an explicit diagnostic message.
   - If projected (e.g., UTM or state plane), geometries remain untouched.
   - If geographic (e.g., `EPSG:4326`), the dataset's centroid is used to calculate the appropriate UTM projection zone via `estimate_utm_crs()`, and all geometries are reprojected into meters.

5. **Measurement Calculation (`MeasurementService`)**:
   - Each feature geometry is examined independently:
     - `Polygon` / `MultiPolygon`: `geom.area` -> `measurement_type = "area"`, `unit = "sq_m"`.
     - `LineString` / `MultiLineString`: `geom.length` -> `measurement_type = "length"`, `unit = "meters"`.
     - `Point` / `MultiPoint`: `status = "NOT_REQUIRED"`, values set to `None`.
     - `GeometryCollection` / other: `status = "UNSUPPORTED"`.
     - Malformed / invalid geometries: `status = "FAILED"`, error recorded, pipeline continues.

6. **Persistence & Status Finalization (`ProcessingService`)**:
   - Feature measurements are bulk-saved into `feature_measurements`.
   - If any feature failed or was unsupported, the file status becomes `COMPLETED_WITH_WARNINGS`.
   - If all features succeeded, the file status becomes `COMPLETED`.
   - If a file-level error occurred (e.g., missing CRS, corrupt file), the transaction rolls back, and status becomes `FAILED`.

---

## 8. CRS Handling Strategy

Accurate spatial measurement requires working in a metric Cartesian coordinate space:

- **Missing CRS Rejection**: If an uploaded dataset does not specify a coordinate system (e.g., a Shapefile missing a `.prj` file), the API **never guesses** EPSG:4326. Guessing coordinates can lead to severe spatial distortion or incorrect measurements. Instead, a `MissingCRSError` is raised, setting the file status to `FAILED`.
- **Existing Projected CRS**: If a dataset is already projected (such as `EPSG:32644` or `EPSG:3857`), the coordinate system and units are preserved.
- **Geographic CRS Reprojection**: For geographic coordinate systems expressed in angular degrees (such as WGS 84 / `EPSG:4326`), calculating planar area or length directly produces distorted, unitless numbers (`degrees` or `degrees²`). The service calculates the bounding center of the dataset and reprojects the geometries into the corresponding local Universal Transverse Mercator (UTM) zone (e.g., `WGS 84 / UTM Zone 44N / EPSG:32644` for the Hyderabad region).
- **Separation of Concerns**: The source CRS is stored on the `UploadedFile` record, ensuring clients know the original datum of the uploaded data.

---

## 9. Measurement Logic

Measurement calculations are governed by strict geometry type rules implemented in `MeasurementService`:

| Geometry Type | Status | Measurement Type | Unit | Calculation Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Polygon** | `MEASURED` | `area` | `sq_m` | `round(float(geometry.area), 4)` |
| **MultiPolygon** | `MEASURED` | `area` | `sq_m` | `round(float(geometry.area), 4)` |
| **LineString** | `MEASURED` | `length` | `meters` | `round(float(geometry.length), 4)` |
| **MultiLineString** | `MEASURED` | `length` | `meters` | `round(float(geometry.length), 4)` |
| **Point** | `NOT_REQUIRED` | `null` | `null` | Zero-dimensional feature; no area/length |
| **MultiPoint** | `NOT_REQUIRED` | `null` | `null` | Zero-dimensional feature; no area/length |
| **GeometryCollection** | `UNSUPPORTED` | `null` | `null` | Mixed/unsupported geometry; flagged with note |
| **Invalid Topology** | `FAILED` | `null` | `null` | Fails Shapely `.is_valid` check (e.g. self-intersecting) |
| **Empty Geometry** | `FAILED` | `null` | `null` | Geometry object has no coordinate vertices |

---

## 10. Database Design

The relational persistence schema is built using SQLAlchemy 2.x Declarative Models.

### Tables & Relationships

```sql
-- Uploaded files master record
CREATE TABLE uploaded_files (
    id VARCHAR(36) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    feature_count INTEGER NULL,
    crs VARCHAR(100) NULL,
    status VARCHAR(50) NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Granular feature measurements
CREATE TABLE feature_measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id VARCHAR(36) NOT NULL,
    feature_id INTEGER NOT NULL,
    source_id VARCHAR(255) NULL,
    geometry_type VARCHAR(50) NOT NULL,
    geometry_geojson TEXT NULL,
    properties_json TEXT NULL,
    measurement_type VARCHAR(50) NULL,
    measurement_value FLOAT NULL,
    measurement_unit VARCHAR(50) NULL,
    status VARCHAR(50) NOT NULL,
    message TEXT NULL,
    FOREIGN KEY(file_id) REFERENCES uploaded_files(id) ON DELETE CASCADE
);

CREATE INDEX ix_feature_measurements_file_id ON feature_measurements(file_id);
```

- **Cascading Deletes**: Deleting an `UploadedFile` deletes all associated `FeatureMeasurement` records automatically (`ondelete="CASCADE"`).
- **SQLite Foreign Keys**: Foreign key constraints are explicitly enforced at the SQLite driver level using `PRAGMA foreign_keys=ON`.
- **Indexing**: An index on `file_id` ensures rapid measurement lookups for files with high feature counts.

---

## 11. Error Handling

The application adopts a layered error-handling pattern:
1. **HTTP Layer (`FastAPI HTTPException`)**:
   - 400 Bad Request: Unsupported file format, corrupt ZIP, missing Shapefile companion files.
   - 404 Not Found: Requesting an unknown or non-existent file ID.
   - 413 Payload Too Large: Files exceeding 50 MB threshold.
   - 422 Unprocessable Entity: Missing multipart fields or malformed schema payloads.
2. **Domain Service Exceptions**:
   - `StorageServiceError`: File streaming or archive extraction anomalies.
   - `MissingCRSError`: Raised when geospatial data lacks a CRS definition.
   - `MalformedGeospatialFileError`: Raised when GDAL/pyogrio encounters invalid syntax.
3. **Fault-Tolerant Feature Processing**:
   - An invalid geometry on row 5 does not fail rows 1 to 4 or rows 6 to 10. The failing row is marked `FAILED` with its specific topology error, while the overall file transitions to `COMPLETED_WITH_WARNINGS`.

---

## 12. Security Considerations

- **Zip Slip & Path Traversal Prevention**: Every member entry within an uploaded ZIP archive is inspected before extraction. Paths containing `..`, absolute paths (e.g., `/etc/passwd`), or Windows drive letters (`C:\...`) trigger an immediate 400 rejection and prevent extraction.
- **Decompression Bomb Defense**: File streams are checked against `MAX_FILE_SIZE_BYTES` during disk writes. Files that expand beyond the limit are aborted, and temporary storage is purged.
- **Storage Path Concealment**: Internal file system paths (`file_path`) are stored in the database for backend service processing, but are strictly excluded from all API response schemas.
- **Filename Sanitization**: Uploaded filenames are stripped of non-alphanumeric characters (preserving safe dots, dashes, and underscores) to prevent path injection vulnerabilities.
- **No Direct Execution**: Uploaded files are strictly parsed as data tables using PyOgrio/GDAL; no uploaded code or macros are ever executed.
- **Environment & DB Exclusion**: Local SQLite database files (`*.db`), `.env` secrets, and temporary storage directories (`uploads/`) are explicitly excluded from version control via `.gitignore`.

---

## 13. API Documentation

### Endpoints Overview

| Method | Endpoint | Description | Expected Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health status check | `200 OK` |
| `POST` | `/api/files/` | Upload and process geospatial file | `201 Created` |
| `GET` | `/api/files/{id}/` | Retrieve file processing metadata | `200 OK`, `404 Not Found` |
| `GET` | `/api/files/{id}/measurements/`| Retrieve calculated measurements | `200 OK`, `404 Not Found` |

---

## 14. Example curl Requests

### 1. Upload a KML File
```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@survey_boundary.kml;type=application/vnd.google-earth.kml+xml"
```

### 2. Upload a Shapefile ZIP Archive
```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@cadastral_parcels.zip;type=application/zip"
```

### 3. Check File Metadata & Status
```bash
curl -X GET "http://127.0.0.1:8000/api/files/a1b2c3d4e5f6/" \
  -H "accept: application/json"
```

### 4. Retrieve Computed Feature Measurements
```bash
curl -X GET "http://127.0.0.1:8000/api/files/a1b2c3d4e5f6/measurements/" \
  -H "accept: application/json"
```

---

## 15. Example JSON Responses

### `POST /api/files/` Response (201 Created)
```json
{
  "id": "e2f170b0239c",
  "filename": "survey_city.kml",
  "file_type": "kml",
  "status": "COMPLETED"
}
```

### `GET /api/files/{id}/` Response (200 OK)
```json
{
  "id": "e2f170b0239c",
  "filename": "survey_city.kml",
  "file_type": "kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-07T17:50:00.123456Z",
  "updated_at": "2026-10-07T17:50:01.456789Z"
}
```

### `GET /api/files/{id}/measurements/` Response (200 OK)
```json
{
  "file_id": "e2f170b0239c",
  "filename": "survey_city.kml",
  "status": "COMPLETED",
  "crs": "EPSG:4326",
  "total_features": 3,
  "measurements": [
    {
      "id": 1,
      "feature_id": 0,
      "source_id": "Survey Point",
      "geometry_type": "Point",
      "geometry": {
        "type": "Point",
        "coordinates": [233150.2, 1924150.1]
      },
      "properties": {
        "Name": "Survey Point"
      },
      "measurement_type": null,
      "measurement_value": null,
      "measurement_unit": null,
      "status": "NOT_REQUIRED",
      "message": null
    },
    {
      "id": 2,
      "feature_id": 1,
      "source_id": "Transit Corridor",
      "geometry_type": "LineString",
      "geometry": {
        "type": "LineString",
        "coordinates": [[233150.2, 1924150.1], [233256.4, 1924255.8]]
      },
      "properties": {
        "Name": "Transit Corridor"
      },
      "measurement_type": "length",
      "measurement_value": 101.872,
      "measurement_unit": "meters",
      "status": "MEASURED",
      "message": null
    },
    {
      "id": 3,
      "feature_id": 2,
      "source_id": "Urban Park",
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[233080.0, 1924040.0], [233290.0, 1924040.0], [233290.0, 1924260.0], [233080.0, 1924260.0], [233080.0, 1924040.0]]]
      },
      "properties": {
        "Name": "Urban Park"
      },
      "measurement_type": "area",
      "measurement_value": 36881.8334,
      "measurement_unit": "sq_m",
      "status": "MEASURED",
      "message": null
    }
  ]
}
```

---

## 16. Local Setup Instructions

### Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13
- GDAL/GEOS libraries (standard pre-compiled wheels installed automatically with PyOgrio/Shapely)

### Step 1: Clone or Open Project
```bash
cd geospatial-file-measurement-api
```

### Step 2: Virtual Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Linux / macOS:
source venv/bin/activate
```

### Step 3: Requirements Installation
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment
Copy `.env.example` to `.env` if custom adjustments (e.g. ports, upload limits) are required:
```bash
# Windows
copy .env.example .env
# Linux/macOS
cp .env.example .env
```

---

## 17. Running the Application

Start the local development server using Uvicorn:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The server will initialize the SQLite schema automatically and start listening on `http://127.0.0.1:8000`.

---

## 18. Running Tests

Run the full pytest test suite:
```bash
pytest -v
```

All 45 automated tests will execute, validating CRS reprojection, database cascading, reading drivers, measurement math, security protections, and edge cases.

---

## 19. Swagger /docs Usage

FastAPI provides an interactive OpenAPI Swagger UI:
1. Start the server via `uvicorn app.main:app --reload`.
2. Open your browser and navigate to:
   ```
   http://127.0.0.1:8000/docs
   ```
3. Test endpoints interactively:
   - Expand `POST /api/files/`.
   - Click **Try it out**.
   - Choose a `.kml` or `.zip` file from your local machine.
   - Click **Execute** and review the 201 response.
   - Use the returned `id` in `GET /api/files/{id}/` and `GET /api/files/{id}/measurements/`.

---

## 20. Design Decisions

1. **Synchronous Processing Model**:
   - *Decision*: Processing occurs synchronously inside the upload route before returning the response.
   - *Rationale*: For standard municipal/surveying KML and Shapefile files, in-memory spatial processing with PyOgrio and Shapely 2.0 executes rapidly. Synchronous execution guarantees that measurements are immediately available to the client upon upload completion without requiring polling loops or external message broker infrastructure for local evaluation.
2. **PyOgrio as Primary Vector Driver**:
   - *Decision*: Preferred `pyogrio` over legacy `fiona`.
   - *Rationale*: `pyogrio` provides vectorized C-level GDAL bindings that are significantly faster and natively bundle required GDAL/GEOS binaries across platforms, simplifying Windows and Linux setup.
3. **Dynamic UTM Zone Estimation**:
   - *Decision*: Utilized PyProj/GeoPandas `estimate_utm_crs()` for geographic datasets.
   - *Rationale*: Unlike global Web Mercator (`EPSG:3857`), which suffers from severe latitude-dependent area distortion (up to 400%+ near polar regions), local UTM projections preserve conformal metric shapes and minimize planar distortion across local/regional datasets.
4. **Per-Feature Fault Isolation**:
   - *Decision*: Isolate failing or invalid geometries rather than aborting the entire dataset.
   - *Rationale*: In real-world GIS operations, individual features frequently possess minor topological defects (such as self-intersecting boundaries). Dropping or failing an entire cadastral survey due to one bad polygon is unacceptable in production environments.

---

## 21. Alternatives Considered

1. **Celery / Redis Background Worker**:
   - *Evaluated*: Offloading processing to asynchronous worker queues.
   - *Why Deferred*: Introducing Celery/Redis introduces external operational dependencies for an evaluator running the project locally. The current synchronous design meets assignment requirements cleanly and keeps local deployment zero-dependency.
2. **PostgreSQL / PostGIS Database Engine**:
   - *Evaluated*: Using PostGIS for native spatial SQL measurements (`ST_Area`, `ST_Length`).
   - *Why Deferred*: PostGIS requires a running PostgreSQL instance with spatial extensions installed. Using GeoPandas + Shapely achieves the same spatial accuracy in Python while keeping the database layer completely portable (SQLite).
3. **Hardcoding EPSG:4326 for Missing CRS**:
   - *Evaluated*: Defaulting missing CRS files to WGS 84.
   - *Why Rejected*: Dangerous in surveying. A Shapefile missing a `.prj` could be in local state plane feet or national grid coordinates; guessing WGS 84 results in invalid coordinates and erroneous calculations.

---

## 22. Known Limitations

- **Local SQLite Storage**: SQLite is used for local development. SQLite does not support high-concurrency write locks.
- **Synchronous Execution Latency**: Datasets containing hundreds of thousands of features will block the HTTP worker until calculation completes.
- **Single Page Measurements**: `GET /api/files/{id}/measurements/` returns the full measurement list in a single JSON payload.
- **UTM Boundary Distortion**: Datasets spanning multiple UTM zones (continental scale) will exhibit scale distortion away from the estimated central meridian.

---

## 23. Learning Outcomes

- Mastery of vector file normalization across different geospatial specifications (KML vs. Shapefile).
- Deep understanding of geodesic vs. planar projection physics and the importance of metric projected coordinate reference systems.
- Robust implementation of defense-in-depth archive security (Zip Slip, path traversal, decompression guards).
- Designing decoupled, service-oriented backend architectures in FastAPI with clean separation of storage, domain processing, and persistence.

---

## 24. Future Scope

If extended for large-scale enterprise production:
- **Asynchronous Task Queue**: Integrate Celery, ARQ, or Redis Queue to process files asynchronously in worker pools, with WebSocket or polling status updates.
- **PostGIS Storage**: Migrate to PostgreSQL with PostGIS for spatial indexing (`GIST`), topological validation, and spatial queries.
- **Pagination & Filtering**: Add cursor or offset pagination (`?page=1&limit=50`) and status filters (`?status=MEASURED`) to `/measurements/`.
- **Cloud Object Storage**: Transition `StorageService` to store raw files in AWS S3 or Google Cloud Storage with presigned URLs.
- **Authentication & RBAC**: Introduce JWT-based OAuth2 authentication and user-level multi-tenancy.
