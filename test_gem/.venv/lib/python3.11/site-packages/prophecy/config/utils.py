import argparse
import os
import json

from pyhocon import ConfigFactory, ConfigTree


def parse_args():
    parser = argparse.ArgumentParser(description="Spark Application")
    parser.add_argument(
        "-C",
        "--config",
        nargs="+",
        help=(
            "Property of the config that needs to be overridden. Set a number of key-value "
            "pairs(do not put spaces before or after the = sign). Ex: -C fabricName=dev "
            'dbConnection="db.prophecy.io" dbUserName="prophecy"'
        ),
    )
    parser.add_argument(
        "-d",
        "--defaultConfFile",
        help="Full path of default hocon config file. Ex: -d dbfs:/some_path/default.json",
        default=None
    )
    parser.add_argument(
        "-f",
        "--file",
        help="Location of the hocon config file. Ex: -f /opt/prophecy/dev.json",
    )
    parser.add_argument(
        "-i",
        "--confInstance",
        help="Config instance name present in config directory. Ex.: -i default",
    )
    parser.add_argument(
        "-O",
        "--overrideJson",
        type=str,
        help="Overridden values in json format"
    )
    parser.add_argument(
        "-pi",
        "--projectConfInstance",
        help="Project Config instance name present in config/projectconf directory. Ex.: -i default",
        required=False
    )
    parser.add_argument(
        "-pc",
        "--projectConfig",
        help="Path to project config directory containing config.metadata.json. Ex.: -pc /path/to/project/config",
        required=False
    )
    parser.add_argument(
        "-pj",
        "--projectConfigDirJson",
        help="""
        This is the json of the directory content of project configs. 
        Format : {"file_name1": "file_content1", "file_name2": "file_content2", ....}
        Ex: {"config.metadata.json": "....", "default.json": "....", "instance1.json": "....", ....}
        """,
        required=False
    )
    args = parser.parse_args()

    return args


def get_resource_file_content(resource_file_name, config_package):
    try:
        # python 3.7+
        import importlib.resources
        with importlib.resources.open_text(config_package, f"{resource_file_name}") as file:
            data = file.read()
    except:
        # python < 3.7
        import importlib.util
        config_instances_path = importlib.util.find_spec(config_package).submodule_search_locations[0]
        config_file_path = f"{config_instances_path}/{resource_file_name}"
        with open(config_file_path, 'r') as file:
            data = file.read()
    return data


# 1 arg parse_config() for backward compatibility.
def parse_config(args, pipeline_dot_conf=None, config_package=None):
    config_package = "prophecy_config_instances" if config_package is None else config_package
    if args.file is not None:
        if hasattr(args, "defaultConfFile"):
            default_config = ConfigFactory.parse_file(
                args.defaultConfFile) if args.defaultConfFile is not None else ConfigFactory.parse_string("{}")
            conf = ConfigFactory.parse_file(args.file).with_fallback(default_config)
        else:
            conf = ConfigFactory.parse_file(args.file)
    elif args.confInstance is not None:
        try:
            # python 3.7+
            import importlib.resources
            with importlib.resources.open_text(
                    config_package,
                    "{instance}.json".format(instance=args.confInstance),
            ) as file:
                data = file.read()
                conf = ConfigFactory.parse_string(data)
        except:
            # python < 3.7
            import importlib.util
            config_instances_path = importlib.util.find_spec(config_package).submodule_search_locations[0]
            config_file_path = f"{config_instances_path}/{args.confInstance}.json"
            with open(config_file_path, 'r') as file:
                data = file.read()
                conf = ConfigFactory.parse_string(data)
    else:
        conf = ConfigFactory.parse_string("{}")
    if args.overrideJson is not None:
        # Override fields
        conf = ConfigTree.merge_configs(conf, ConfigFactory.parse_string(args.overrideJson))
    # override the file config with explicit value passed
    if args.config is not None:
        for config in args.config:
            c = config.split("=", 1)
            conf.put(c[0], c[1])

    if pipeline_dot_conf is not None:
        # `resolve=False` is important here because variable substitution should happen after overriding
        try:
            # Check in resources/
            pipeline_default_conf = ConfigFactory.parse_string(get_resource_file_content(pipeline_dot_conf, config_package),
                                                               resolve=False)
        except:
            # Check as full file path
            pipeline_default_conf = ConfigFactory.parse_file(pipeline_dot_conf, resolve=False)
        # `resolve=True` so that variables get substituted at this step with overridden values
        # pipeline_dot_conf contains default values for a given pipeline. It should have the lowest priority,
        conf = conf.with_fallback(pipeline_default_conf, resolve=True)

    return conf

def get_project_config(config_schema_json, default_json, instance_json):
    # Create DataElement from the schema
    config_schema = create_data_element_from_json(config_schema_json)

    # Merge instance.json with default.json (instance.json takes preference)
    from prophecy.config.config_base import ProjectConfig
    final_project_config_values = ProjectConfig.get_merged_values(default_json, instance_json)

    # Create and return ProjectConfig instance
    return ProjectConfig(config_schema=config_schema, config_values=final_project_config_values)

def parse_project_config(args):
    """
    This method reads the `-pi` / `--projectInstance` and `-pc` / `-projectConfig` parameters passed to
    command line argument and then returns an instance of ProjectConfig( ) having schema and values.
    Values are merged values of default instance and the instance passed as `pi`.
    :param args: Sys args passed to the pipeline .whl.
    """
    if not hasattr(args, 'projectConfInstance') or args.projectConfInstance is None:
        return None
    
    # Get the filename from projectConfInstance argument
    project_config_instance_name = args.projectConfInstance
    
    # Get the project config path from projectConfig argument
    if (hasattr(args, 'projectConfig') and args.projectConfig is not None):
        project_config_path = args.projectConfig

        # Construct file paths
        schema_file_path = os.path.join(project_config_path, "config.metadata.json")
        project_instance_json_path = os.path.join(project_config_path, f"{project_config_instance_name}.json")
        default_json_path = os.path.join(project_config_path, "default.json")

        # Check if required files exist
        if not os.path.exists(schema_file_path):
            raise FileNotFoundError(f"config.metadata.json not found at path: {schema_file_path}")

        if not os.path.exists(project_instance_json_path):
            raise FileNotFoundError(f"File: {project_config_instance_name}.json not found at path: {project_instance_json_path}")

        try:
            # Read and parse the config.metadata.json file
            with open(schema_file_path, 'r') as schema_file:
                schema_data = json.load(schema_file)

            # Read filename.json
            with open(project_instance_json_path, 'r') as filename_file:
                project_instance_config_values = json.load(filename_file)

            # Read default.json if it exists
            project_default_config_values = {}
            if os.path.exists(default_json_path):
                with open(default_json_path, 'r') as default_file:
                    project_default_config_values = json.load(default_file)

            # Create and return ProjectConfig instance
            return get_project_config(schema_data, project_default_config_values, project_instance_config_values)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise Exception(f"Error reading project config from {project_config_path}: {e}")

    elif (hasattr(args, 'projectConfigDirJson') and (args.projectConfigDirJson is not None)):
        # Case when the directory content is passed as a json string
        # This can be used as a fallback for project configs when the read from directory isn't
        # working fine.
        try:
            # Parse the projectConfigDirJson string
            project_config_files = json.loads(args.projectConfigDirJson)
            
            # Check if required files are present
            if "config.metadata.json" not in project_config_files:
                raise FileNotFoundError("config.metadata.json not found in projectConfigDirJson")
            
            instance_file_name = f"{project_config_instance_name}.json"
            if instance_file_name not in project_config_files:
                raise FileNotFoundError(f"File: {instance_file_name} not found in projectConfigDirJson")
            
            # Parse the file contents
            schema_data = json.loads(project_config_files["config.metadata.json"])
            project_instance_config_values = json.loads(project_config_files[instance_file_name])
            
            # Read default.json if it exists
            project_default_config_values = {}
            if "default.json" in project_config_files:
                project_default_config_values = json.loads(project_config_files["default.json"])
            
            # Create and return ProjectConfig instance
            return get_project_config(schema_data, project_default_config_values, project_instance_config_values)
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in projectConfigDirJson or configuration file content: {e}")
        except Exception as e:
            raise Exception(f"Error parsing project config from projectConfigDirJson: {e}")
    else:
        raise ValueError("projectConfig path (-pc) or projectConfigDirJson (-pj) is required when projectConfInstance (-pi) is provided")


"""
Python classes corresponding to Scala DataElement types.
These classes represent the various data types used in Prophecy configuration system.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import json


class DataElement(ABC):
    """Abstract base class for all data elements."""

    @abstractmethod
    def get_name(self) -> str:
        """Get the name/type of this data element."""
        pass


@dataclass
class Property:
    """Represents a property value that can hold different types."""
    string_value: Optional[str] = None
    int_value: Optional[int] = None
    float_value: Optional[float] = None
    boolean_value: Optional[bool] = None
    list_value: Optional[List[Any]] = None
    struct_value: Optional[Dict[str, Any]] = None


@dataclass
class ArrayElement(DataElement):
    """Represents an array of elements of a specific type."""
    element_type: DataElement
    value: Property

    def get_name(self) -> str:
        return "array"


@dataclass
class ShortElement(DataElement):
    """Represents a short integer value."""
    value: Property

    def get_name(self) -> str:
        return "short"


@dataclass
class IntElement(DataElement):
    """Represents an integer value."""
    value: Property

    def get_name(self) -> str:
        return "int"


@dataclass
class LongElement(DataElement):
    """Represents a long integer value."""
    value: Property

    def get_name(self) -> str:
        return "long"


@dataclass
class ValueElement(DataElement):
    """Represents a generic value element."""
    value: Optional[str] = None
    actual_value: Optional[str] = None

    def get_name(self) -> str:
        return "value"


@dataclass
class TableNameElement(DataElement):
    """Represents a table name."""
    value: Optional[str] = None

    def get_name(self) -> str:
        return "table"


@dataclass
class ColumnNameElement(DataElement):
    """Represents a column name."""
    value: Optional[str] = None

    def get_name(self) -> str:
        return "column"


@dataclass
class FloatElement(DataElement):
    """Represents a float value."""
    value: Property

    def get_name(self) -> str:
        return "float"


@dataclass
class DoubleElement(DataElement):
    """Represents a double value."""
    value: Property

    def get_name(self) -> str:
        return "double"


@dataclass
class StringElement(DataElement):
    """Represents a string value."""
    value: Property

    def get_name(self) -> str:
        return "string"


@dataclass
class SparkColumnElement(DataElement):
    """Represents a Spark column."""
    value: Property

    def get_name(self) -> str:
        return "spark_column"


@dataclass
class SparkExpressionElement(DataElement):
    """Represents a Spark expression."""
    value: Property

    def get_name(self) -> str:
        return "spark_expression"


@dataclass
class BooleanElement(DataElement):
    """Represents a boolean value."""
    value: Property

    def get_name(self) -> str:
        return "boolean"


@dataclass
class EnumElement(DataElement):
    """Represents an enumeration with predefined values."""
    default_value: str
    values: List[str]

    def get_name(self) -> str:
        return "enum"


@dataclass
class LookupElement(DataElement):
    """Represents a lookup element with dataset and column references."""
    default_value: str
    dataset_id: str
    column_name: str

    def get_name(self) -> str:
        return "lookup"


@dataclass
class RulesetElement(DataElement):
    """Represents a ruleset element."""
    value: str

    def get_name(self) -> str:
        return "ruleset"


@dataclass
class ConfigurationRecordField:
    """Represents a field in a configuration record."""
    name: str
    kind: DataElement
    optional: bool = False


@dataclass
class SecretElement(DataElement):
    """Represents a secret element with configuration fields."""
    fields: List[ConfigurationRecordField]

    def get_name(self) -> str:
        return "secret"


@dataclass
class DBSecretElement(DataElement):
    """Represents a database secret element."""
    value: Property

    def get_name(self) -> str:
        return "db_secret"


@dataclass
class DateElement(DataElement):
    """Represents a date element."""
    value: Property

    def get_name(self) -> str:
        return "date"


@dataclass
class TimestampElement(DataElement):
    """Represents a timestamp element."""
    value: Property

    def get_name(self) -> str:
        return "timestamp"


@dataclass
class ConfigurationRecord(DataElement):
    """Represents a configuration record with multiple fields."""
    fields: List[ConfigurationRecordField]

    def get_name(self) -> str:
        return "record"


@dataclass
class UnknownElementDeprecated(DataElement):
    """Represents an unknown/deprecated element."""
    value: Optional[str] = None
    actual_value: Optional[str] = None

    def get_name(self) -> str:
        return "unknown"


def create_property_from_json_value(value) -> Property:
    """Create a Property instance from JSON data.

    Based on the Scala Property.write method, Property can contain:
    - string, int, long, short, float, double, boolean values
    - list (array of Properties)
    - struct (object with string keys and Property values)
    """
    # Handle null/empty case
    if value is None:
        return Property()

    # Extract the actual value based on what's present in the JSON
    # The Property.write method prioritizes string, then int, then long, etc.
    string_val = None
    int_val = None
    float_val = None
    boolean_val = None
    list_val = None
    struct_val = None

    # Handle primitive values that might be at the root level
    if type(value) == str:
        string_val = value
    elif type(value) == bool:
        boolean_val = value
    elif type(value) == int:
        int_val = value
    elif type(value) == float:
        float_val = value
    elif type(value) == list:
        list_val = [create_property_from_json_value(item) for item in value]
    elif type(value) == dict:
        struct_val = {k: create_property_from_json_value(v) for k, v in value.items()}

    return Property(
        string_value=string_val,
        int_value=int_val,
        float_value=float_val,
        boolean_value=boolean_val,
        list_value=list_val,
        struct_value=struct_val
    )


def create_data_element_from_json(json_data: Dict[str, Any]) -> DataElement:
    """Create a DataElement instance from JSON data.

    The JSON structure follows the Scala Play JSON serialization format:
    - Uses "type" as discriminator field
    - Data fields are at the root level of the object
    """
    element_type = json_data.get("type", "")

    if element_type == "record":
        fields_data = json_data.get("fields", [])
        fields = []
        for field_data in fields_data:
            field_kind_data = field_data.get("kind", {})
            field_kind = create_data_element_from_json(field_kind_data)
            field = ConfigurationRecordField(
                name=field_data.get("name", ""),
                kind=field_kind,
                optional=field_data.get("optional", False)
            )
            fields.append(field)
        return ConfigurationRecord(fields=fields)

    elif element_type == "array":
        # For arrays, the elementType is a nested DataElement
        element_type_data = json_data.get("elementType", {})
        element_type_obj = create_data_element_from_json(element_type_data)
        # The value is the actual Property data
        value_data = json_data
        value = create_property_from_json_value(value_data.get("value"))
        return ArrayElement(element_type=element_type_obj, value=value)

    elif element_type == "short":
        value = create_property_from_json_value(json_data.get("value"))
        return ShortElement(value=value)

    elif element_type == "int":
        value = create_property_from_json_value(json_data.get("value"))
        return IntElement(value=value)

    elif element_type == "long":
        value = create_property_from_json_value(json_data.get("value"))
        return LongElement(value=value)

    elif element_type == "value":
        return ValueElement(
            value=json_data.get("value"),
            actual_value=json_data.get("actualValue")
        )

    elif element_type == "table":
        return TableNameElement(value=json_data.get("value"))

    elif element_type == "column":
        return ColumnNameElement(value=json_data.get("value"))

    elif element_type == "float":
        value = create_property_from_json_value(json_data.get("value"))
        return FloatElement(value=value)

    elif element_type == "double":
        value = create_property_from_json_value(json_data.get("value"))
        return DoubleElement(value=value)

    elif element_type == "string":
        value = create_property_from_json_value(json_data.get("value"))
        return StringElement(value=value)

    elif element_type == "spark_column":
        value = create_property_from_json_value(json_data.get("value"))
        return SparkColumnElement(value=value)

    elif element_type == "spark_expression":
        value = create_property_from_json_value(json_data.get("value"))
        return SparkExpressionElement(value=value)

    elif element_type == "boolean":
        value = create_property_from_json_value(json_data.get("value"))
        return BooleanElement(value=value)

    elif element_type == "enum":
        return EnumElement(
            default_value=json_data.get("defaultValue", ""),
            values=json_data.get("values", [])
        )

    elif element_type == "lookup":
        return LookupElement(
            default_value=json_data.get("defaultValue", ""),
            dataset_id=json_data.get("datasetId", ""),
            column_name=json_data.get("columnName", "")
        )

    elif element_type == "ruleset":
        return RulesetElement(value=json_data.get("value", ""))

    elif element_type == "secret":
        fields_data = json_data.get("fields", [])
        fields = []
        for field_data in fields_data:
            field_kind_data = field_data.get("kind", {})
            field_kind = create_data_element_from_json(field_kind_data)
            field = ConfigurationRecordField(
                name=field_data.get("name", ""),
                kind=field_kind,
                optional=field_data.get("optional", False)
            )
            fields.append(field)
        return SecretElement(fields=fields)

    elif element_type == "databricks_secret":
        value = create_property_from_json_value(json_data.get("value"))
        return DBSecretElement(value=value)

    elif element_type == "date":
        value = create_property_from_json_value(json_data.get("value"))
        return DateElement(value=value)

    elif element_type == "timestamp":
        value = create_property_from_json_value(json_data.get("value"))
        return TimestampElement(value=value)

    elif element_type == "unknown":
        return UnknownElementDeprecated(
            value=json_data.get("value"),
            actual_value=json_data.get("actualValue")
        )

    else:
        raise ValueError(f"Unknown DataElement type: {element_type}")


def create_data_element_from_json_string(json_string: str) -> DataElement:
    """Create a DataElement instance from a JSON string."""
    json_data = json.loads(json_string)
    return create_data_element_from_json(json_data)