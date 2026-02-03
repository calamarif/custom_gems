from pyspark.sql import SparkSession
from callums_custom_gem import callums_custom_gem

def main():
    spark = SparkSession.builder.appName("TestApp").getOrCreate()
    data = [("a", 1), ("b", 2), ("c", 3)]
    columns = ["col1", "col2"]
    df = spark.createDataFrame(data, columns)
    
    # an instance of the component
    custom_gem = callums_custom_gem()
    
    # get the properties of the component
    props = custom_gem.callums_custom_gemProperties()
    
    # create an instance of the component code
    custom_gem_code = custom_gem.callums_custom_gemCode(props)
    
    # apply the component to the dataframe
    df = custom_gem_code.apply(spark, df)
    
    # check that the dataframe has been returned correctly
    assert df.count() == 3
    
    print("Test passed!")

if __name__ == "__main__":
    main()