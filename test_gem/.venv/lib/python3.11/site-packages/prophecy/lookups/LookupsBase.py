# WARNING - Do not add import * in this module

from typing import List, Optional

from pyspark.sql import SparkSession, Column, DataFrame

import prophecy.lookups.LookupsNative
from prophecy.lookups.LookupsNative import LookupCondition as LookupConditionNative


class LookupsBase:
    sparkSession = None
    UDFUtils = None
    can_access_jvm = True

    def __init__(self, spark):
        try:
            self.UDFUtils = spark.sparkContext._jvm.io.prophecy.libs.python.UDFUtils
        except:
            self.can_access_jvm = False
        self.sparkSession = spark


lookupConfig: Optional[LookupsBase] = None

LookupCondition = LookupConditionNative  # For backward compat


def initializeLookups(spark):
    global lookupConfig
    if lookupConfig is None:
        lookupConfig = LookupsBase(spark)
    return lookupConfig


def createScalaList(_list, spark):
    return spark.sparkContext._jvm.PythonUtils.toList(_list)


def createLookup(
        name: str,
        df: DataFrame,
        spark: SparkSession,
        keyCols: List[str],
        valueCols: List[str],
):
    initializeLookups(spark)
    if (lookupConfig.can_access_jvm):
        keyColumns = createScalaList(keyCols, spark)
        valueColumns = createScalaList(valueCols, spark)
        lookupConfig.UDFUtils.createLookup(
            name, df._jdf, spark._jsparkSession, keyColumns, valueColumns
        )
    else:
        prophecy.lookups.LookupsNative.createLookup(
            name,
            df,
            spark,
            keyCols,
            valueCols
        )


def createRangeLookup(
        name: str,
        df: DataFrame,
        spark: SparkSession,
        minColumn: str,
        maxColumn: str,
        valueColumns: List[str],
):
    initializeLookups(spark)
    if (lookupConfig.can_access_jvm):
        valueColumns = createScalaList(valueColumns, spark)
        lookupConfig.UDFUtils.createRangeLookup(
            name, df._jdf, spark._jsparkSession, minColumn, maxColumn, valueColumns
        )
    else:
        prophecy.lookups.LookupsNative.createRangeLookup(
            name,
            df,
            spark,
            minColumn,
            maxColumn,
            valueColumns
        )


def createScalaConditionsList(conditions: List[LookupCondition], spark):
    scalaConditions = []
    for condition in conditions:
        sConditions = lookupConfig.UDFUtils.LookupCondition(condition.lookupColumn, condition.comparisonOp,
                                                            condition.inputParam)
        scalaConditions.append(sConditions)
    return spark.sparkContext._jvm.PythonUtils.toList(scalaConditions)


def createExtendedLookup(
        name: str,
        df: DataFrame,
        spark: SparkSession,
        conditions: List[LookupCondition],
        inputParams: List[str],
        valueColumns: List[str],
):
    if (lookupConfig.can_access_jvm):
        initializeLookups(spark)
        conditions = createScalaConditionsList(conditions, spark)
        inputParams = createScalaList(inputParams, spark)
        valueColumns = createScalaList(valueColumns, spark)

        lookupConfig.UDFUtils.createExtendedLookup(
            name, df._jdf, spark._jsparkSession, conditions, inputParams, valueColumns
        )
    else:
        prophecy.lookups.LookupsNative.createExtendedLookup(name, df, spark, conditions, inputParams, valueColumns)


def lookup(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if (lookupConfig.can_access_jvm):
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup(lookupName, *cols)


def extended_lookup(lookupName: str, *cols):
    if (lookupConfig.can_access_jvm):
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.extended_lookup(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.extended_lookup(lookupName, *cols)


def lookup_last(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_last(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_last(lookupName, *cols)


def lookup_match(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_match(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_match(lookupName, *cols)


def lookup_count(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_count(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_count(lookupName, *cols)


def lookup_row(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_row(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_row(lookupName, *cols)


def lookup_row_reverse(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_row_reverse(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_row_reverse(lookupName, *cols)


def lookup_nth(lookupName: str, *cols):
    if lookupConfig is None:
        raise Exception(f"Lookup: `{lookupName}` is being used but not initialised.")
    if lookupConfig.can_access_jvm:
        _cols = createScalaList(
            [item._jc for item in list(cols)], lookupConfig.sparkSession
        )
        lookupResult = lookupConfig.UDFUtils.lookup_nth(lookupName, _cols)
        return Column(lookupResult)
    else:
        return prophecy.lookups.LookupsNative.lookup_nth(lookupName, *cols)
