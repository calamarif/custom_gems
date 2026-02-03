# This contains wrappers over dml_schema implemented in scala

from prophecy.utils.transpiler.abi_base import ScalaUtil


def parse(schema):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.abinitio.dml.DMLSchema.parsePy(schema)


def toSpark(schema):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    return jvm.io.prophecy.abinitio.dml.DMLSchema.toSparkPy(schema)


def getTopLevelColumns(schema):
    spark = ScalaUtil.getAbiLib().spark
    jvm = spark.sparkContext._jvm
    result = jvm.io.prophecy.abinitio.dml.DMLSchema.getTopLevelColumns(schema)
    return [result.apply(i) for i in range(result.size())]
