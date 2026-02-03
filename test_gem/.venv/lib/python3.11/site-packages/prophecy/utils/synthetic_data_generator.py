import random
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, IntegerType, FloatType, BooleanType, DateType, TimestampType, StructType, StructField
from pyspark.sql.functions import udf
from .faker import Faker
from datetime import datetime

@udf(returnType=StringType())
def random_full_name() -> str:
    local_faker = Faker()
    return local_faker.name()

@udf(returnType=StringType())
def random_first_name() -> str:
    local_faker = Faker()
    return local_faker.first_name()

@udf(returnType=StringType())
def random_last_name() -> str:
    local_faker = Faker()
    return local_faker.last_name()

@udf(returnType=StringType())
def random_address() -> str:
    local_faker = Faker()
    return local_faker.address()

@udf(returnType=StringType())
def random_email() -> str:
    local_faker = Faker()
    return local_faker.email()

@udf(returnType=StringType())
def random_phone_number(pattern="###-###-####") -> str:
    local_faker = Faker()
    return local_faker.numerify(pattern)

@udf(returnType=StringType())
def random_uuid() -> str:
    local_faker = Faker()
    return str(local_faker.uuid4())

@udf(returnType=IntegerType())
def random_int(min=0, max=100) -> int:
    local_faker = Faker()
    return local_faker.random_int(min=min, max=max)

@udf(returnType=FloatType())
def random_float(min_value=0, max_value=100, decimal_places=2) -> float:
    local_faker = Faker()
    return local_faker.pyfloat(min_value=min_value, max_value=max_value, right_digits=decimal_places)

@udf(returnType=BooleanType())
def random_boolean() -> bool:
    local_faker = Faker()
    return local_faker.boolean()

@udf(returnType=DateType())
def random_date(start_date: str, end_date: str) -> str:
    local_faker = Faker()
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    return local_faker.date_between_dates(date_start=start, date_end=end)

@udf(returnType=TimestampType())
def random_datetime(start_datetime: str, end_datetime: str) -> str:
    local_faker = Faker()
    start = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(end_datetime, "%Y-%m-%d %H:%M:%S")
    return local_faker.date_time_between_dates(datetime_start=start, datetime_end=end)

@udf(returnType=StringType())
def random_list_elements(elements: list) -> str:
    local_faker = Faker()
    return str(local_faker.random_element(elements))

@udf(returnType=StringType())
def random_foreign_key(ref_values: list) -> str:
    local_faker = Faker()
    return str(local_faker.random_element(ref_values))

@udf(returnType=IntegerType())
def sequential_number(temp_id: int, start: int) -> int:
    return temp_id + start

class FakeDataFrame:
    def __init__(self, spark, rows, seed=None):
        self.spark = spark
        self.rows = rows
        self.seed = seed
        self.df = spark.range(rows).toDF("temp_id")
        self.schema_fields = []
        self.null_columns_dict = {}
        self.columns_with_types = {}
        if seed is not None:
            random.seed(seed)

    def addColumn(self, column_name, column_expression=None, data_type=None, nulls=0, ref_table=None, ref_column=None):
        if data_type:
            self.schema_fields.append(StructField(column_name, data_type, nullable=True))
        else:
            raise ValueError(f"Unsupported data type for column: {column_name}")

        if data_type is not None:
            self.columns_with_types[column_name] = data_type

        if ref_table and ref_column:
            ref_df = self.spark.read.table(ref_table).select(ref_column).distinct()
            ref_values = [row[ref_column] for row in ref_df.collect()]
            column_expression = random_foreign_key(F.array([F.lit(val) for val in ref_values]))

        self.df = self.df.withColumn(column_name, column_expression)

        if nulls > 0:
            total_rows = self.rows

            null_indices = random.sample(range(total_rows), nulls)

            self.df = self.df.withColumn(
                column_name, 
                F.when(F.col("temp_id").isin(null_indices), None).otherwise(F.col(column_name))
            )

        return self

    def build(self):
        current_schema = self.df.schema
        
        for column_name, user_defined_type in self.columns_with_types.items():
            current_type = next((field.dataType for field in current_schema if field.name == column_name), None)
            
            if current_type and current_type != user_defined_type:
                self.df = self.df.withColumn(column_name, self.df[column_name].cast(user_defined_type))

        self.df = self.df.drop("temp_id")
        
        return self.df