"""
Module for extracting files from ZIP/JAR archives.
Handles extraction of code and configuration files from packaged Spark applications.
"""

import os
import zipfile
import logging
from typing import List, Union, Optional
import shutil
from urllib.parse import urlparse

from prophecy.executionmetrics.package import FileContent

# Set up logging
logger = logging.getLogger(__name__)


class ZipFileExtractor:
    """Utility class for extracting files from ZIP and JAR archives."""

    @staticmethod
    def _zip_file(file_path: str) -> Union[zipfile.ZipFile, Exception]:
        """
        Open a ZIP or JAR file.

        Args:
            file_path: Path to the archive file

        Returns:
            ZipFile object or Exception if failed
        """
        try:
            file_name = os.path.basename(file_path)

            # if file_name.endswith(".jar") or file_name.endswith(".whl"):
            if file_name.endswith(".whl"):
                return zipfile.ZipFile(file_path, "r")
            else:
                raise RuntimeError(f"Unknown Extension {file_name}!!")

        except Exception as exception:
            logger.error(f"Error opening zip '{file_path}'", exc_info=True)
            return exception

    @staticmethod
    def _unzip(zip_path: str) -> Union[List[FileContent], Exception]:
        """
        Extract code and config files from a ZIP archive.

        Args:
            zip_path: Path to the ZIP file

        Returns:
            List of FileContent objects or Exception if failed
        """
        zip_result = ZipFileExtractor._zip_file(zip_path)

        if isinstance(zip_result, Exception):
            return zip_result

        try:
            with zip_result as zip_file:
                file_contents = []

                for entry in zip_file.namelist():
                    if FileContent.is_code_or_config(entry):
                        try:
                            with zip_file.open(entry) as f:
                                content = f.read().decode("utf-8")
                                file_contents.append(FileContent(entry, content))
                        except Exception as e:
                            logger.warning(f"Failed to read {entry}: {e}")

                return file_contents

        except Exception as e:
            logger.error(f"Error extracting files from {zip_path}", exc_info=True)
            return e

    @staticmethod
    def _copy_to_local(source_path: str, dest_path: str) -> Optional[Exception]:
        """
        Copy file from source to local destination.

        Args:
            source_path: Source file path (can be remote)
            dest_path: Local destination path

        Returns:
            None if successful, Exception if failed
        """
        try:
            # Try using dbutils if available (Databricks environment)
            try:
                # In Databricks: dbutils.fs.cp(source_path, f"file://{dest_path}")
                from databricks.sdk.dbutils import RemoteDbUtils

                # from pyspark.dbutils import DBUtils

                dbutils = RemoteDbUtils()
                success = dbutils.fs.cp(source_path, f"file://{dest_path}")
                if success:
                    logger.info(
                        f"Successfully copied file from {source_path} to {dest_path}"
                    )
                    return None
                else:
                    raise RuntimeError("Couldn't copy file.")
            except (ImportError, NameError, AttributeError, ValueError):
                # Fallback to hadoop filesystem copy
                # MOCK: Hadoop FileSystem functionality
                # In real implementation: Would use pyarrow.fs or similar for HDFS operations
                parsed_uri = urlparse(source_path)

                if parsed_uri.scheme in ["hdfs", "s3", "gs"]:
                    # For remote filesystems, would use appropriate client libraries
                    raise NotImplementedError(
                        f"Remote filesystem {parsed_uri.scheme} not implemented in mock"
                    )
                else:
                    # For local files, use standard copy
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    return None

        except Exception as exception:
            logger.error(
                f"Failed to copy file from {source_path} to {dest_path}", exc_info=True
            )
            return RuntimeError(
                f"Failed to copy file from {source_path} to {dest_path}", exception
            )

    @staticmethod
    def extract(path: str) -> Union[List[FileContent], Exception]:
        """
        Extract files from an archive at the given path.

        This method handles copying the archive to a local temporary location
        if needed, then extracts code and configuration files.

        Args:
            path: Path to the archive (can be remote)

        Returns:
            List of FileContent objects or Exception if failed
        """
        file_name = os.path.basename(path)
        temp_path = f"/tmp/prophecy/workspaces/package/{file_name}"

        # Ensure directory exists
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)

        # Copy to local if needed
        copy_result = ZipFileExtractor._copy_to_local(path, temp_path)

        if copy_result is not None:
            return copy_result

        # Extract files from the local copy
        return ZipFileExtractor._unzip(temp_path)
