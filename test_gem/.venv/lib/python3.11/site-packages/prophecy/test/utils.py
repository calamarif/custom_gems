import json
from datetime import datetime
from decimal import Decimal

from pyspark.sql import *
from pyspark.sql.functions import *
from pyspark.sql.types import *
from typing import Optional


def readResource(path: str) -> str:
    f = open(path, "r")
    content = f.read()
    f.close()
    return content


def defaultForDatatype(type: DataType):
    if isinstance(type, StringType):
        return ""
    elif (
            isinstance(type, IntegerType)
            or isinstance(type, ShortType)
            or isinstance(type, LongType)
    ):
        return 0
    elif isinstance(type, ByteType):
        return 0
    elif isinstance(type, FloatType) or isinstance(type, DoubleType):
        return 0.0
    elif isinstance(type, BinaryType):
        return bytearray(0)
    elif isinstance(type, BooleanType):
        return False
    elif isinstance(type, DateType):
        return datetime.now()
    elif isinstance(type, TimestampType):
        return datetime.now()
    elif isinstance(type, DecimalType):
        return Decimal(0)
    elif isinstance(type, ArrayType):
        return []
    elif isinstance(type, NullType):
        return None
    elif isinstance(type, MapType):
        return {}
    elif isinstance(type, StructType):
        fields = {}
        for field in type.fields:
            fields[field.name] = defaultForDatatype(field.dataType)
        return fields
    else:
        try:
            # Only applicable for pyspark >= 3.4
            if isinstance(type, TimestampNTZType):
                return datetime.now()
            else:
                raise Exception()
        except Exception:
                raise Exception(f"default value for datatype: {type} not found")


def defaultsForSchema(schema: StructType):
    pairs = list(map(lambda f: (f.name, defaultForDatatype(f.dataType)), schema.fields))
    return dict(pairs)


def isNull(value):
    return value == "" or value == "null"


def isNullTypeValue(value):
    return value == None


def convertToDatetime(dateString: str) -> datetime:
    formats = [
        # with timezone
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        # without timezone
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        # date
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(dateString, fmt)
        except ValueError:
            continue

    raise ValueError(f"Date string '{dateString}' does not match any known formats.")


def convertStringValueToDatatype(dataType: DataType, value: Optional[str]):
    # Do not remove these, when we do eval("[true, false, true]") our parsing fails as it doesn't find variables named true/false.
    # When we dump interim data we dump the string json equivalent of it, so it fails.
    true = True
    false = False
    if isinstance(dataType, StringType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = value
    elif (
            isinstance(dataType, IntegerType)
            or isinstance(dataType, ShortType)
            or isinstance(dataType, LongType)
    ):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = 0 if isNull(value) else int(value)
    elif isinstance(dataType, ByteType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = 0 if isNull(value) else int(value)
    elif isinstance(dataType, FloatType) or isinstance(dataType, DoubleType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = 0.0 if isNull(value) else float(value)
    elif isinstance(dataType, BinaryType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = bytearray(0) if isNull(value) else bytearray(value.encode("utf-8"))
    elif isinstance(dataType, BooleanType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = False if isNull(value) else (value == "true")
    elif isinstance(dataType, NullType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = None
    elif isinstance(dataType, DateType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = (
                datetime.now() if isNull(value) else datetime.strptime(value, "%Y-%m-%d")
            )
    elif isinstance(dataType, TimestampType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = (
                # Don't do datetime.now() as it will lead to different microsecond values in case of `NULL` types.
                datetime(1970, 1, 1, 0, 0, 0, 0)
                if isNull(value)
                else convertToDatetime(value)
            )
    elif isinstance(dataType, DecimalType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = Decimal(0) if isNull(value) else Decimal(value)
    elif isinstance(dataType, ArrayType):
        if isNullTypeValue(value):
            newValue = None
        else:
            value_list = [] if (isNull(value)) else value if isinstance(value, list) else list(eval(value))
            newValue = [convertStringValueToDatatype(dataType.elementType, element) for element in value_list]
    elif isinstance(dataType, StructType):
        if isNullTypeValue(value):
            newValue = None
        else:
            newValue = {}
            for structFieldElement in dataType.fields:
                fieldName = structFieldElement.name
                value_dict = dict() if (isNull(value)) else value if isinstance(value, dict) else dict(eval(value))
                fieldValue = "null"
                if fieldName in value_dict.keys():
                    fieldValue = value_dict.get(fieldName)
                newValue[fieldName] = convertStringValueToDatatype(structFieldElement.dataType, fieldValue)
    else:
        try:
            # Only applicable for pyspark >= 3.4
            if isinstance(dataType, TimestampNTZType):
                if isNullTypeValue(value):
                    newValue = None
                else:
                    newValue = (
                        # Don't do datetime.now() as it will lead to different microsecond values in case of `NULL` types.
                        datetime(1970, 1, 1, 0, 0, 0, 0)
                        if isNull(value)
                        else convertToDatetime(value)
                    )
            else:
                raise Exception()
        except Exception:
            raise Exception("unexpected data type", dataType)
    return newValue


def createDF(spark, columns, values, schema, typeMap, port) -> DataFrame:
    defaults = defaultsForSchema(schema)
    missingColumns = list(set(defaults.keys()) - set(columns))
    allColumns = columns + missingColumns
    missingValues = list(map(lambda c: defaults[c], missingColumns))
    allValues = list(map(lambda row: row + missingValues, values))

    reorderedSchema = StructType(
        list(map(lambda column: StructField(column, typeMap[column]), allColumns))
    )
    df = spark.createDataFrame(allValues, reorderedSchema)
    return df


def createDfFromResourceFiles(
        spark: SparkSession, schemaDefinitionPath: str, dataPath: str, port: str
) -> DataFrame:
    schemaJson = json.loads(readResource(schemaDefinitionPath))
    schema = StructType.fromJson(schemaJson)

    colDataMap = {}
    for col in schema:
        colDataMap[col.name] = col.dataType

    data = json.loads(readResource(dataPath))
    cols = []
    for col in data["columns"]:
        cols.append(col)

    values = []
    for row in data["values"]:
        newRow = []
        for (value, colName) in zip(row, cols):
            type = colDataMap[colName]
            newValue = convertStringValueToDatatype(type, value)
            newRow.append(newValue)
        values.append(newRow)

    # dataSchema = StructType(list(filter(lambda c: c.name.lower() in cols, schema.fields)))
    return createDF(spark, cols, values, schema, colDataMap, port)


def rowEquals(r1, r2):
    if len(r1) != len(r2):
        return False

    for i in range(len(r1)):
        if r1[i] != r2[i]:
            return False

    return True


def postProcess(origDf: DataFrame) -> DataFrame:
    df = origDf.na.fill("null")
    return df.sql_ctx.createDataFrame(df.rdd, df.schema)


def assertDFEquals(
        expectedUnsorted: DataFrame, resultUnsorted: DataFrame, maxUnequalRowsToShow: int
) -> str:
    def _sort(df: DataFrame):
        if len(df.columns) == 0:
            return df
        return df.sort(*[col(x) for x in df.columns])

    def fetchTypes(df: DataFrame):
        return [(f.name, f.dataType) for f in df.schema.fields]

    def _assertEqualsTypes(dfExpected: DataFrame, dfActual: DataFrame):
        expectedTypes = fetchTypes(dfExpected)
        actualTypes = fetchTypes(dfActual)
        if str(expectedTypes) != str(actualTypes):
            raise Exception(
                "Types NOT equal! " + str(expectedTypes) + " != " + str(actualTypes)
            )

    def _assertEqualsCount(dfExpected: DataFrame, dfActual: DataFrame):
        dfExpectedCount = dfExpected.rdd.count()
        dfActualCount = dfActual.rdd.count()
        if dfExpectedCount != dfActualCount:
            raise Exception(
                f"Length not Equal.\n{str(dfExpectedCount)} vs {dfActualCount}"
            )

    def _assertEqualsValues(dfExpected: DataFrame, dfActual: DataFrame):
        expectedVal = dfExpected.rdd.zipWithIndex().map(lambda x: (x[1], x[0]))
        resultVal = dfActual.rdd.zipWithIndex().map(lambda x: (x[1], x[0]))

        joined = expectedVal.join(resultVal)
        unequalRDD = joined.filter(lambda x: (not rowEquals(x[1][0], x[1][1])))

        if len(unequalRDD.take(maxUnequalRowsToShow)) != 0:
            raise Exception(
                "Expected != Actual\nMismatch: "
                + str(unequalRDD.take(maxUnequalRowsToShow))
            )

    expected = _sort(postProcess(expectedUnsorted))
    result = _sort(postProcess(resultUnsorted))

    try:
        expected.rdd.cache()
        result.rdd.cache()

        # assert equality by means of count, types and data
        _assertEqualsCount(expected, result)
        _assertEqualsTypes(expected, result)
        _assertEqualsValues(expected, result)
    except:
        raise Exception("Dataframe match error")
    finally:
        expected.rdd.unpersist()
        result.rdd.unpersist()


def assertPredicates(port: str, df: DataFrame, predicates):
    for (pred, name) in predicates:
        if df.filter(pred).count() != df.count():
            raise Exception(
                f"Predicate {name} [[`{pred}`]] not universally true for port {port}"
            )


def readData(spark: SparkSession, schema: StructType, path: str) -> DataFrame:
    jsonData = json.loads(readResource(path))
    colDataMap = {}
    for col in schema:
        colDataMap[col.name] = col.dataType
    data = []
    for row in jsonData:
        newRow = []
        for idx, element in enumerate(row):
            newElement = convertStringValueToDatatype(
                schema.fields[idx].dataType, element
            )
            newRow.append(newElement)
        data.append(newRow)
    df = spark.createDataFrame(data, schema)
    df.show()
    return df


def writeData(
        pathPrefix: str, fileName: str, df: DataFrame, separator: str, maxRows: int = 100
):
    from pathlib import Path

    Path(pathPrefix).mkdir(parents=True, exist_ok=True)
    file = open(f"{pathPrefix}/{fileName}", "w")
    headers = separator.join(df.schema.fieldNames()) + "\n"
    for row in df.rdd.collect():
        print(row)
    fields = "\n".join(
        list(map(lambda row: separator.join(list(map(str, row))), df.take(maxRows)))
    )
    content = headers + fields
    file.write(content)
    file.close()


class ProphecyDBUtil:
    class secrets:
        # Dummy Implementation for dbutils so unit test won't complain
        # This however won't cause issue because source/target nodes do not run in unit test
        @staticmethod
        def get(*values: str) -> str:
            return ":".join(values)
