
def concatenateFiles(spark, format, mode, inputDir, outputFileName, deleteTempPath=True, fileFormatHasHeaders=True):
    jvm = spark.sparkContext._jvm
    jvm.io.prophecy.libs.package.concatenateFiles(spark._jsparkSession, format, mode, inputDir, outputFileName, deleteTempPath, fileFormatHasHeaders)

