from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple
import json
import gzip
import base64 as base64_std
import re
from typing import Dict, Any

from pyspark.sql import SparkSession

from prophecy.executionmetrics.evolutions.models import (
    MetricsStore,
    StorageMetadata,
)
from prophecy.executionmetrics.schemas.external import MetricsTableNames
from prophecy.executionmetrics.utils.common import (
    timestamp_from_long,
)
from prophecy.executionmetrics.utils.constants import CREATED_AT, CREATED_BY, FABRIC_UID

# --------------------------------------------------------------------------------------
# Helper utilities
# --------------------------------------------------------------------------------------


def create_db_suffix_from_url(url: Optional[str]) -> str:
    """Return a database suffix derived from the provided URL (or a default)."""

    return url or "default"


@dataclass
class Filters:
    """
    Filters class for database query filtering and partitioning.

    This class provides functionality to filter database queries based on various criteria
    such as submission time, run type, fabric ID, and user. It also generates SQL partition
    filter queries.

    Attributes:
        submission_time_lte: Optional maximum submission time (as timestamp)
        run_type: Optional run type filter
        last_uid: Optional last UID for pagination
        fabric_id: Optional fabric ID filter
        db_suffix: Optional database suffix
        created_by: Optional user filter
        metrics_table_names: Metrics table names configuration
        metrics_store: Type of metrics store (default: DeltaStore)
    """

    submission_time_lte: Optional[int] = None
    run_type: Optional[str] = None
    last_uid: Optional[str] = None
    fabric_id: Optional[str] = None
    db_suffix: Optional[str] = None
    created_by: Optional[str] = None
    metrics_table_names: MetricsTableNames = field(default_factory=MetricsTableNames)
    metrics_store: MetricsStore = MetricsStore.DELTA_STORE

    def _timestamp_from_long(self, time: Optional[int]) -> datetime:
        """
        Convert optional timestamp to datetime object.

        Args:
            time: Optional timestamp in milliseconds

        Returns:
            datetime object from timestamp or current time if None
        """
        return timestamp_from_long(time)

    def append_partition_filter_queries(self, table_name: Optional[str] = None) -> str:
        """
        Generate SQL partition filter queries based on the filter criteria.

        This method constructs SQL WHERE clause conditions for filtering based on
        creation time, fabric UID, and created by user.

        Args:
            table_name: Optional table name to prefix columns

        Returns:
            SQL WHERE clause string for partition filtering
        """
        # Determine table prefix for SQL query
        table_prefix_for_query = "" if table_name is None else f"{table_name}."

        # Build creation time filter query
        timestamp = self._timestamp_from_long(self.submission_time_lte)
        and_create_at_query = (
            f" and {table_prefix_for_query}{CREATED_AT} <= '{timestamp.isoformat()}'"
        )

        # Build fabric UID filter query
        and_fabric_uid_query = ""
        if self.fabric_id is not None:
            and_fabric_uid_query = (
                f" and {table_prefix_for_query}{FABRIC_UID} = '{self.fabric_id}' "
            )

        # Build created by filter query
        and_created_by_query = ""
        if self.created_by is not None:
            and_created_by_query = (
                f" and {table_prefix_for_query}{CREATED_BY} = '{self.created_by}' "
            )

        return and_fabric_uid_query + and_create_at_query + and_created_by_query

    @property
    def suffix(self) -> str:
        """
        Get the processed database suffix.

        Returns:
            Processed database suffix string
        """
        return create_db_suffix_from_url(self.db_suffix)

    def get_storage_metadata(
        self,
        spark_session: SparkSession,
        user: str,
        metrics_store: MetricsStore,
        read_only: bool = True,
    ) -> StorageMetadata:
        """
        Get storage metadata configuration.

        Args:
            spark_session: Active Spark session
            user: User identifier
            metrics_store: Type of metrics store
            read_only: Whether access is read-only

        Returns:
            StorageMetadata configuration object
        """
        from prophecy.executionmetrics.evolutions.metrics_storage_initializer import (
            create_storage_metadata,
        )

        return create_storage_metadata(
            spark_session,
            self.metrics_table_names,
            self.suffix,
            user,
            metrics_store,
            read_only,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Filters object to dictionary representation.

        Returns:
            Dictionary representation of the Filters object
        """
        return {
            "submissionTimeLTE": self.submission_time_lte,
            "runType": self.run_type,
            "lastUID": self.last_uid,
            "fabricId": self.fabric_id,
            "dbSuffix": self.db_suffix,
            "createdBy": self.created_by,
            "metricsTableNames": (
                self.metrics_table_names.to_dict()
                if hasattr(self.metrics_table_names, "to_dict")
                else None
            ),
            "metricsStore": self.metrics_store.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Filters":
        """
        Create Filters object from dictionary representation.

        Args:
            data: Dictionary containing filter data

        Returns:
            Filters object created from dictionary data
        """
        # Handle metrics_store enum conversion
        metrics_store = MetricsStore.DELTA_STORE
        if "metricsStore" in data:
            try:
                metrics_store = MetricsStore.from_string(data["metricsStore"])
            except ValueError:
                metrics_store = MetricsStore.DELTA_STORE

        return cls(
            submission_time_lte=data.get("submissionTimeLTE"),
            run_type=data.get("runType"),
            last_uid=data.get("lastUID"),
            fabric_id=data.get("fabricId"),
            db_suffix=data.get("dbSuffix"),
            created_by=data.get("createdBy"),
            metrics_table_names=MetricsTableNames.from_dict(
                data.get("metricsTableNames")
            ),
            metrics_store=metrics_store,
        )

    def to_json(self) -> str:
        """
        Convert Filters object to JSON string.

        Returns:
            JSON string representation of the Filters object
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "Filters":
        """
        Create Filters object from JSON string.

        Args:
            json_str: JSON string containing filter data

        Returns:
            Filters object created from JSON data
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @staticmethod
    def partition_queries(filters: Filters, table_name: Optional[str] = None) -> str:
        """
        Generate partition filter queries for the given filters.

        Args:
            filters: Filters object containing filter criteria
            table_name: Optional table name for column prefixing

        Returns:
            SQL WHERE clause string for partition filtering
        """
        return filters.append_partition_filter_queries(table_name)

    @staticmethod
    def find_db_suffix(filters: Filters) -> str:
        """
        Find and process database suffix from filters.

        Args:
            filters: Filters object containing database suffix

        Returns:
            Processed database suffix string
        """
        return create_db_suffix_from_url(filters.db_suffix)


def compress(s: str) -> str:
    """
    Compress a string using GZIP and encode it to Base64.

    Args:
        s: Input string to compress

    Returns:
        Base64 encoded compressed string
    """
    # Convert string to bytes
    string_bytes = s.encode("utf-8")

    # Compress using gzip
    compressed_bytes = gzip.compress(string_bytes)

    # Encode to Base64
    base64_bytes = base64_std.b64encode(compressed_bytes)

    # Convert back to string
    return base64_bytes.decode("ascii")


def parse_uri(uri: str) -> Optional[Tuple[int, str]]:
    """
    Parse URI and extract project UID and entity path.

    Args:
        uri: The URI string to parse

    Returns:
        Optional tuple of (project_uid, entity_path) or None if no match
    """
    URI_PATTERN = re.compile(r"([0-9]+)/([-_.A-Za-z0-9 /]+)")
    match = URI_PATTERN.match(uri)
    if match:
        project_uid = int(match.group(1))
        entity_path = match.group(2)
        return (project_uid, entity_path)
    return None


def parse_repository_path(uri: str) -> Optional[Tuple[int, str]]:
    """
    Parse repository path and extract project UID and entity path.

    Args:
        uri: The repository path string to parse

    Returns:
        Optional tuple of (project_uid, entity_path) or None if no match
    """
    REPOSITORY_PATH_PATTERN = re.compile(
        r"(https?://[a-z0-9A-Z.\-:]+/[a-z-.A-Z_0-9]+/[a-z.A-Z_0-9-]+[.git]?)/?"
        r"([a-zA-Z0-9._/]+)@([a-z-.A-Z_0-9]+/[a-z-.A-Z_0-9]+)/"
        r"([0-9]+)/(.*)"
    )

    HTTPS_URI_ALL_REPO_PATTERNS = re.compile(
        r"gitUri=(.*)&subPath=(.*)&tag=(.*)&projectSubscriptionProjectId=(.*)&path=(.*)"
    )

    # Try REPOSITORY_PATH_PATTERN first
    match = REPOSITORY_PATH_PATTERN.match(uri)
    if match:
        # Groups: (gitURI, _, releaseTag, projectUID, entityPath)
        project_uid = int(match.group(4))
        entity_path = match.group(5)
        return (project_uid, entity_path)

    # Try HTTPS_URI_ALL_REPO_PATTERNS
    match = HTTPS_URI_ALL_REPO_PATTERNS.match(uri)
    if match:
        # Groups: (gitURI, subPath, tag, projectUID, entityPath)
        project_uid = int(match.group(4))
        entity_path = match.group(5)
        return (project_uid, entity_path)

    return None


def get_entity_uri(uri: str) -> str:
    """
    Get entity URI from the given URI string.

    Args:
        uri: The URI string to process

    Returns:
        The extracted entity URI or the original URI if no pattern matches
    """
    # Try parse_uri first
    result = parse_uri(uri)
    if result is not None:
        return result[1]  # Return entity_path

    # Try parse_repository_path
    result = parse_repository_path(uri)
    if result is not None:
        # Return "projectUID/entityPath" for cross project
        return f"{result[0]}/{result[1]}"

    # Return original URI if no pattern matches
    return uri


def check_if_entities_are_same(id1: str, id2: str) -> bool:
    """
    Check if two entity IDs represent the same entity.
    Supports cross project and same project with backward compatibility.

    Args:
        id1: First entity ID
        id2: Second entity ID

    Returns:
        True if entities are the same, False otherwise
    """
    uri = get_entity_uri(id1)
    parsed_uri = get_entity_uri(id2)

    return uri == parsed_uri or uri == id2 or parsed_uri == id1


def add_project_id_to_prophecy_uri(uri: str, project_id_opt: Optional[str]) -> str:
    parts = parse_uri(uri)
    if parts and project_id_opt:
        return f"{project_id_opt}/{parts[1]}"

    res = parse_repository_path(uri)
    if res:
        return f"{res[0]}/{res[1]}"

    return f"{project_id_opt}/{uri}" if project_id_opt else uri
