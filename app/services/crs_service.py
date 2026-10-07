from dataclasses import dataclass
from typing import Optional
import geopandas as gpd
from pyproj.exceptions import CRSError as PyProjCRSError


class CRSError(Exception):
    """Base domain exception for Coordinate Reference System processing errors."""

    pass


class MissingCRSError(CRSError):
    """Raised when dataset has no defined CRS."""

    pass


class CRSInvalidError(CRSError):
    """Raised when source CRS is invalid or cannot be parsed."""

    pass


class CRSTransformationError(CRSError):
    """Raised when estimation of UTM or reprojection fails."""

    pass


@dataclass(frozen=True)
class CRSReprojectionResult:
    """Immutable data structure holding source CRS, target metric CRS, and reprojected GeoDataFrame."""

    source_crs: str
    target_crs: str
    is_reprojected: bool
    transformed_gdf: gpd.GeoDataFrame


class CRSService:
    """Service handling CRS identification, validation, and projected UTM transformation."""

    @classmethod
    def prepare_for_measurement(cls, gdf: gpd.GeoDataFrame) -> CRSReprojectionResult:
        """
        Validate source CRS and ensure geometries are represented in a projected metric CRS.

        - If CRS is missing: Raises MissingCRSError. Never assumes EPSG:4326.
        - If CRS is already projected: Preserves original CRS and geometries unchanged.
        - If CRS is geographic (lat/lon degrees): Estimates local UTM zone and reprojects to meters.

        Args:
            gdf: Source GeoDataFrame

        Returns:
            CRSReprojectionResult containing source_crs, target_crs, is_reprojected flag, and transformed_gdf.
        """
        if gdf is None or len(gdf) == 0:
            raise CRSTransformationError("Cannot perform CRS handling on an empty or null GeoDataFrame.")

        if gdf.crs is None:
            raise MissingCRSError(
                "Source dataset has no defined Coordinate Reference System (CRS). "
                "Safe metric measurement is impossible without a valid source CRS."
            )

        source_crs_str = str(gdf.crs)

        try:
            if gdf.crs.is_projected:
                return CRSReprojectionResult(
                    source_crs=source_crs_str,
                    target_crs=source_crs_str,
                    is_reprojected=False,
                    transformed_gdf=gdf,
                )
            elif gdf.crs.is_geographic:
                try:
                    target_utm_crs = gdf.estimate_utm_crs()
                except Exception as e:
                    raise CRSTransformationError(
                        f"Failed to estimate local UTM projected CRS for geographic dataset: {str(e)}"
                    )

                if target_utm_crs is None:
                    raise CRSTransformationError(
                        "Unable to determine a suitable UTM projected CRS for dataset location."
                    )

                target_crs_str = str(target_utm_crs)

                try:
                    transformed_gdf = gdf.to_crs(target_utm_crs)
                except Exception as e:
                    raise CRSTransformationError(
                        f"Failed to reproject dataset from '{source_crs_str}' to '{target_crs_str}': {str(e)}"
                    )

                return CRSReprojectionResult(
                    source_crs=source_crs_str,
                    target_crs=target_crs_str,
                    is_reprojected=True,
                    transformed_gdf=transformed_gdf,
                )
            else:
                raise CRSInvalidError(f"Dataset CRS '{source_crs_str}' is neither geographic nor projected.")

        except PyProjCRSError as e:
            raise CRSInvalidError(f"Invalid CRS definition encountered: {str(e)}")
