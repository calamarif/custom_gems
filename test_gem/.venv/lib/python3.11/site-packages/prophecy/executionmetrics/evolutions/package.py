"""
Evolutions package for execution metrics.

This module handles schema evolution for execution metrics tables,
providing mechanisms to upgrade table schemas as needed.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Type, TypeVar

from pyspark.sql import SparkSession
from pyspark.sql.types import StructType

from prophecy.executionmetrics.utils.constants import (
    GEM_NAME,
    PROCESS_ID,
    GEM_TYPE,
    INPUT_GEMS,
    OUTPUT_GEMS,
    IN_PORTS,
    OUT_PORTS,
    NUM_ROWS_OUTPUT,
    NUM_ROWS,
    STDOUT,
    STDERR,
    START_TIME,
    END_TIME,
    STATE,
    EXCEPTION,
    FROM_PORT,
    TO_PORT,
    EXCEPTION_TYPE,
    MSG,
    CAUSE_MSG,
    STACK_TRACE,
    TIME,
    CONTENT,
)

logger = logging.getLogger(__name__)


class ExecutionMetricsSchema(ABC):
    """Base class for execution metrics schema types."""

    pass


class PipelineRunsSchema(ExecutionMetricsSchema):
    """Schema type for pipeline runs."""

    pass


class ComponentRunsSchema(ExecutionMetricsSchema):
    """Schema type for component runs."""

    pass


class InterimsSchema(ExecutionMetricsSchema):
    """Schema type for interims."""

    pass


class SchemaEvolution(ABC):
    """
    Abstract base class for schema evolution operations.

    Each evolution knows how to check if it's required and how to apply itself.
    """

    @abstractmethod
    def required(self, schema: StructType) -> bool:
        """Check if this evolution is required for the given schema."""
        pass

    @abstractmethod
    def up(self, fqtn: str) -> str:
        """
        Generate SQL statement to apply this evolution.

        Args:
            fqtn: Fully qualified table name

        Returns:
            SQL ALTER TABLE statement
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this evolution."""
        pass


class InstrumentationEvolution(SchemaEvolution, ComponentRunsSchema):
    """
    Evolution to add instrumentation columns to component runs table.

    This evolution adds columns for detailed gem execution tracking including
    inputs, outputs, stdout/stderr, timing, and exception information.
    """

    @property
    def name(self) -> str:
        return "Instrumentation"

    def required(self, schema: StructType) -> bool:
        """Check if gem_name column exists in schema."""
        field_names = [field.name for field in schema.fields]
        return GEM_NAME not in field_names

    def up(self, fqtn: str) -> str:
        """Generate ALTER TABLE statement to add instrumentation columns."""
        return f"""
ALTER TABLE {fqtn} ADD COLUMNS (
{GEM_NAME} STRING,
{PROCESS_ID} STRING,
{GEM_TYPE} STRING,
{INPUT_GEMS} ARRAY<STRUCT<{GEM_NAME}: STRING, {FROM_PORT}: STRING, {TO_PORT}: STRING, {NUM_ROWS}: BIGINT>>,
{OUTPUT_GEMS} ARRAY<STRUCT<{GEM_NAME}: STRING, {FROM_PORT}: STRING, {TO_PORT}: STRING, {NUM_ROWS}: BIGINT>>,
{IN_PORTS} ARRAY<STRING>,
{OUT_PORTS} ARRAY<STRING>,
{NUM_ROWS_OUTPUT} BIGINT,
{STDOUT} ARRAY<STRUCT<{CONTENT}: STRING, {TIME}: BIGINT>>,
{STDERR} ARRAY<STRUCT<{CONTENT}: STRING, {TIME}: BIGINT>>,
{START_TIME} BIGINT,
{END_TIME} BIGINT,
{STATE} STRING,
{EXCEPTION} STRUCT<{EXCEPTION_TYPE}: STRING, {MSG}: STRING, {CAUSE_MSG}: STRING, {STACK_TRACE}: STRING, {TIME}: BIGINT>
);
"""


class SchemaEvolutionRegistry:
    """
    Registry for all schema evolutions.

    This class manages all available schema evolutions and provides
    methods to find and apply them.
    """

    # All registered evolutions
    _evolutions: List[SchemaEvolution] = [InstrumentationEvolution()]

    @classmethod
    def values(cls) -> List[SchemaEvolution]:
        """Get all registered schema evolutions."""
        return cls._evolutions

    @classmethod
    def evolutions(
        cls, schema_type: Type[ExecutionMetricsSchema]
    ) -> List[SchemaEvolution]:
        """
        Get evolutions for a specific schema type.

        Args:
            schema_type: The type of schema to get evolutions for

        Returns:
            List of evolutions that apply to the given schema type
        """
        return [
            evolution
            for evolution in cls._evolutions
            if isinstance(evolution, schema_type)
        ]


def perform_up_evolutions(
    spark: SparkSession, fqtn: str, schema_type: Type[ExecutionMetricsSchema]
) -> None:
    """
    Perform all required schema evolutions on a table.

    This function checks which evolutions are needed for the given table
    and applies them in order. Failures are logged but don't stop the process.

    Args:
        spark: SparkSession to use for executing SQL
        fqtn: Fully qualified table name
        schema_type: Type of schema to evolve (e.g., ComponentRunsSchema)
    """
    try:
        # Get current table schema
        schema = spark.table(fqtn).schema

        # Get applicable evolutions for this schema type
        evolutions = SchemaEvolutionRegistry.evolutions(schema_type)

        for evolution in evolutions:
            try:
                if evolution.required(schema):
                    # Apply the evolution
                    sql_statement = evolution.up(fqtn)
                    logger.info(
                        f"Applying evolution '{evolution.name}' on table {fqtn}"
                    )
                    logger.debug(f"SQL: {sql_statement}")

                    spark.sql(sql_statement)
                    logger.info(
                        f"Successfully applied evolution '{evolution.name}' on table {fqtn}"
                    )
                else:
                    logger.info(
                        f"Evolution '{evolution.name}' is not required for table {fqtn}"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to apply evolution '{evolution.name}' on table {fqtn}",
                    exc_info=e,
                )

    except Exception as e:
        logger.error(f"Failed to get schema for table {fqtn}", exc_info=e)


# Type variable for generic schema type constraints
T = TypeVar("T", bound=ExecutionMetricsSchema)


def get_evolutions_for_schema(schema_type: Type[T]) -> List[SchemaEvolution]:
    """
    Get all evolutions for a specific schema type.

    This is a convenience function that provides type-safe access to evolutions.

    Args:
        schema_type: The schema type to get evolutions for

    Returns:
        List of evolutions applicable to the schema type
    """
    return SchemaEvolutionRegistry.evolutions(schema_type)


def check_evolution_required(
    spark: SparkSession, fqtn: str, evolution: SchemaEvolution
) -> bool:
    """
    Check if a specific evolution is required for a table.

    Args:
        spark: SparkSession to use
        fqtn: Fully qualified table name
        evolution: Evolution to check

    Returns:
        True if evolution is required, False otherwise
    """
    try:
        schema = spark.table(fqtn).schema
        return evolution.required(schema)
    except Exception as e:
        logger.error(
            f"Failed to check if evolution '{evolution.name}' is required for {fqtn}",
            exc_info=e,
        )
        return False


def apply_single_evolution(
    spark: SparkSession, fqtn: str, evolution: SchemaEvolution
) -> bool:
    """
    Apply a single evolution to a table.

    Args:
        spark: SparkSession to use
        fqtn: Fully qualified table name
        evolution: Evolution to apply

    Returns:
        True if successful, False otherwise
    """
    try:
        if not check_evolution_required(spark, fqtn, evolution):
            logger.info(
                f"Evolution '{evolution.name}' is not required for table {fqtn}"
            )
            return True

        sql_statement = evolution.up(fqtn)
        logger.info(f"Applying evolution '{evolution.name}' on table {fqtn}")
        spark.sql(sql_statement)
        logger.info(
            f"Successfully applied evolution '{evolution.name}' on table {fqtn}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to apply evolution '{evolution.name}' on table {fqtn}", exc_info=e
        )
        return False
