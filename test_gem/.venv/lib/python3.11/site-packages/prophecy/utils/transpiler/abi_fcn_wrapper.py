import io

import pyspark.sql.types
from pyspark.sql import Column, DataFrame, SQLContext, SparkSession
from pyspark.sql.functions import lit, col, explode
from pyspark.sql.window import Window

from prophecy.utils.transpiler.abi_base import ScalaUtil
from prophecy.udfs.scala_udf_wrapper import call_udf
from prophecy.libs.utils import createScalaOption, createScalaList


def castArgForScala(item):
    # TODO - this seems enough for now, but needs to be enhanced to handle more complex/nested types
    if isinstance(item, Column):
        return item._jc
    elif isinstance(item, SparkSession):
        return item._jsparkSession
    elif isinstance(item, DataFrame):
        return item._jdf
    elif isinstance(item, pyspark.sql.types.StructType):
        return item.json()
    else:
        return item


def decorateColumnFunction(fn):
    spark = ScalaUtil.getAbiLib().spark
    sqlContext = SQLContext(spark.sparkContext, sparkSession=spark)

    def doit(*args):
        newArgs = [castArgForScala(item) for item in list(args)]
        result = fn(*newArgs)
        resultType = result.getClass().getName()
        if resultType == "org.apache.spark.sql.Dataset":
            return DataFrame(result, sqlContext)
        elif resultType == "org.apache.spark.sql.Column":
            return Column(result)
        else:
            return result

    return doit


def is_valid(*args):
    """
    is_valid in prophecy libs supports these variants
    is_valid(input: Column)
    is_valid(input: Column, isNullable: Boolean)
    is_valid(input: Column, isNullable: Boolean, formatInfo: Option[Any])
    is_valid(input: Column, formatInfo: Option[Any])
    is_valid(input: Column, formatInfo: Option[Any], len: Option[Seq[Int]])
    is_valid(input: Column, isNullable: Boolean, formatInfo: Option[Any], len: Option[Seq[Int]])
    """
    libs = ScalaUtil.getAbiLib().libs
    spark = ScalaUtil.getAbiLib().spark
    arglist = list(args)

    def _processFormatInfoArg(arg):
        if isinstance(arg, pyspark.sql.types.DataType):
            formatInfo = createScalaOption(spark, arg.json())
        elif isinstance(arg, list):
            formatInfo = createScalaOption(spark, createScalaList(spark, arg))
        else:
            formatInfo = createScalaOption(spark, arg)
        return formatInfo

    def _processLengthArg(arg):
        if not isinstance(arg, list):
            arg = [arg]
        return createScalaOption(spark, createScalaList(spark, arg))

    input = arglist[0]._jc
    isNullable = False
    formatInfo = createScalaOption(spark, None)
    lengthArg = createScalaOption(spark, None)
    if len(arglist) > 1:
        if isinstance(arglist[1], bool):
            isNullable = arglist[1]
            if len(arglist) > 2:
                formatInfo = _processFormatInfoArg(arglist[2])
            if len(arglist) > 3:
                lengthArg = _processLengthArg(arglist[3])
        else:
            formatInfo = _processFormatInfoArg(arglist[1])
            if len(arglist) > 2:
                lengthArg = _processLengthArg(arglist[2])

    func = libs.__getattr__("is_valid_python_bridge")
    res = func(input, isNullable, formatInfo, lengthArg)

    return Column(res)


def hash_value(input, keys, hashAlgorithm):
    # assert(hashAlgorithm == "murmur")
    from pyspark.sql.functions import struct
    columnToHash = struct([input.getField(f) for f in keys])
    return call_udf("murmur", columnToHash)


# Wrapper to call column expression based functions implemented in the SparkFunction trait in scala
def call_spark_fcn(funcName, *args):
    libs = ScalaUtil.getAbiLib().libs
    try:
        func = libs.__getattr__(funcName)  # Check if this is a column function from the ScalaFunctions class
        f = decorateColumnFunction(func)
        return f(*args)
    except:
        return call_udf(funcName, *args)  # This must be a UDF


def windowSpec(partitionByExpr=None):
    if partitionByExpr is None:
        partitionByExpr = lit(1)
    return Window.partitionBy(partitionByExpr).rowsBetween(Window.unboundedPreceding, Window.currentRow)


def windowSpecPrevRow(partitionByExpr=None):
    if partitionByExpr is None:
        partitionByExpr = lit(1)
    return Window.partitionBy(partitionByExpr).rowsBetween(Window.unboundedPreceding, -1)


def jsonStrToString(jsonstr):
    try:
        return bytes(jsonstr, 'utf-8').decode()
    except:
        return jsonstr

def generateDataFrameWithSequenceColumn(rows, sequenceColumnName, spark) -> DataFrame:
    df = spark.createDataFrame([(list(range(1, rows + 1)),)], [sequenceColumnName])
    out = df.select(explode(col(sequenceColumnName)).alias(sequenceColumnName))
    return out