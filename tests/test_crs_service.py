import pytest
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from app.services.crs_service import (
    CRSService,
    MissingCRSError,
    CRSTransformationError,
    CRSReprojectionResult,
)


@pytest.fixture
def geographic_epsg4326_gdf() -> gpd.GeoDataFrame:
    """Geographic dataset (EPSG:4326) with Point, LineString, and Polygon in Hyderabad, India."""
    return gpd.GeoDataFrame(
        {"id": [1, 2, 3], "label": ["Point", "Line", "Polygon"]},
        geometry=[
            Point(78.4867, 17.3850),
            LineString([(78.4867, 17.3850), (78.4877, 17.3860)]),
            Polygon([(78.4860, 17.3840), (78.4880, 17.3840), (78.4880, 17.3860), (78.4860, 17.3860), (78.4860, 17.3840)]),
        ],
        crs="EPSG:4326",
    )


@pytest.fixture
def projected_epsg3857_gdf() -> gpd.GeoDataFrame:
    """Projected dataset (Web Mercator EPSG:3857)."""
    return gpd.GeoDataFrame(
        {"id": [10]},
        geometry=[Polygon([(1390500, 5144500), (1391500, 5144500), (1391500, 5145500), (1390500, 5145500)])],
        crs="EPSG:3857",
    )


@pytest.fixture
def missing_crs_gdf() -> gpd.GeoDataFrame:
    """Dataset with missing (None) CRS."""
    return gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(10.0, 20.0)],
        crs=None,
    )


def test_geographic_epsg4326_transforms_to_projected_utm(geographic_epsg4326_gdf):
    """Verify EPSG:4326 geographic dataset is automatically reprojected to a UTM projected CRS."""
    result = CRSService.prepare_for_measurement(geographic_epsg4326_gdf)

    assert isinstance(result, CRSReprojectionResult)
    assert result.is_reprojected is True
    assert "4326" in result.source_crs
    assert "32644" in result.target_crs  # UTM Zone 44N for Hyderabad coordinates
    assert result.transformed_gdf.crs.is_projected is True


def test_already_projected_dataset_remains_projected(projected_epsg3857_gdf):
    """Verify an already projected dataset (EPSG:3857) remains unchanged."""
    result = CRSService.prepare_for_measurement(projected_epsg3857_gdf)

    assert result.is_reprojected is False
    assert result.source_crs == result.target_crs
    assert "3857" in result.target_crs
    assert result.transformed_gdf.crs.is_projected is True


def test_missing_crs_raises_missing_crs_error(missing_crs_gdf):
    """Verify missing CRS raises MissingCRSError and is never guessed as EPSG:4326."""
    with pytest.raises(MissingCRSError) as exc_info:
        CRSService.prepare_for_measurement(missing_crs_gdf)

    assert "no defined Coordinate Reference System" in str(exc_info.value)


def test_original_crs_preserved_separately_from_target(geographic_epsg4326_gdf):
    """Verify source_crs retains EPSG:4326 while target_crs contains the projected UTM CRS."""
    result = CRSService.prepare_for_measurement(geographic_epsg4326_gdf)

    assert result.source_crs != result.target_crs
    assert "4326" in result.source_crs
    assert "32644" in result.target_crs


def test_transformed_coordinates_differ_from_geographic(geographic_epsg4326_gdf):
    """Verify projected coordinate values (meters) differ numerically from lat/lon degrees."""
    orig_geom = geographic_epsg4326_gdf.geometry.iloc[0]
    result = CRSService.prepare_for_measurement(geographic_epsg4326_gdf)
    proj_geom = result.transformed_gdf.geometry.iloc[0]

    # Geographic: (78.4867, 17.3850)
    assert abs(orig_geom.x) < 180 and abs(orig_geom.y) < 90
    # Projected UTM: (~233150, ~1924150)
    assert abs(proj_geom.x) > 10000 and abs(proj_geom.y) > 100000


def test_reprojection_preserves_feature_count_and_geometry_types(geographic_epsg4326_gdf):
    """Verify feature count and geometry types remain intact after reprojection."""
    result = CRSService.prepare_for_measurement(geographic_epsg4326_gdf)
    transformed = result.transformed_gdf

    assert len(transformed) == len(geographic_epsg4326_gdf)
    assert transformed.geometry.iloc[0].geom_type == "Point"
    assert transformed.geometry.iloc[1].geom_type == "LineString"
    assert transformed.geometry.iloc[2].geom_type == "Polygon"


def test_empty_dataset_raises_transformation_error():
    """Verify empty GeoDataFrame raises CRSTransformationError."""
    empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    with pytest.raises(CRSTransformationError) as exc_info:
        CRSService.prepare_for_measurement(empty_gdf)

    assert "empty" in str(exc_info.value).lower()
