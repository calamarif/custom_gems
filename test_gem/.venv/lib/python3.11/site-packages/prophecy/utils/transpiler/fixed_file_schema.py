# This contains wrappers over various fixed file schema classes implemented in scala

from prophecy.utils.transpiler.abi_base import ScalaUtil
from prophecy.libs.utils import (createScalaList, createScalaOption, createScalaMap)


def FFSchemaRecord(recordType, rows, delimiter=None):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFSchemaRecord(recordType, createScalaList(spark, rows),
                                               createScalaOption(spark, delimiter))


def FFRecordType(startType):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFRecordType(startType)


def FFIncludeFileRow(filePath):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFIncludeFileRow(filePath)


def FFConditionalSchemaRow(condition, schemaRow):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFConditionalSchemaRow(condition, schemaRow)


def FFSimpleSchemaRow(name, format, value):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFSimpleSchemaRow(name, format, value)


def FFCompoundSchemaRow(compound, rows):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFCompoundSchemaRow(compound, createScalaList(spark, rows))


def FFSimpleSchemaList(rows):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFSimpleSchemaList(createScalaList(spark, rows))


def FUnionType(name, typeName=None):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FUnionType(createScalaOption(spark, name), createScalaOption(spark, typeName))


def FFStructType(name1, typeName=None):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFStructType(name1, createScalaOption(spark, typeName))


def FFStructArrayType(name1, arraySizeInfo, typeName=None):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFStructArrayType(name1, createScalaOption(spark, arraySizeInfo),
                                                  createScalaOption(spark, typeName))


def FFTypeNameWithProperties(name, delimiter, miscProperties={"packed": False}):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFTypeNameWithProperties(name, createScalaOption(spark, delimiter),
                                                         createScalaMap(spark, miscProperties))


def FFTypeName(name, delimiter):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFTypeName(name, createScalaOption(spark, delimiter))


def FFNumberFormat(name, precision, scale, miscProperties={"signReserved": False, "packed": False}):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFNumberFormat(name, createScalaOption(spark, precision),
                                               createScalaOption(spark, scale),
                                               createScalaMap(spark, miscProperties))


def FFStringFormat(name, precision, props):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    if props is None:
        jprops = createScalaOption(spark, None)
    else:
        jprops = createScalaOption(spark, createScalaMap(spark, props))
    return jvm.io.prophecy.libs.FFStringFormat(name, createScalaOption(spark, precision), jprops)


def FFDateFormat(name, format, miscProperties={}):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFDateFormat(name, createScalaOption(spark, format),
                                             createScalaMap(spark, miscProperties))


def FFDateTimeFormat(name, format, miscProperties={}):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFDateTimeFormat(name, createScalaOption(spark, format),
                                                 createScalaMap(spark, miscProperties))


def FFStructFormat(name, precision):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFStructFormat(name, createScalaOption(spark, precision))


def FFUnknownFormat(name, arraySizeInfo):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFUnknownFormat(name, createScalaOption(spark, arraySizeInfo))


def FFStringArrayFormat(name, precision, arraySizeInfo):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFStringArrayFormat(name, createScalaOption(spark, precision),
                                                    createScalaOption(spark, arraySizeInfo))


def FFNumberArrayFormat(name, precision, scale, arraySizeInfo,
                        miscProperties={"signReserved": False, "packed": False}):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFNumberArrayFormat(name, createScalaOption(spark, precision),
                                                    createScalaOption(spark, scale),
                                                    createScalaOption(spark, arraySizeInfo),
                                                    createScalaMap(spark, miscProperties))


def FFNoDefaultVal():
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFNoDefaultVal()


def FFNullDefaultVal(value=0):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFNullDefaultVal(createScalaOption(spark, value))


def FFStringDefaultVal(value):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFStringDefaultVal(value)


def FFIntDefaultVal(value):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFIntDefaultVal(value)


def FFDoubleDefaultVal(value):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.libs.FFDoubleDefaultVal(value)
