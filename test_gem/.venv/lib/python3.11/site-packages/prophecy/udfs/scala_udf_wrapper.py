from typing import Optional

from pyspark.sql import Column
from pyspark.sql.functions import udf
from pyspark.sql.types import IntegerType

# Version-compatible imports for Spark 3.x and 4.x
try:
    from pyspark.sql.classic.column import _to_java_column, _to_seq
except ImportError:
    from pyspark.sql.column import _to_java_column, _to_seq


class UDFBase:
    sparkSession = None
    UDFUtils = None

    def __init__(self, spark):
        self.UDFUtils = spark.sparkContext._jvm.io.prophecy.libs.python.UDFUtils
        self.sparkSession = spark


udfConfig: Optional[UDFBase] = None


def initializeUDFBase(spark):
    global udfConfig
    if udfConfig is None:
        udfConfig = UDFBase(spark)
    return udfConfig


def rest_api(*cols):
    _cols = udfConfig.sparkSession.sparkContext._jvm.PythonUtils.toList(
        [item._jc for item in list(cols)]
    )
    rest_api_response = udfConfig.UDFUtils.rest_api(_cols)
    return 1


def call_udf(udfName: str, *cols):
    _cols = _to_seq(udfConfig.sparkSession.sparkContext, cols, _to_java_column)
    call_udf_result = udfConfig.UDFUtils.call_udf(udfName, _cols)
    return Column(call_udf_result)
