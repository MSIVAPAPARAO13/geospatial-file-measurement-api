from pathlib import Path
from typing import Dict, Any, List, Optional
import geopandas as gpd
from shapely.geometry.base import BaseGeometry
import pyogrio


class GeospatialProcessingError(Exception):
    """Base exception for geospatial file reading and parsing errors."""

    pass


class UnsupportedGeospatialFormatError(GeospatialProcessingError):
    """Raised when file format is not supported for reading."""

    pass


class GeospatialFileNotFoundError(GeospatialProcessingError):
    """Raised when source file or Shapefile directory is missing."""

    pass


class DriverUnavailableError(GeospatialProcessingError):
    """Raised when required GDAL/PyOgrio driver (e.g. KML) is missing."""

    pass


class MalformedGeospatialFileError(GeospatialProcessingError):
    """Raised when KML or Shapefile is corrupt or cannot be parsed."""

    pass


class EmptyGeospatialDatasetError(GeospatialProcessingError):
    """Raised when dataset contains zero features."""

    pass


class GeospatialService:
    """Service for loading and normalizing geospatial vector datasets into GeoDataFrames."""

    @classmethod
    def read_geospatial_file(cls, file_path: str | Path, file_type: str) -> gpd.GeoDataFrame:
        """
        Read a stored geospatial file (.kml or Shapefile) into a unified GeoPandas GeoDataFrame.

        Args:
            file_path: Path to stored file (e.g., .kml file or zip/extracted directory)
            file_type: Type identifier ('kml' or 'shapefile')

        Returns:
            gpd.GeoDataFrame containing geometry, attributes, and source CRS metadata.
        """
        path = Path(file_path)
        if not path.exists():
            raise GeospatialFileNotFoundError(f"Geospatial storage path does not exist: {path}")

        file_type_clean = file_type.lower().strip()
        if file_type_clean == "kml":
            return cls._read_kml(path)
        elif file_type_clean in ["shapefile", "shp"]:
            return cls._read_shapefile(path)
        else:
            raise UnsupportedGeospatialFormatError(
                f"Unsupported file format '{file_type}' for geospatial reading."
            )

    @classmethod
    def _read_kml(cls, path: Path) -> gpd.GeoDataFrame:
        """Read KML file into GeoDataFrame using pyogrio/Fiona driver."""
        target_kml = path
        if path.is_dir():
            kml_files = list(path.glob("*.kml")) + list(path.glob("*.KML"))
            if not kml_files:
                raise GeospatialFileNotFoundError(f"No .kml file found in directory: {path}")
            target_kml = kml_files[0]

        # Verify driver availability
        drivers = pyogrio.list_drivers()
        if "KML" not in drivers and "LIBKML" not in drivers:
            raise DriverUnavailableError("KML driver is unavailable in current GDAL/PyOgrio environment.")

        try:
            gdf = gpd.read_file(target_kml, engine="pyogrio")
        except Exception as e:
            raise MalformedGeospatialFileError(f"Failed to parse KML file '{target_kml.name}': {str(e)}")

        if gdf is None or len(gdf) == 0:
            raise EmptyGeospatialDatasetError(f"KML dataset '{target_kml.name}' contains zero features.")

        return gdf

    @classmethod
    def _read_shapefile(cls, path: Path) -> gpd.GeoDataFrame:
        """Locate and read Shapefile into GeoDataFrame."""
        shp_path: Optional[Path] = None

        if path.is_file():
            if path.suffix.lower() == ".shp":
                shp_path = path
            elif path.suffix.lower() == ".zip":
                # Look in sibling 'extracted' directory created during Phase 3
                extracted_dir = path.parent / "extracted"
                if extracted_dir.exists():
                    shp_files = list(extracted_dir.rglob("*.shp"))
                    if shp_files:
                        shp_path = shp_files[0]

        elif path.is_dir():
            shp_files = list(path.rglob("*.shp"))
            if shp_files:
                shp_path = shp_files[0]

        if not shp_path or not shp_path.exists():
            raise GeospatialFileNotFoundError(f"No valid .shp file found for path: {path}")

        try:
            gdf = gpd.read_file(shp_path, engine="pyogrio")
        except Exception as e:
            raise MalformedGeospatialFileError(f"Failed to parse Shapefile '{shp_path.name}': {str(e)}")

        if gdf is None or len(gdf) == 0:
            raise EmptyGeospatialDatasetError(f"Shapefile '{shp_path.name}' contains zero features.")

        return gdf

    @classmethod
    def extract_features_metadata(cls, gdf: gpd.GeoDataFrame) -> List[Dict[str, Any]]:
        """
        Extract normalized feature metadata dictionaries from a GeoDataFrame.

        Returns list of dicts with:
        - feature_id (int)
        - geometry_type (str)
        - geometry (Shapely geometry object)
        - properties (dict of row attributes)
        - source_crs (str or None)
        """
        features = []
        crs_str = str(gdf.crs) if gdf.crs is not None else None

        # Non-geometry attribute column names
        attr_columns = [col for col in gdf.columns if col != gdf._geometry_column_name]

        for index, row in gdf.iterrows():
            geom: Optional[BaseGeometry] = row.geometry
            geom_type = geom.geom_type if geom is not None else "Unknown"

            # Build properties dictionary cleanly
            properties = {}
            for col in attr_columns:
                val = row[col]
                # Filter out pandas/numpy NaNs for clean serialization
                if val is not None and str(val) != "nan":
                    properties[col] = val

            features.append(
                {
                    "feature_id": int(index),
                    "geometry_type": geom_type,
                    "geometry": geom,
                    "properties": properties,
                    "source_crs": crs_str,
                }
            )

        return features
