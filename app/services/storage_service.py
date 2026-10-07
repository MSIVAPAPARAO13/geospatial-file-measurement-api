import os
import io
import shutil
import zipfile
import uuid
from pathlib import Path
from typing import Tuple, List
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings
from app.models.file import FileType


class StorageServiceError(HTTPException):
    """Base HTTP exception for storage and validation errors."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class StorageService:
    """Service handling file upload streaming, format validation, ZIP security checks, and safe storage."""

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize raw filename to prevent path injection."""
        base_name = os.path.basename(filename)
        # Strip out any remaining dangerous characters
        safe_name = "".join(c for c in base_name if c.isalnum() or c in "._- ")
        return safe_name or "uploaded_file"

    @classmethod
    async def save_uploaded_file(
        cls, upload_file: UploadFile, file_id: str, upload_dir: Path | None = None
    ) -> Tuple[str, str, Path]:
        """
        Validate, stream, and safely store an uploaded geospatial file.

        Returns:
            Tuple of (sanitized_filename, detected_file_type, stored_file_path)
        """
        if not upload_file.filename:
            raise StorageServiceError("Uploaded file has no filename.")

        filename = upload_file.filename
        ext = Path(filename).suffix.lower()

        if ext not in [".kml", ".zip"]:
            raise StorageServiceError(
                f"Unsupported file extension '{ext}'. Only .kml and .zip files are allowed."
            )

        target_dir = (upload_dir or settings.UPLOAD_DIR) / file_id
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_filename = cls.sanitize_filename(filename)
        temp_file_path = target_dir / f"temp_{safe_filename}"

        # Stream file to disk while enforcing max size limit
        total_size = 0
        chunk_size = 1024 * 1024  # 1 MB chunk

        try:
            with temp_file_path.open("wb") as buffer:
                while chunk := await upload_file.read(chunk_size):
                    total_size += len(chunk)
                    if total_size > settings.MAX_FILE_SIZE_BYTES:
                        raise StorageServiceError(
                            f"File size exceeds maximum allowed limit of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        )
                    buffer.write(chunk)
        except StorageServiceError:
            # Clean up temp file on size error
            if temp_file_path.exists():
                temp_file_path.unlink()
            raise
        except Exception as e:
            if temp_file_path.exists():
                temp_file_path.unlink()
            raise StorageServiceError(f"Failed to write uploaded file to disk: {str(e)}")

        if total_size == 0:
            if temp_file_path.exists():
                temp_file_path.unlink()
            raise StorageServiceError("Uploaded file is empty (0 bytes).")

        # Process based on extension
        if ext == ".kml":
            final_path = target_dir / safe_filename
            temp_file_path.rename(final_path)
            return safe_filename, FileType.KML.value, final_path

        elif ext == ".zip":
            final_path = target_dir / safe_filename
            temp_file_path.rename(final_path)

            # Validate ZIP archive and check for Shapefile content
            cls._validate_and_extract_zip(final_path, target_dir)
            return safe_filename, FileType.SHAPEFILE.value, final_path

        raise StorageServiceError("Unsupported file type.")

    @classmethod
    def _validate_and_extract_zip(cls, zip_file_path: Path, target_dir: Path) -> Path:
        """Validate ZIP archive safety and extract contents safely."""
        if not zipfile.is_zipfile(zip_file_path):
            raise StorageServiceError("Uploaded .zip file is corrupt or not a valid ZIP archive.")

        extract_dir = target_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        resolved_extract_dir = extract_dir.resolve()

        try:
            with zipfile.ZipFile(zip_file_path, "r") as archive:
                members = archive.infolist()
                if not members:
                    raise StorageServiceError("Uploaded ZIP archive is empty.")

                member_names = [m.filename for m in members]

                # 1. Path traversal security checks
                for name in member_names:
                    # Check absolute paths or Windows drive letters
                    p = Path(name)
                    if p.is_absolute() or name.startswith("/") or name.startswith("\\"):
                        raise StorageServiceError(
                            f"Security violation: ZIP archive contains absolute path entry '{name}'."
                        )
                    if ".." in p.parts:
                        raise StorageServiceError(
                            f"Security violation: ZIP archive contains path traversal entry '{name}'."
                        )

                    # Verify final destination path is strictly within extract_dir
                    target_member_path = (extract_dir / name).resolve()
                    if not str(target_member_path).startswith(str(resolved_extract_dir)):
                        raise StorageServiceError(
                            f"Security violation: ZIP entry '{name}' extracts outside of target directory."
                        )

                # 2. Shapefile contents validation
                shp_files = [
                    m for m in member_names if m.lower().endswith(".shp") and not m.startswith("__MACOSX")
                ]

                if not shp_files:
                    raise StorageServiceError(
                        "Invalid Shapefile archive: ZIP does not contain any .shp file."
                    )

                # Verify companion files (.shx and .dbf) for each .shp file
                lower_names = {m.lower(): m for m in member_names}
                for shp_name in shp_files:
                    stem = shp_name[:-4].lower()
                    required_shx = f"{stem}.shx"
                    required_dbf = f"{stem}.dbf"

                    if required_shx not in lower_names or required_dbf not in lower_names:
                        raise StorageServiceError(
                            f"Invalid Shapefile archive: Missing companion file (.shx or .dbf) for '{shp_name}'."
                        )

                # 3. Safe extraction
                archive.extractall(path=extract_dir)

        except zipfile.BadZipFile:
            raise StorageServiceError("Uploaded file is a corrupted ZIP archive.")
        except StorageServiceError:
            raise
        except Exception as e:
            raise StorageServiceError(f"Failed to inspect or extract ZIP archive: {str(e)}")

        return extract_dir
