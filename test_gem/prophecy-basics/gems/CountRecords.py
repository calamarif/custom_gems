import dataclasses
import json

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *

from pyspark.sql import *
from pyspark.sql.functions import *


class CountRecords(MacroSpec):
    name: str = "CountRecords"
    projectName: str = "prophecy_basics"
    category: str = "Transform"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class CountRecordsProperties(MacroProperties):
        # properties for the component with default values
        relation_name: List[str] = field(default_factory=list)
        schema: str = ""
        column_names: List[str] = field(default_factory=list)
        count_method: str = "count_all_records"

    def dialog(self) -> Dialog:
        count_radio_box = (
            RadioGroup("Select count option")
            .addOption(
                "Count total number of records",
                "count_all_records",
                description=(
                    "This option will return the total row count of input table"
                ),
            )
            .addOption(
                "Count non-null records in selected columns",
                "count_non_null_records",
                description="This option will return the total row count excluding NULLs for the selected column(s)",
            )
            .addOption(
                "Count distinct non-null records in selected columns",
                "count_distinct_records",
                description="This option will return the distinct row count excluding NULLs for the selected column(s)",
            )
            .setOptionType("button")
            .setVariant("medium")
            .setButtonStyle("solid")
            .bindProperty("count_method")
        )

        dialog = Dialog("count_records_dialog_box").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(Step().addElement(count_radio_box))
                )
                .addElement(
                    Condition()
                    .ifNotEqual(
                        PropExpr("component.properties.count_method"),
                        StringExpr("count_all_records"),
                    )
                    .then(
                        StepContainer().addElement(
                            Step().addElement(
                                Condition()
                                .ifNotEqual(
                                    PropExpr("component.properties.count_method"),
                                    StringExpr("count_all_records"),
                                )
                                .then(
                                    StackLayout(height="100%")
                                    .addElement(TitleElement("Select columns to count"))
                                    .addElement(
                                        SchemaColumnsDropdown("", appearance="minimal")
                                        .withMultipleSelection()
                                        .bindSchema("component.ports.inputs[0].schema")
                                        .bindProperty("column_names")
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(CountRecords, self).validate(context, component)
        if component.properties.count_method == "count_non_null_records":
            if len(component.properties.column_names) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.column_names",
                        f"Select atleast one column to get count",
                        SeverityLevelEnum.Error,
                    )
                )
            elif len(component.properties.column_names) > 0:
                missingKeyColumns = [
                    col
                    for col in component.properties.column_names
                    if col not in component.properties.schema
                ]
                if missingKeyColumns:
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.column_names",
                            f"Selected columns {missingKeyColumns} are not present in input schema - {component.properties.schema}.",
                            SeverityLevelEnum.Error,
                        )
                    )
        return diagnostics

    def get_relation_names(self, component: Component, context: SqlContext):
        all_upstream_nodes = []
        for inputPort in component.ports.inputs:
            upstreamNode = None
            for connection in context.graph.connections:
                if connection.targetPort == inputPort.id:
                    upstreamNodeId = connection.source
                    upstreamNode = context.graph.nodes.get(upstreamNodeId)
            all_upstream_nodes.append(upstreamNode)

        relation_name = []
        for upstream_node in all_upstream_nodes:
            if upstream_node is None or upstream_node.label is None:
                relation_name.append("")
            else:
                relation_name.append(upstream_node.label)

        return relation_name

    def onChange(
        self, context: SqlContext, oldState: Component, newState: Component
    ) -> Component:
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": field["name"], "dataType": field["dataType"]["type"]}
            for field in schema["fields"]
        ]
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: CountRecordsProperties) -> str:
        # Generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        def safe_str(val):
            if val is None or val == "":
                return "''"
            if isinstance(val, list):
                return str(val)
            return f"'{val}'"

        arguments = [
            str(props.relation_name),
            safe_str(props.column_names),
            safe_str(props.count_method),
        ]

        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return CountRecords.CountRecordsProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            schema=parametersMap.get("schema"),
            column_names=json.loads(
                parametersMap.get("column_names").replace("'", '"')
            ),
            count_method=parametersMap.get('count_method').lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("column_names", json.dumps(properties.column_names)),
                MacroParameter("count_method", str(properties.count_method)),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": field["name"], "dataType": field["dataType"]["type"]}
            for field in schema["fields"]
        ]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
        )
        return component.bindProperties(newProperties)

    def applyPython(self, spark: SparkSession, in0: DataFrame) -> DataFrame:
        column_names = self.props.column_names
        count_method = self.props.count_method

        if count_method == "count_all_records":
            agg_exprs = [count(lit(1)).alias("total_records")]

        elif count_method == "count_non_null_records":
            if not column_names:
                agg_exprs = [count(lit(1)).alias("total_records")]
            else:
                agg_exprs = [count(col(c)).alias(f"{c}_count") for c in column_names]

        elif count_method == "count_distinct_records":
            if not column_names:
                agg_exprs = [count(lit(1)).alias("total_records")]
            else:
                agg_exprs = [countDistinct(col(c)).alias(f"{c}_distinct_count") for c in column_names]

        else:
            agg_exprs = [count(lit(1)).alias("total_records")]

        return in0.agg(*agg_exprs)
