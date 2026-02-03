from pyspark.sql import DataFrame
from pyspark.sql.functions import lit

from prophecy.libs.utils import createScalaOption, createScalaList
from prophecy.utils import ProphecyDataFrame
from prophecy.utils.transpiler.abi_base import ScalaUtil
from prophecy.libs.uc_shared_utils import directory_listing
from pyspark.sql.types import StructType, StructField, StringType


def readFixedFile(schema, path,
                  skipHeaderLines=0,
                  skipFooterLines=0,
                  parallelism=1,
                  tmpDir="temp",
                  bufferSize=4096):
    spark = ScalaUtil.getAbiLib().spark
    df = spark.sparkContext._jvm.io.prophecy.libs.FixedFileFormatImplicits.readFixedFile(spark._jsparkSession, schema,
                                                                                         path, skipHeaderLines,
                                                                                         skipFooterLines, parallelism,
                                                                                         tmpDir, bufferSize)
    return DataFrame(df, ScalaUtil.getAbiLib().sqlContext)


def writeFixedFile(df, schema, path, mode="overwrite"):
    spark = ScalaUtil.getAbiLib().spark
    spark.sparkContext._jvm.io.prophecy.libs.FixedFileFormatImplicits.writeFixedFile(df._jdf, schema, path,
                                                                                     createScalaOption(spark, None),
                                                                                     createScalaOption(spark, None),
                                                                                     createScalaOption(spark, None),
                                                                                     _getSaveMode(spark, mode))

def flattenSchema(df, jsonParsedColumnName, distributeColumnsOnType):
    spark = ScalaUtil.getAbiLib().spark
    result = spark.sparkContext._jvm.io.prophecy.alteryx.SparkFunctions.flattenSchema(df._jdf, jsonParsedColumnName, distributeColumnsOnType, spark._jsparkSession)
    return DataFrame(result, ScalaUtil.getAbiLib().sqlContext)

def parseXML(df, xmlStringColumnName, childName, attributeOrChildValues, spark):
    result = spark.sparkContext._jvm.io.prophecy.alteryx.SparkFunctions.parseXML(df._jdf, xmlStringColumnName, childName, createScalaList(spark, attributeOrChildValues), spark._jsparkSession)
    return DataFrame(result, ScalaUtil.getAbiLib().sqlContext)

def buildJson(df, groupByColumns, nameFieldColumn, valueFieldColumn, outputColumn, spark):
    result = spark.sparkContext._jvm.io.prophecy.alteryx.SparkFunctions.buildJson(df._jdf, createScalaList(spark, groupByColumns), nameFieldColumn, valueFieldColumn, outputColumn, spark._jsparkSession)
    return DataFrame(result, ScalaUtil.getAbiLib().sqlContext)

def buildJsonFromPrimitiveCols(df, groupByColumns, nameFieldColumn, stringFieldColumnName, intFieldColumnName, floatFieldColumnName, boolFieldColumnName, outputColumn, spark):
    result = spark.sparkContext._jvm.io.prophecy.alteryx.SparkFunctions.buildJsonFromPrimitiveCols(df._jdf, createScalaList(spark, groupByColumns), nameFieldColumn, stringFieldColumnName, intFieldColumnName, floatFieldColumnName, boolFieldColumnName, outputColumn, spark._jsparkSession)
    return DataFrame(result, ScalaUtil.getAbiLib().sqlContext)

def _getSaveMode(spark, mode):
    if mode == "ignore":
        return spark.sparkContext._jvm.org.apache.spark.sql.SaveMode.Ignore
    elif mode == "append":
        return spark.sparkContext._jvm.org.apache.spark.sql.SaveMode.Append
    elif mode == "overwrite":
        return spark.sparkContext._jvm.org.apache.spark.sql.SaveMode.Overwrite

    return spark.sparkContext._jvm.org.apache.spark.sql.SaveMode.ErrorIfExists


def getMTimeDataframe(filepath, format, spark) -> DataFrame:
    try:
        df = ScalaUtil.getAbiLib().libs.getMTimeDataframe(filepath, format, spark._jsparkSession)
        return DataFrame(df, ScalaUtil.getAbiLib().sqlContext)
    except Exception as e:
        dirPath = '/'.join(filepath.split("/")[0:-1])
        fileName = filepath.split("/")[-1]
        df = directory_listing(spark, dirPath , False, fileName)
        if df.count() > 0:
            modification_time = df.select("modification_time").collect()[0][0]
            modification_time = modification_time.strftime(format)
            formatted_df=spark.createDataFrame([(filepath, modification_time)], ["file", "mtime"])
            return formatted_df
        else:
            schema = StructType([
                StructField("file", StringType(), True),
                StructField("mtime", StringType(), True)
            ])
            return spark.createDataFrame([], schema=schema)


def getEmptyLogDataFrame(spark) -> DataFrame:
    df = ScalaUtil.getAbiLib().libs.getEmptyLogDataFrame(spark._jsparkSession)
    return DataFrame(df, ScalaUtil.getAbiLib().sqlContext)


def collectDataFrameColumnsToApplyFilter(
        df,
        spark,
        columnList,
        filterSourceDataFrame
) -> DataFrame:
    return ProphecyDataFrame(df, spark).collectDataFrameColumnsToApplyFilter(
        columnList,
        filterSourceDataFrame
    )


def normalize(
        df,
        spark,
        lengthExpression,
        finishedExpression,
        finishedCondition,
        alias,
        colsToSelect,
        tempWindowExpr,
        lengthRelatedGlobalExpressions={},
        normalizeRelatedGlobalExpressions={},
        sparkSession = None
) -> DataFrame:
    return ProphecyDataFrame(df, spark).normalize(
        lengthExpression,
        finishedExpression,
        finishedCondition,
        alias,
        colsToSelect,
        tempWindowExpr,
        lengthRelatedGlobalExpressions,
        normalizeRelatedGlobalExpressions,
        sparkSession
    )


def denormalizeSorted(
        df,
        spark,
        groupByColumns,
        orderByColumns,
        denormalizeRecordExpression,
        finalizeExpressionMap,
        inputFilter,
        outputFilter,
        denormColumnName,
        countColumnName="count") -> DataFrame:
    return ProphecyDataFrame(df, spark).denormalizeSorted(
        groupByColumns,
        orderByColumns,
        denormalizeRecordExpression,
        finalizeExpressionMap,
        inputFilter,
        outputFilter,
        denormColumnName,
        countColumnName)


def readSeparatedValues(
        df,
        spark,
        inputColumn,
        outputSchemaColumns,
        recordSeparator,
        fieldSeparator
) -> DataFrame:
    return ProphecyDataFrame(df, spark).readSeparatedValues(
        inputColumn,
        outputSchemaColumns,
        recordSeparator,
        fieldSeparator
    )


def syncDataFrameColumnsWithSchema(df, spark, columnNames) -> DataFrame:
    return ProphecyDataFrame(df, spark).syncDataFrameColumnsWithSchema(columnNames)


def fuzzyDedup(
        df, dedupColumnName, threshold, spark, algorithm
) -> DataFrame:
    return ProphecyDataFrame(df, spark).fuzzyDedup(
        dedupColumnName,
        threshold,
        spark,
        algorithm,
    )


def fuzzyPurgeMode(
        df, spark, recordId, threshold, matchFields, includeSimilarityScore=False
) -> DataFrame:
    return ProphecyDataFrame(df, spark).fuzzyPurgeMode(
        recordId=recordId,
        threshold=threshold,
        matchFields=matchFields,
        includeSimilarityScore=includeSimilarityScore
    )


def fuzzyMergeMode(
        df, spark, recordId, sourceId, threshold, matchFields, includeSimilarityScore=False
) -> DataFrame:
    return ProphecyDataFrame(df, spark).fuzzyMergeMode(
        recordId=recordId,
        sourceId=sourceId,
        threshold=threshold,
        matchFields=matchFields,
        includeSimilarityScore=includeSimilarityScore
    )


def zipWithIndex(
        df,
        startValue,
        incrementBy,
        indexColName,
        sparkSession
) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).zipWithIndex(
        startValue,
        incrementBy,
        indexColName,
        sparkSession
    )


def metaPivot(
        df,
        pivotColumns,
        nameField,
        valueField,
        sparkSession
) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).metaPivot(
        pivotColumns,
        nameField,
        valueField,
        sparkSession
    )


def dynamicReplaceExpr(df, rulesDf, rulesOrderBy, baseColName, replacementExpressionColumnName, replacementValueColumnName, sparkSession) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).dynamicReplaceExpr(rulesDf._jdf, rulesOrderBy, baseColName, replacementExpressionColumnName, replacementValueColumnName, sparkSession)

def dynamicReplace(df, rulesDf, rulesOrderBy, baseColName, replacementExpressionColumnName, replacementValueColumnName, sparkSession) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).dynamicReplace(rulesDf._jdf, rulesOrderBy, baseColName, replacementExpressionColumnName, replacementValueColumnName, sparkSession)

def evaluate_expression(df, userExpression, selectedColumnNames, sparkSession) -> DataFrame:
    try:
        if sparkSession.sparkContext.emptyRDD():
            return ProphecyDataFrame(df, sparkSession).evaluate_expression(userExpression, selectedColumnNames, sparkSession)
    except AttributeError as ex:
        """
            Changes: For Shared UC cluster compatibility
        """
        from prophecy.libs.uc_shared_utils import evaluate_expression as shared_evaluate_expression
        return shared_evaluate_expression(dataframe=df,
                                          user_expression=userExpression,
                                          selected_column_names=selectedColumnNames,
                                          spark=sparkSession)


def compareRecords(df, otherDataFrame, componentName, limit, sparkSession) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).compareRecords(otherDataFrame, componentName, limit, sparkSession)


def generateSurrogateKeys(
        df,
        keyDF,
        naturalKeys,
        surrogateKey,
        overrideSurrogateKeys,
        computeOldPortOutput,
        spark
) -> (DataFrame, DataFrame, DataFrame):
    return ProphecyDataFrame(df, spark).generateSurrogateKeys(
        keyDF,
        naturalKeys,
        surrogateKey,
        overrideSurrogateKeys,
        computeOldPortOutput,
        spark
    )


def generateLogOutput(
        df,
        sparkSession,
        componentName,
        subComponentName="",
        perRowEventTypes=None,
        perRowEventTexts=None,
        inputRowCount=0,
        outputRowCount=0,
        finalLogEventType=None,
        finalLogEventText=None,
        finalEventExtraColumnMap={}
) -> DataFrame:
    return ProphecyDataFrame(df, sparkSession).generateLogOutput(
        componentName,
        subComponentName,
        perRowEventTypes,
        perRowEventTexts,
        inputRowCount,
        outputRowCount,
        finalLogEventType,
        finalLogEventText,
        finalEventExtraColumnMap,
        sparkSession
    )


def mergeMultipleFileContentInDataFrame(
        df,
        fileNameDF,
        spark,
        delimiter,
        readFormat,
        joinWithInputDataframe,
        outputSchema=None,
        ffSchema=None,
        abinitioSchema=None
) -> DataFrame:
    return ProphecyDataFrame(df, spark).mergeMultipleFileContentInDataFrame(
        fileNameDF,
        spark,
        delimiter,
        readFormat,
        joinWithInputDataframe,
        outputSchema,
        ffSchema,
        abinitioSchema
    )


def breakAndWriteDataFrameForOutputFile(
        df,
        spark,
        outputColumns,
        fileColumnName,
        format,
        delimiter
):
    ProphecyDataFrame(df, spark).breakAndWriteDataFrameForOutputFile(
        outputColumns,
        fileColumnName,
        format,
        delimiter
    )


def breakAndWriteDataFrameForOutputFileWithSchema(
        df,
        spark,
        outputSchema,
        fileColumnName,
        format,
        delimiter=None
):
    ProphecyDataFrame(df, spark).breakAndWriteDataFrameForOutputFileWithSchema(
        outputSchema,
        fileColumnName,
        format,
        delimiter
    )


def readInputFile(spark,
                  inputPath,
                  ffSchemaString,
                  formatType="fixedFormat",
                  delimiter=",",
                  sparkSchema="") -> DataFrame:
    df = ScalaUtil.getAbiLib().libs.readInputFile(spark._jsparkSession, inputPath, ffSchemaString, formatType,
                                                  delimiter, sparkSchema)
    return DataFrame(df, ScalaUtil.getAbiLib().sqlContext)


def writeToOutputFile(
        df,
        spark,
        outputPath,
        ffSchema,
        formatType="fixedFormat",
        delimiter=","
):
    ProphecyDataFrame(df, spark).writeToOutputFile(
        outputPath,
        ffSchema,
        formatType,
        delimiter
    )


def deduplicate(
        df,
        spark,
        typeToKeep,
        groupByColumns=None,
        orderByColumns=None
):
    if groupByColumns is None:
        groupByColumns = [lit(1)]
    if orderByColumns is None:
        orderByColumns = [lit(1)]
    ProphecyDataFrame(df, spark).deduplicate(
        typeToKeep, groupByColumns, orderByColumns
    )

def generate_xml(df, rootElement, namespacePrefixes, namespaceURIs, columnNames, xmlPaths, isAttributes, writeNilElement, schemaLocation=None):
    spark = df.sparkSession
    sc = spark.sparkContext
    
    java_namespacePrefixes = sc._jvm.java.util.ArrayList()
    for item in namespacePrefixes:
        java_namespacePrefixes.add(item)
    
    java_namespaceURIs = sc._jvm.java.util.ArrayList()
    for item in namespaceURIs:
        java_namespaceURIs.add(item)
    
    java_columnNames = sc._jvm.java.util.ArrayList()
    for item in columnNames:
        java_columnNames.add(item)
    
    java_xmlPaths = sc._jvm.java.util.ArrayList()
    for item in xmlPaths:
        java_xmlPaths.add(item)
    
    java_isAttributes = sc._jvm.java.util.ArrayList()
    for item in isAttributes:
        java_isAttributes.add(item)

    namespacePrefixes_seq = sc._jvm.scala.collection.JavaConverters.asScalaBufferConverter(java_namespacePrefixes).asScala().toSeq()
    namespaceURIs_seq = sc._jvm.scala.collection.JavaConverters.asScalaBufferConverter(java_namespaceURIs).asScala().toSeq()
    columnNames_seq = sc._jvm.scala.collection.JavaConverters.asScalaBufferConverter(java_columnNames).asScala().toSeq()
    xmlPaths_seq = sc._jvm.scala.collection.JavaConverters.asScalaBufferConverter(java_xmlPaths).asScala().toSeq()
    isAttributes_seq = sc._jvm.scala.collection.JavaConverters.asScalaBufferConverter(java_isAttributes).asScala().toSeq()

    if schemaLocation is not None:
        schemaLocation_opt = sc._jvm.scala.Some(schemaLocation)
    else:
        schemaLocation_opt = sc._jvm.scala.Option.apply(None)

    result = sc._jvm.io.prophecy.datastage.SparkFunctions.generate_xml(
        df._jdf,
        rootElement,
        namespacePrefixes_seq,
        namespaceURIs_seq,
        columnNames_seq,
        xmlPaths_seq,
        isAttributes_seq,
        writeNilElement,
        schemaLocation_opt
    )

    return result
