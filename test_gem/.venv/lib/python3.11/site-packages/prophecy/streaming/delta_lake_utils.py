from pyspark.sql.functions import *
from pyspark.sql import DataFrame
from pyspark.sql.types import *
from typing import List
from delta.tables import DeltaMergeBuilder, DeltaTable


def deltaLakeMergeForEachBatch(originalDataset: DeltaTable, props: dict):
    def wrapper(batchDF: DataFrame, batchId: int):
        if props.get("writeMode") == "merge":

            dt = originalDataset.alias(props.get("mergeTargetAlias")) \
                .merge(batchDF.alias(props.get("mergeSourceAlias")), props.get("mergeCondition"))
            resMatched: DeltaMergeBuilder = dt

            if props.get("matchedActionDelete") == "delete":
                if props.get("matchedConditionDelete") is not None:
                    resMatched = resMatched.whenMatchedDelete(condition=props.get("matchedConditionDelete"))
                else:
                    resMatched = resMatched.whenMatchedDelete()

            if props.get("matchedAction") == "update":

                if props.get("matchedCondition") is not None:
                    if len(props.get("matchedTable")) > 0:
                        resMatched = resMatched.whenMatchedUpdate(
                            condition=props.get("matchedCondition"),
                            set=props.get("matchedTable"))
                    else:
                        resMatched = resMatched.whenMatchedUpdateAll(
                            condition=props.get("matchedCondition"))
                else:
                    if len(props.get("matchedTable")) > 0:
                        resMatched = resMatched.whenMatchedUpdate(set=props.get("matchedTable"))
                    else:
                        resMatched = resMatched.whenMatchedUpdateAll()

            if props.get("notMatchedAction") is not None:
                if props.get("notMatchedAction") == "insert":
                    if props.get("notMatchedCondition") is not None:
                        if len(props.get("notMatchedTable")) > 0:
                            resMatched = resMatched.whenNotMatchedInsert(
                                condition=props.get("notMatchedCondition"),

                                values=props.get("notMatchedTable"))
                        else:
                            resMatched = resMatched.whenNotMatchedInsertAll(
                                condition=props.get("notMatchedCondition"))
                    else:
                        if len(props.get("notMatchedTable")) > 0:
                            resMatched = resMatched.whenNotMatchedInsert(values=props.get("notMatchedTable"))
                        else:
                            resMatched = resMatched.whenNotMatchedInsertAll()

            resMatched.execute()
        elif props.get("writeMode") == "merge_scd2":
            keyColumns = props.get("keyColumns")
            scdHistoricColumns = props.get("historicColumns")
            fromTimeColumn = props.get("fromTimeCol")
            toTimeColumn = props.get("toTimeCol")
            minFlagColumn = props.get("minFlagCol")
            maxFlagColumn = props.get("maxFlagCol")
            flagY = "1"
            flagN = "0"
            if props.get("flagValue") == "boolean":
                flagY = "true"
                flagN = "false"

            updatesDF: DataFrame = batchDF.withColumn(minFlagColumn, lit(flagY)).withColumn(maxFlagColumn, lit(flagY))
            updateColumns: List[str] = updatesDF.columns
            existingTable: DeltaTable = originalDataset
            existingDF: DataFrame = existingTable.toDF()

            cond = None
            for scdCol in scdHistoricColumns:
                if cond is None:
                    cond = (existingDF[scdCol] != updatesDF[scdCol])
                else:
                    cond = (cond | (existingDF[scdCol] != updatesDF[scdCol]))

            rowsToUpdate = updatesDF \
                .join(existingDF, keyColumns) \
                .where(
                (existingDF[maxFlagColumn] == lit(flagY)) & (
                    cond
                )) \
                .select(*[updatesDF[val] for val in updateColumns]) \
                .withColumn(minFlagColumn, lit(flagN))

            stagedUpdatesDF: DataFrame = rowsToUpdate \
                .withColumn("mergeKey", lit(None)) \
                .union(updatesDF.withColumn("mergeKey", concat(*keyColumns)))

            updateCond = None
            for scdCol in scdHistoricColumns:
                if updateCond is None:
                    updateCond = (existingDF[scdCol] != stagedUpdatesDF[scdCol])
                else:
                    updateCond = (updateCond | (existingDF[scdCol] != stagedUpdatesDF[scdCol]))

            existingTable \
                .alias("existingTable") \
                .merge(
                stagedUpdatesDF.alias("staged_updates"),
                concat(*[existingDF[key] for key in keyColumns]) == stagedUpdatesDF["mergeKey"]
            ) \
                .whenMatchedUpdate(
                condition=(existingDF[maxFlagColumn] == lit(flagY)) & updateCond,
                set={
                    maxFlagColumn: flagN,
                    toTimeColumn: ("staged_updates." + fromTimeColumn)
                }
            ).whenNotMatchedInsertAll() \
                .execute()

    return wrapper
