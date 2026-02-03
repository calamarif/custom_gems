from typing import Optional
from prophecy.udfs.scala_udf_wrapper import initializeUDFBase
from pyspark.sql import SQLContext


class ABILib:
    def __init__(self, spark):
        self.spark = spark
        self.sqlContext = SQLContext(spark.sparkContext, sparkSession=spark)
        self.libs = spark.sparkContext._jvm.io.prophecy.libs.package
        self._registerABIUDFs()

    def _registerABIUDFs(self):
        udfBase = initializeUDFBase(self.spark)
        self.libs.registerAllUDFs(self.spark._jsparkSession)


abiLib: Optional[ABILib] = None


class ScalaUtil:
    @staticmethod
    def initializeUDFs(spark):
        global abiLib
        if abiLib is None:
            abiLib = ABILib(spark)

    @staticmethod
    def getAbiLib():
        global abiLib
        return abiLib
