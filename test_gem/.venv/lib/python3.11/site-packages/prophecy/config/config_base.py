# WARNING - Do not add import * in this module
from pyspark import Row
from pyspark.sql import SparkSession
from pyspark.sql.functions import expr
from functools import lru_cache
from datetime import datetime, date
import os
import logging

logger = logging.getLogger(__name__)

is_serverless = bool(int(os.environ.get("DATABRICKS_SERVERLESS_MODE_ENABLED", "0")))
logger.debug(f'is_serverless is {is_serverless}')


class ProjectConfig:

    @staticmethod
    def get_merged_values(base_values, overridden_values):
        from pyhocon import ConfigFactory, ConfigTree
        def to_plain_dict(obj):
            if isinstance(obj, dict):
                return {k: to_plain_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [to_plain_dict(i) for i in obj]
            else:
                return obj
        conf1 = ConfigFactory.from_dict(base_values)
        conf2 = ConfigFactory.from_dict(overridden_values)

        # Merge using pyhocon's built-in merge
        return to_plain_dict(ConfigTree.merge_configs(conf1, conf2).as_plain_ordered_dict())

    @staticmethod
    def get_resolved_project_config_values(project_config_values, overridden_values):
        merged_values = ProjectConfig.get_merged_values(project_config_values, overridden_values)
        # Override with pipeline config values for fields that are present in config_values
        keys_to_delete = []
        for field_name, field_value in merged_values.items():
            if field_name not in project_config_values:
                # Delete those fields which are not in project config
                keys_to_delete.append(field_name)
        for key in keys_to_delete:
            del merged_values[key]
        return merged_values

    def __init__(self, config_schema, config_values: dict):
        """
        :param config_schema: The schema.json of ProjectConfig variables.
        :param config_values: The final values as a dictionary. Same as <instance>.json.
        """
        self.config_schema = config_schema
        self.config_values = config_values

    def with_pipeline_overrides(self, overridden_values: dict):
        self.config_values = self.get_resolved_values(overridden_values)
        return self

    def get_resolved_values(self, overridden_values: dict):
        """
        Resolve project configuration values by overriding project config values with pipeline config values
        for fields that are present in config_values.

        Args:
            overridden_values: The project config values (project config)

        Returns:
            dict: Resolved configuration values where pipeline config overrides project config
                  for fields present in config_values, but project config values are kept
                  for fields not present in config_values
        """
        return ProjectConfig.get_resolved_project_config_values(self.config_values, overridden_values)

class ConfigBase:

    class SecretValue:
        def __init__(self, prophecy_spark=None, secretScope: str="", secretKey: str="", providerType: str="Databricks", **kwargs):
            self.prophecy_spark = prophecy_spark
            self.secretScope = secretScope
            self.secretKey = secretKey
            self.providerType = providerType

        def __deepcopy__(self, memo):
            import copy
            from pyspark.sql import SparkSession
            cls = self.__class__
            result = cls.__new__(cls)
            memo[id(self)] = result
            for k, v in self.__dict__.items():
                if isinstance(v, SparkSession):
                    setattr(result, k, v)
                else:
                    setattr(result, k, copy.deepcopy(v, memo))
            return result

        @lru_cache()
        def __str__(self):
            if is_serverless:
                from prophecy.utils.secrets import ProphecySecrets
                self.secret_manager = ProphecySecrets
                return self.secret_manager.get(self.secretScope, self.secretKey, self.providerType)

            if (self.prophecy_spark is not None and self.prophecy_spark.sparkContext.getConf().get("prophecy.schema.analysis") == "True"):
                return f"{self.secretScope}:{self.secretKey}"
            self.jvm = self.prophecy_spark.sparkContext._jvm
            self.secret_manager = self.jvm.io.prophecy.libs.secrets.ProphecySecrets
            return self.secret_manager.get(self.secretScope, self.secretKey, self.providerType)

    def updateSpark(self, spark):
        self.spark = spark

    def get_dbutils(self, spark):
        try:
            dbutils  # Databricks provides an instance of dbutils be default. Checking for it's existence
            return dbutils
        except NameError:
            try:
                from pyspark.dbutils import DBUtils

                _dbutils = DBUtils(spark)
            except:
                try:
                    import IPython

                    _dbutils = IPython.get_ipython().user_ns["dbutils"]
                except Exception as e:
                    from prophecy.test.utils import ProphecyDBUtil

                    _dbutils = ProphecyDBUtil

            return _dbutils

    def get_int_value(self, value):
        if value is not None:
            return int(value)
        else:
            return value

    def get_float_value(self, value):
        if value is not None:
            return float(value)
        else:
            return value

    def get_bool_value(self, value):
        if value is not None:
            return bool(value)
        else:
            return value

    def get_timestamp_value(self, value):
        if value is None:
            return value
        if type(value) is datetime:
            return value
        if type(value) is date:
            return datetime.combine(value, datetime.min.time())
        if type(value) is str and value != "":
            formats = [
                # with timezone
                "%d-%m-%YT%H:%M:%SZ%z", # default format that prophecy uses
                "%d-%m-%Y %H:%M:%S %z",
                "%d-%m-%YT%H:%M:%S.%fZ%z",
                "%d-%m-%YT%H:%M:%S.%f%z",
                "%d-%m-%YT%H:%M:%S%z",
                "%d-%m-%Y %H:%M:%S.%f %z",
                "%d-%m-%Y %H:%M:%S.%f%z",
                "%d-%m-%Y %H:%M:%S%z",
                # without timezone
                "%d-%m-%YT%H:%M:%S.%f",
                "%d-%m-%YT%H:%M:%S",
                "%d-%m-%Y %H:%M:%S.%f",
                "%d-%m-%Y %H:%M:%S",

                # other formats
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%m-%d-%YT%H:%M:%S.%f%z",
                "%m-%d-%YT%H:%M:%S%z",
                "%m-%d-%Y %H:%M:%S.%f%z",
                "%m-%d-%Y %H:%M:%S%z",
                "%m-%d-%YT%H:%M:%S.%f",
                "%m-%d-%YT%H:%M:%S",
                "%m-%d-%Y %H:%M:%S.%f",
                "%m-%d-%Y %H:%M:%S",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

            raise ValueError(f"Timestamp string '{value}' does not match any known formats.")
        return None

    def get_date_value(self, value):
        if type(value) is date:
            return value
        if type(value) is str and value != "":
            formats = [
                # date
                "%Y-%m-%d",
                "%m-%d-%Y",
                "%d-%m-%Y",

                "%Y/%m/%d",
                "%m/%d/%Y",
                "%d/%m/%Y",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue

            raise ValueError(f"Date string '{value}' does not match any known formats.")
        return None

    def get_date_list(self, date_list):
        if date_list is None:
            return date_list
        if isinstance(date_list, list):
            return [self.get_date_value(x) for x in date_list]
        else:
            raise ValueError(f"Expected a list of dates, but got {type(date_list)}")

    def get_timestamp_list(self, timestamp_list):
        if timestamp_list is None:
            return timestamp_list
        if isinstance(timestamp_list, list):
            return [self.get_timestamp_value(x) for x in timestamp_list]
        else:
            raise ValueError(f"Expected a list of timestamps, but got {type(timestamp_list)}")

    # Old function, keeping it for backward compatibility
    def generate_object(self, value, cls):
        if isinstance(value, list):
            return [self.generate_object(x, cls) for x in value]
        elif isinstance(value, dict):
            return cls(**value)
        return value

    # Old function, keeping it for backward compatibility
    def get_object(self, default, override, cls):
        if override == None:
            return default
        else:
            return self.generate_object(override, cls)

    def generate_config_object(self, spark, value, cls, project_config: ProjectConfig=None):
        if isinstance(value, list):
            # `project_config` will only be passed for subgraphs. It won't be passed for normal records.
            # No need to pass project_config here.
            return [self.generate_config_object(spark, x, cls) for x in value]
        elif isinstance(value, dict):
            if project_config is None:
                # Keep this as a safety check.
                return cls(**{**{"prophecy_spark": spark}, **value})
            else:
                # No need to worry whether the generated code of the pipeline has the `prophecy_project_config` argument
                # mentioned or not. **kwargs is present in all the calls class's __init__ methods. This will prevent throwing
                # any exception.
                return cls(**{**{"prophecy_spark": spark, "prophecy_project_config": project_config}, **value})
        return value

    def get_secret_config_object(self, spark, default, override, cls):
        if isinstance(override, str) and override.count(":") == 1:
            parts = override.split(":")
            values = {"providerType": "Databricks", "secretScope": parts[0], "secretKey": parts[1]}
            return self.get_config_object(spark, default, values, cls)
        else:
            return self.get_config_object(spark, default, override, cls)

    def get_config_object(self, spark, default, override, cls, project_config: ProjectConfig=None):
        # project_config will only be passed for Subgraphs. Won't be passed for normal records
        if override == None:
            return default
        else:
            return self.generate_config_object(spark, override, cls, project_config)

    def to_dict(self):
        to_ignore = ["spark", "prophecy_spark", "jvm", "secret_manager", "prophecy_project_config"]
        def to_dict_recursive(obj):
            def should_include(key, value):
                # remove any unwanted objects from the config:
                return key not in to_ignore and not isinstance(value, SparkSession)
            if isinstance(obj, (list, tuple)):
                return [to_dict_recursive(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: to_dict_recursive(value) for key, value in obj.items() if should_include(key, value)}
            elif type(obj) is date:
                return obj.strftime("%d-%m-%Y")
            elif type(obj) is datetime:
                if obj.tzinfo is None:
                    return obj.strftime("%d-%m-%YT%H:%M:%SZ")
                else:
                    return obj.strftime("%d-%m-%YT%H:%M:%SZ%z")
            elif hasattr(obj, "__dict__"):
                return to_dict_recursive({key: value for key, value in obj.__dict__.items() if should_include(key, value)})
            elif hasattr(obj, "__slots__"):
                return to_dict_recursive({slot: getattr(obj, slot) for slot in obj.__slots__ if should_include(slot, getattr(obj, slot))})
            else:
                return obj
        return to_dict_recursive(self)

    def update_all(self, name, new_value):
        def process_attr_value(attr_val):
            if isinstance(attr_val, ConfigBase):
                attr_val.update_all(name, new_value)
            elif isinstance(attr_val, list) or isinstance(attr_val, tuple):
                for element in attr_val:
                    if isinstance(element, ConfigBase):
                        element.update_all(name, new_value)
            elif isinstance(attr_val, dict):
                for k, v in attr_val.items():
                    if isinstance(v, ConfigBase):
                        v.update_all(name, new_value)
            else:
                pass

        if hasattr(self, "__dict__"):
            for attr_name, attr_val in self.__dict__.items():
                if attr_name == name:
                    setattr(self, attr_name, new_value)
                else:
                    process_attr_value(attr_val)
        if hasattr(self, "__slots__"):
            for attr_name in self.__slots__:
                if attr_name == name:
                    setattr(self, attr_name, new_value)
                else:
                    process_attr_value(getattr(self, attr_name))
        else:
            pass

    def find_spark(self, instance):
        if isinstance(instance, list):
            for element in instance:
                spark = self.find_spark(element)
                if spark is not None:
                    return spark
        if isinstance(instance, ConfigBase) or isinstance(instance, ConfigBase.SecretValue):
            if hasattr(instance, "spark") and isinstance(instance.spark, SparkSession):
                    return instance.spark
            elif hasattr(instance, "prophecy_spark") and isinstance(instance.prophecy_spark, SparkSession):
                    return instance.prophecy_spark
            for key, value in instance.__dict__.items():
                    spark = self.find_spark(value)
                    if spark is not None:
                        return spark
        return None

    def update_from_row(self, row: Row):
        import copy
        new_config = copy.deepcopy(self)
        spark_variable = self.find_spark(self)
        updated_config_json = {**new_config.to_dict(), **row.asDict(recursive=True)}
        prophecy_project_config = None
        if hasattr(self, 'prophecy_project_config'):
            prophecy_project_config = self.prophecy_project_config
        return self.get_config_object(spark_variable, new_config, updated_config_json, new_config.__class__, project_config=prophecy_project_config)

    def update_from_row_map(self, row: Row, config_to_column: dict):
        import copy
        new_config = copy.deepcopy(self)
        spark_variable = self.find_spark(self)
        row_as_dict = row.asDict(recursive=True)
        overridden_values = {}
        for config_name, column_name in config_to_column.items():
            overridden_values[config_name] = row_as_dict[column_name]
        updated_config_json = {**new_config.to_dict(), **overridden_values}
        prophecy_project_config = None
        if hasattr(self, 'prophecy_project_config'):
            prophecy_project_config = self.prophecy_project_config
        return self.get_config_object(spark_variable, new_config, updated_config_json, new_config.__class__, project_config=prophecy_project_config)

    def __deepcopy__(self, memo):
        import copy
        from pyspark.sql import SparkSession
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if isinstance(v, SparkSession):
                setattr(result, k, v)
            else:
                setattr(result, k, copy.deepcopy(v, memo))
        return result

    def add_config_fields(self, spark_variable, config_record, config_values: dict):
        """
        Add configuration fields to this ConfigBase instance based on a ConfigurationRecord
        and a dictionary of key-value pairs.
        
        Args:
            config_record: ConfigurationRecord object defining the schema
            config_values: Dictionary with field names as keys and their values
        """
        from prophecy.config.utils import (
            StringElement, IntElement, LongElement, ShortElement, 
            FloatElement, DoubleElement, BooleanElement, DateElement, 
            TimestampElement, ArrayElement, ConfigurationRecord, SecretElement,
            EnumElement, LookupElement, ValueElement, TableNameElement, 
            ColumnNameElement, SparkColumnElement, SparkExpressionElement
        )
        
        def convert_value(value, data_element):
            """Convert a value based on the DataElement type."""
            element_type = data_element.get_name()
            
            if element_type == "string":
                return str(value) if value is not None else None
            elif element_type == "spark_column":
                return str(value) if value is not None else None
            elif element_type == "spark_expression":
                return str(value) if value is not None else None
            elif element_type == "int":
                return self.get_int_value(value)
            elif element_type == "long":
                return self.get_int_value(value)  # Python doesn't distinguish int/long
            elif element_type == "short":
                return self.get_int_value(value)  # Python doesn't distinguish int/short
            elif element_type == "float":
                return self.get_float_value(value)
            elif element_type == "double":
                return self.get_float_value(value)  # Python doesn't distinguish float/double
            elif element_type == "boolean":
                return self.get_bool_value(value)
            elif element_type == "date":
                return self.get_date_value(value)
            elif element_type == "timestamp":
                return self.get_timestamp_value(value)
            elif element_type == "array":
                if isinstance(value, list):
                    return [convert_value(item, data_element.element_type) for item in value]
                else:
                    return value
            elif element_type == "record":
                if isinstance(value, dict):
                    # Create a nested ConfigBase instance for record types
                    nested_config = type('NestedConfig', (ConfigBase,), {})()
                    nested_config.add_config_fields(spark_variable, data_element, value)
                    return nested_config
                else:
                    return value
            elif element_type == "enum":
                # For enum, validate that the value is in the allowed values
                if value in data_element.values:
                    return value
                else:
                    raise ValueError(f"Value '{value}' is not in allowed enum values: {data_element.values}")
            elif element_type == "secret":
                # For secrets, create a SecretValue instance
                if isinstance(value, dict):
                    return self.get_secret_config_object(
                        spark_variable,
                        ConfigBase.SecretValue(prophecy_spark=spark_variable),
                        value,
                        ConfigBase.SecretValue
                    )
                else:
                    return value
            else:
                # For unknown types, return as-is
                return value
        
        def process_fields(fields, values_dict):
            """Process configuration fields recursively."""
            for field in fields:
                field_name = field.name
                field_kind = field.kind
                
                # Skip if field is not in the provided values and is optional
                if field_name not in values_dict:
                    if field.optional:
                        continue
                    else:
                        raise ValueError(f"Required field '{field_name}' is missing from config values")
                
                field_value = values_dict[field_name]
                
                # Convert the value based on the field type
                converted_value = convert_value(field_value, field_kind)
                
                # Set the field on this ConfigBase instance
                setattr(self, field_name, converted_value)
        
        # Process the configuration record fields
        if hasattr(config_record, 'fields'):
            process_fields(config_record.fields, config_values)
        else:
            raise ValueError("ConfigurationRecord must have a 'fields' attribute")

    def add_project_config(self, project_config: ProjectConfig, overridden_values: dict):
        self.prophecy_project_config = project_config
        if project_config is not None and hasattr(self, 'add_config_fields'):
            # Merge project_config.config_values with overridden_values
            # Start with project config values
            merged_values = ProjectConfig.get_resolved_project_config_values(project_config.config_values, overridden_values)
            # Call add_config_fields with the merged values
            self.add_config_fields(self.find_spark(self), project_config.config_schema, merged_values)

    def add_project_config(self, overridden_values: dict):
        # Assumption here is that the `prophecy_project_config` is already part of the class variable.
        self.add_project_config(self.prophecy_project_config, overridden_values)

    def update_project_conf_values(self, project_config: ProjectConfig, overridden_values):
        if project_config is None:
            return None
        return project_config.with_pipeline_overrides(overridden_values)

    def update_and_add_project_config(self, prophecy_spark=None, project_config: ProjectConfig=None, overridden_values: dict=None):
        """
        This will merge the overridden values with the project config values and then assign the new values along with
        schema to `prophecy_project_config`.
        :param project_config:
        :param overridden_values:
        :return:
        """
        self.prophecy_project_config = project_config
        if project_config is not None:
            if overridden_values is None:
                self.add_config_fields(prophecy_spark, project_config.config_schema, config_values=project_config.config_values)
            else:
                # Merge project_config.config_values with overridden_values
                # Start with project config values
                merged_values = ProjectConfig.get_resolved_project_config_values(project_config.config_values, overridden_values)
                self.add_config_fields(prophecy_spark, project_config.config_schema, merged_values)

    def update_project_config_fields(self, source_config):
        """
        Copy all project config variables from another ConfigBase instance to this ConfigBase instance.
        
        Args:
            source_config: The ConfigBase instance from which project config variables will be copied
        """
        if hasattr(source_config, 'prophecy_project_config') and source_config.prophecy_project_config is not None:
            # Copy the project config from the source to self
            self.prophecy_project_config = source_config.prophecy_project_config
            
            # Copy all project config fields using the schema field names
            if hasattr(source_config.prophecy_project_config, 'config_schema') and source_config.prophecy_project_config.config_schema is not None:
                for field in source_config.prophecy_project_config.config_schema.fields:
                    field_name = field.name
                    if hasattr(source_config, field_name):
                        attr_value = getattr(source_config, field_name)
                        setattr(self, field_name, attr_value)

    def evaluate_sql_expr(self, prophecy_spark: SparkSession, expr_string: str):
        if prophecy_spark:
            result = prophecy_spark.range(1).select(expr(expr_string)).first()[0]
            return result
        return None
