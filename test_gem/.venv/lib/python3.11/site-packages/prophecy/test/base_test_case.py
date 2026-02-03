import json
import unittest
from pyspark.sql import SparkSession
import glob
import os
from prophecy.libs.utils import isBlank


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # jarDependencies = glob.glob("/opt/docker/lib/*.jar")
        sparkSession = (
            SparkSession.builder.master("local")
                .appName("init")
                .config("spark.sql.legacy.allowUntypedScalaUDF", "true")
                .config("spark.port.maxRetries", "100")
        )

        config_json_str = os.getenv('SPARK_CONFIG_JSON')
        if not isBlank(config_json_str):
            print(f"Found spark conf {config_json_str}")
            try:
                sparkConf = json.loads(config_json_str)
                for key, value in sparkConf.items():
                    print(f"Setting spark conf as Key: {key}, Value: {value}")
                    sparkSession.config(key, value)
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON {config_json_str} with exception:", e)
                raise
            except Exception as e:
                print(f"An error occurred parsing config {config_json_str} with exception:", e)
                raise

        jars = os.getenv('SPARK_JARS_CONFIG')
        fallBackSparkPackages = [
            "io.prophecy:prophecy-libs_2.12:6.3.0-3.1.2"
        ]

        if not isBlank(jars):
            sparkSessionWithReqdDependencies = sparkSession.config("spark.jars", jars)
        else:
            sparkSessionWithReqdDependencies = sparkSession.config("spark.jars.packages",
                                                                   ",".join(fallBackSparkPackages))

        cls.spark = (sparkSessionWithReqdDependencies.getOrCreate())
        cls.maxUnequalRowsToShow = 5

    def setup(self):
        self.spark = BaseTestCase.spark
        self.maxUnequalRowsToShow = BaseTestCase.maxUnequalRowsToShow
