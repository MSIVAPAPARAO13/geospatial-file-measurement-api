import pytest
import geopandas as gpd
from shapely.geometry import (
    Point,
    MultiPoint,
    LineString,
    MultiLineString,
    Polygon,
    MultiPolygon,
    GeometryCollection,
)
from app.services.measurement_service import MeasurementService, FeatureMeasurementResult


def test_polygon_area_calculation():
    """Verify 10m x 10m square polygon calculates area = 100 sq_m."""
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    result = MeasurementService.calculate_feature_measurement(0, square, {"name": "Plot A"})

    assert isinstance(result, FeatureMeasurementResult)
    assert result.geometry_type == "Polygon"
    assert result.measurement_type == "area"
    assert result.measurement_value == 100.0
    assert result.measurement_unit == "sq_m"
    assert result.status == "MEASURED"
    assert result.message is None


def test_multipolygon_area_calculation():
    """Verify MultiPolygon combining two 10x10 squares calculates total area = 200 sq_m."""
    p1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    p2 = Polygon([(20, 0), (30, 0), (30, 10), (20, 10), (20, 0)])
    multi_poly = MultiPolygon([p1, p2])

    result = MeasurementService.calculate_feature_measurement(1, multi_poly)

    assert result.geometry_type == "MultiPolygon"
    assert result.measurement_type == "area"
    assert result.measurement_value == 200.0
    assert result.measurement_unit == "sq_m"
    assert result.status == "MEASURED"


def test_linestring_length_calculation():
    """Verify LineString from (0,0) to (3,4) calculates length = 5 meters (3-4-5 triangle)."""
    line = LineString([(0, 0), (3, 4)])
    result = MeasurementService.calculate_feature_measurement(2, line)

    assert result.geometry_type == "LineString"
    assert result.measurement_type == "length"
    assert result.measurement_value == 5.0
    assert result.measurement_unit == "meters"
    assert result.status == "MEASURED"


def test_multilinestring_length_calculation():
    """Verify MultiLineString combining two 5m lines calculates length = 10 meters."""
    l1 = LineString([(0, 0), (3, 4)])
    l2 = LineString([(10, 0), (13, 4)])
    multi_line = MultiLineString([l1, l2])

    result = MeasurementService.calculate_feature_measurement(3, multi_line)

    assert result.geometry_type == "MultiLineString"
    assert result.measurement_type == "length"
    assert result.measurement_value == 10.0
    assert result.measurement_unit == "meters"
    assert result.status == "MEASURED"


def test_point_measurement_not_required():
    """Verify Point geometry returns status NOT_REQUIRED and null measurement values."""
    point = Point(100.0, 200.0)
    result = MeasurementService.calculate_feature_measurement(4, point)

    assert result.geometry_type == "Point"
    assert result.measurement_type is None
    assert result.measurement_value is None
    assert result.measurement_unit is None
    assert result.status == "NOT_REQUIRED"


def test_multipoint_measurement_not_required():
    """Verify MultiPoint geometry returns status NOT_REQUIRED and null measurement values."""
    multi_point = MultiPoint([Point(0, 0), Point(10, 10)])
    result = MeasurementService.calculate_feature_measurement(5, multi_point)

    assert result.geometry_type == "MultiPoint"
    assert result.measurement_type is None
    assert result.measurement_value is None
    assert result.status == "NOT_REQUIRED"


def test_unsupported_geometry_type():
    """Verify GeometryCollection returns status UNSUPPORTED with clear explanatory message."""
    geom_coll = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    result = MeasurementService.calculate_feature_measurement(6, geom_coll)

    assert result.geometry_type == "GeometryCollection"
    assert result.status == "UNSUPPORTED"
    assert result.measurement_value is None
    assert "not supported" in result.message


def test_invalid_self_intersecting_polygon():
    """Verify invalid self-intersecting polygon returns status FAILED without raising an unhandled crash."""
    # Self-intersecting bow-tie polygon
    bowtie = Polygon([(0, 0), (0, 10), (10, 0), (10, 10), (0, 0)])
    result = MeasurementService.calculate_feature_measurement(7, bowtie)

    assert result.status == "FAILED"
    assert result.measurement_value is None
    assert "invalid" in result.message.lower()


def test_dataset_measurements_fault_tolerance():
    """Verify dataset containing valid, point, unsupported, and invalid geometries processes all rows without crashing."""
    valid_poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    valid_line = LineString([(0, 0), (3, 4)])
    point = Point(5, 5)
    invalid_poly = Polygon([(0, 0), (0, 10), (10, 0), (10, 10), (0, 0)])

    gdf = gpd.GeoDataFrame(
        {"id": [1, 2, 3, 4]},
        geometry=[valid_poly, valid_line, point, invalid_poly],
        crs="EPSG:32633",
    )

    results = MeasurementService.calculate_dataset_measurements(gdf)

    assert len(results) == 4
    assert results[0].status == "MEASURED"
    assert results[0].measurement_value == 100.0

    assert results[1].status == "MEASURED"
    assert results[1].measurement_value == 5.0

    assert results[2].status == "NOT_REQUIRED"
    assert results[2].measurement_value is None

    assert results[3].status == "FAILED"
    assert results[3].measurement_value is None
