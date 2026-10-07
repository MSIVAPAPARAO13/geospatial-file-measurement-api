import pytest
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from app.services.geospatial_service import (
    GeospatialService,
    GeospatialFileNotFoundError,
    UnsupportedGeospatialFormatError,
    MalformedGeospatialFileError,
    EmptyGeospatialDatasetError,
)


@pytest.fixture
def sample_kml_file(tmp_path) -> Path:
    """Fixture creating a valid KML file with Point, LineString, and Polygon geometries."""
    kml_path = tmp_path / "sample_dataset.kml"
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Point Feature", "Line Feature", "Polygon Feature"],
            "description": ["Marker 1", "Path 1", "Zone 1"],
        },
        geometry=[
            Point(78.4867, 17.3850),
            LineString([(78.4867, 17.3850), (78.4877, 17.3860)]),
            Polygon([(78.4860, 17.3840), (78.4880, 17.3840), (78.4880, 17.3860), (78.4860, 17.3860), (78.4860, 17.3840)]),
        ],
        crs="EPSG:4326",
    )
    gdf.to_file(kml_path, driver="KML", engine="pyogrio")
    return kml_path


@pytest.fixture
def sample_shapefile_dir(tmp_path) -> Path:
    """Fixture creating a valid Shapefile (.shp, .shx, .dbf, .prj) directory with projected CRS."""
    shp_dir = tmp_path / "shapefile_dataset"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "polygons.shp"

    gdf = gpd.GeoDataFrame(
        {"zone_id": [101, 102], "label": ["Alpha", "Beta"]},
        geometry=[
            Polygon([(500000, 4000000), (501000, 4000000), (501000, 4001000), (500000, 4001000), (500000, 4000000)]),
            Polygon([(502000, 4000000), (503000, 4000000), (503000, 4001000), (502000, 4001000), (502000, 4000000)]),
        ],
        crs="EPSG:32644",
    )
    gdf.to_file(shp_path, engine="pyogrio")
    return shp_dir


@pytest.fixture
def shapefile_no_crs(tmp_path) -> Path:
    """Fixture creating a Shapefile without a .prj file (missing CRS)."""
    shp_dir = tmp_path / "no_crs_dataset"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "unprojected.shp"

    gdf = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(10.0, 20.0)],
        crs=None,
    )
    gdf.to_file(shp_path, engine="pyogrio")
    return shp_path


def test_read_kml_returns_geodataframe_with_geometries(sample_kml_file):
    """Verify reading KML file returns a GeoDataFrame with Point, LineString, and Polygon."""
    gdf = GeospatialService.read_geospatial_file(sample_kml_file, "kml")

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 3
    geom_types = set(gdf.geometry.geom_type)
    assert "Point" in geom_types
    assert "LineString" in geom_types
    assert "Polygon" in geom_types


def test_read_kml_preserves_crs_and_attributes(sample_kml_file):
    """Verify KML reader preserves EPSG:4326 CRS and attribute metadata."""
    gdf = GeospatialService.read_geospatial_file(sample_kml_file, "kml")

    assert gdf.crs is not None
    assert "4326" in str(gdf.crs)

    features_meta = GeospatialService.extract_features_metadata(gdf)
    assert len(features_meta) == 3
    assert features_meta[0]["properties"]["Name"] == "Point Feature"
    assert features_meta[1]["geometry_type"] == "LineString"
    assert features_meta[2]["geometry_type"] == "Polygon"


def test_read_shapefile_returns_geodataframe_with_projected_crs(sample_shapefile_dir):
    """Verify reading Shapefile returns GeoDataFrame with projected CRS EPSG:32644."""
    gdf = GeospatialService.read_geospatial_file(sample_shapefile_dir, "shapefile")

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert gdf.crs is not None
    assert "32644" in str(gdf.crs)

    features = GeospatialService.extract_features_metadata(gdf)
    assert len(features) == 2
    assert features[0]["properties"]["zone_id"] == 101
    assert features[1]["properties"]["label"] == "Beta"


def test_read_shapefile_missing_crs_not_guessed(shapefile_no_crs):
    """Verify dataset with missing CRS retains None CRS and is NOT guessed."""
    gdf = GeospatialService.read_geospatial_file(shapefile_no_crs, "shapefile")

    assert gdf.crs is None
    features = GeospatialService.extract_features_metadata(gdf)
    assert features[0]["source_crs"] is None


def test_missing_file_raises_not_found_error(tmp_path):
    """Verify missing file raises GeospatialFileNotFoundError."""
    missing_path = tmp_path / "non_existent.kml"

    with pytest.raises(GeospatialFileNotFoundError):
        GeospatialService.read_geospatial_file(missing_path, "kml")


def test_unsupported_format_raises_error(sample_kml_file):
    """Verify unsupported file format type string raises UnsupportedGeospatialFormatError."""
    with pytest.raises(UnsupportedGeospatialFormatError):
        GeospatialService.read_geospatial_file(sample_kml_file, "gpx")


def test_malformed_file_raises_parsing_error(tmp_path):
    """Verify corrupt/malformed geospatial file raises MalformedGeospatialFileError."""
    corrupt_kml = tmp_path / "corrupt.kml"
    corrupt_kml.write_text("NOT A VALID KML XML CONTENT <<<>>>")

    with pytest.raises(MalformedGeospatialFileError):
        GeospatialService.read_geospatial_file(corrupt_kml, "kml")
