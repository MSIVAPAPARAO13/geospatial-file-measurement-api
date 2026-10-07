from dataclasses import dataclass
import json
from datetime import datetime, date
from typing import Optional, Dict, Any, List
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from app.models.file import FeatureStatus


@dataclass(frozen=True)
class FeatureMeasurementResult:
    """Immutable data structure representing calculated measurements for a single feature."""

    feature_id: int
    geometry_type: str
    geometry_geojson: Optional[str]
    properties_json: Optional[str]
    measurement_type: Optional[str]
    measurement_value: Optional[float]
    measurement_unit: Optional[str]
    status: str
    message: Optional[str] = None


class MeasurementService:
    """Service executing metric measurement calculations on projected geometries."""

    POLYGON_TYPES = {"Polygon", "MultiPolygon"}
    LINESTRING_TYPES = {"LineString", "MultiLineString"}
    POINT_TYPES = {"Point", "MultiPoint"}

    @classmethod
    def calculate_feature_measurement(
        cls,
        feature_id: int,
        geom: Optional[BaseGeometry],
        properties: Optional[Dict[str, Any]] = None,
    ) -> FeatureMeasurementResult:
        """
        Calculate measurement for an individual feature geometry with per-feature fault tolerance.
        """
        props_json = json.dumps(properties) if properties else None

        if geom is None or geom.is_empty:
            return FeatureMeasurementResult(
                feature_id=feature_id,
                geometry_type="Unknown",
                geometry_geojson=None,
                properties_json=props_json,
                measurement_type=None,
                measurement_value=None,
                measurement_unit=None,
                status=FeatureStatus.FAILED.value,
                message="Geometry is missing or empty.",
            )

        geom_type = geom.geom_type
        geojson_str = None
        try:
            geojson_str = json.dumps(mapping(geom))
        except Exception:
            pass

        # Check geometry validity
        if not geom.is_valid:
            return FeatureMeasurementResult(
                feature_id=feature_id,
                geometry_type=geom_type,
                geometry_geojson=geojson_str,
                properties_json=props_json,
                measurement_type=None,
                measurement_value=None,
                measurement_unit=None,
                status=FeatureStatus.FAILED.value,
                message="Geometry is invalid (topology error).",
            )

        try:
            if geom_type in cls.POLYGON_TYPES:
                area_val = float(geom.area)
                return FeatureMeasurementResult(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties_json=props_json,
                    measurement_type="area",
                    measurement_value=round(area_val, 4),
                    measurement_unit="sq_m",
                    status=FeatureStatus.MEASURED.value,
                    message=None,
                )

            elif geom_type in cls.LINESTRING_TYPES:
                length_val = float(geom.length)
                return FeatureMeasurementResult(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties_json=props_json,
                    measurement_type="length",
                    measurement_value=round(length_val, 4),
                    measurement_unit="meters",
                    status=FeatureStatus.MEASURED.value,
                    message=None,
                )

            elif geom_type in cls.POINT_TYPES:
                return FeatureMeasurementResult(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties_json=props_json,
                    measurement_type=None,
                    measurement_value=None,
                    measurement_unit=None,
                    status=FeatureStatus.NOT_REQUIRED.value,
                    message=None,
                )

            else:
                return FeatureMeasurementResult(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    geometry_geojson=geojson_str,
                    properties_json=props_json,
                    measurement_type=None,
                    measurement_value=None,
                    measurement_unit=None,
                    status=FeatureStatus.UNSUPPORTED.value,
                    message=f"Geometry type '{geom_type}' is not supported for measurement calculation.",
                )

        except Exception as e:
            return FeatureMeasurementResult(
                feature_id=feature_id,
                geometry_type=geom_type,
                geometry_geojson=geojson_str,
                properties_json=props_json,
                measurement_type=None,
                measurement_value=None,
                measurement_unit=None,
                status=FeatureStatus.FAILED.value,
                message=f"Measurement calculation error: {str(e)}",
            )

    @classmethod
    def calculate_dataset_measurements(
        cls, gdf: gpd.GeoDataFrame
    ) -> List[FeatureMeasurementResult]:
        """
        Process all rows in a GeoDataFrame, returning a list of FeatureMeasurementResult objects.
        """
        results = []
        attr_columns = [col for col in gdf.columns if col != gdf._geometry_column_name]

        for index, row in gdf.iterrows():
            geom: Optional[BaseGeometry] = row.geometry
            props = {}
            for col in attr_columns:
                val = row[col]
                if val is None or pd.isna(val):
                    continue
                if isinstance(val, (datetime, date)):
                    props[col] = val.isoformat()
                elif isinstance(val, (np.integer, int)):
                    props[col] = int(val)
                elif isinstance(val, (np.floating, float)):
                    props[col] = float(val)
                elif isinstance(val, (str, bool)):
                    props[col] = val
                else:
                    props[col] = str(val)

            res = cls.calculate_feature_measurement(
                feature_id=int(index),
                geom=geom,
                properties=props if props else None,
            )
            results.append(res)

        return results
