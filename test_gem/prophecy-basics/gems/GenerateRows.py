import dataclasses
import json
from typing import List, Optional

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, StructField, IntegerType
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class GenerateRows(MacroSpec):
    name: str = "GenerateRows"
    projectName: str = "prophecy_basics"
    category: str = "Prepare"
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class GenerateRowsProperties(MacroProperties):
        relation_name: List[str] = field(default_factory=list)
        schema: str = ""
        init_expr: Optional[str] = None
        condition_expr: Optional[str] = None
        loop_expr: Optional[str] = None
        column_name: Optional[str] = None
        max_rows: Optional[str] = "100"
        force_mode: Optional[str] = "recursive"

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

    def dialog(self) -> Dialog:
        row_generation = StepContainer().addElement(
            Step().addElement(
                StackLayout(height="100%")
                .addElement(
                    TitleElement("*Configure row generation strategy")
                )
                .addElement(TextBox("Initialization expression").bindPlaceholder(
                    """Row generation would start from this. eg: 1 or payload.col_name""").bindProperty("init_expr"))
                .addElement(TextBox("Condition expression").bindPlaceholder(
                    """Breaking condition to stop loop. eg: value < 10 or value < payload.col_name""").bindProperty(
                    "condition_expr"))
                .addElement(TextBox("Loop expression (usually incremental)").bindPlaceholder(
                    """Step to increment with in every iteration. eg: value + 1 or value + payload.col_name""").bindProperty(
                    "loop_expr"))
            )
        )

        create_column = StepContainer().addElement(
            Step().addElement(
                StackLayout(height="100%")
                .addElement(
                    TitleElement("*Choose output column name")
                )
                .addElement(TextBox("").bindPlaceholder(
                    """value""").bindProperty("column_name"))
            )
        )

        advanced_options = StepContainer().addElement(
            Step().addElement(
                StackLayout(height="100%")
                .addElement(
                    TitleElement("Advanced options")
                )
                .addElement(TextBox("Max rows per iteration (default: 100)").bindPlaceholder(
                    """100""").bindProperty("max_rows"))
            )
        )

        return Dialog("GenerateRows").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                Ports(allowInputAddOrDelete=True, allowCustomOutputSchema=True),
                "content"
            )
            .addColumn(
                StackLayout(height="100%")
                .addElement(create_column)
                .addElement(row_generation)
                .addElement(advanced_options)
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super().validate(context, component)
        props = component.properties

        # Validate init_expr
        if props.init_expr is None or props.init_expr.strip() == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.init_expr",
                    "Initialization expression is required and cannot be empty",
                    SeverityLevelEnum.Error
                )
            )

        # Validate condition_expr
        if props.condition_expr is None or props.condition_expr.strip() == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.condition_expr",
                    "Condition expression is required and cannot be empty",
                    SeverityLevelEnum.Error
                )
            )

        # Validate loop_expr
        if props.loop_expr is None or props.loop_expr.strip() == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.loop_expr",
                    "Loop expression is required and cannot be empty",
                    SeverityLevelEnum.Error
                )
            )

        # Validate column_name
        if props.column_name is None or props.column_name.strip() == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.column_name",
                    "Column name is required and cannot be empty",
                    SeverityLevelEnum.Error
                )
            )

        # Validate max_rows - warning only, default to 100 if not provided
        if props.max_rows is not None:
            try:
                max_rows_int = int(props.max_rows)
                if max_rows_int <= 0:
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.max_rows",
                            "Max rows must be a positive integer, will default to 100",
                            SeverityLevelEnum.Warning
                        )
                    )
            except ValueError:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.max_rows",
                        "Max rows must be a valid integer, will default to 100",
                        SeverityLevelEnum.Warning
                    )
                )

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": field["name"], "dataType": field["dataType"]["type"]}
            for field in schema["fields"]
        ]
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: GenerateRowsProperties) -> str:

        # generate the actual macro call given the component's
        resolved_macro_name = f"{self.projectName}.{self.name}"

        def safe_str(val):
            """Safely convert a value to a SQL string literal, handling None and empty strings"""
            if val is None or val == "":
                return "''"
            if isinstance(val, str):
                # Escape single quotes for SQL string literals ('' represents a single quote in SQL)
                escaped = val.replace("'", "''")
                return f"'{escaped}'"
            return f"'{str(val)}'"

        # Default max_rows to 100 if not provided or invalid
        max_rows_value = props.max_rows
        if max_rows_value is None or max_rows_value.strip() == "":
            max_rows_value = "100"
        else:
            try:
                max_rows_int = int(max_rows_value)
                if max_rows_int <= 0:
                    max_rows_value = "100"
            except ValueError:
                max_rows_value = "100"

        arguments = [
            str(props.relation_name),
            safe_str(props.schema),
            "'" + str(props.init_expr) + "'",
            "'" + str(props.condition_expr) + "'",
            "'" + str(props.loop_expr) + "'",
            "'" + str(props.column_name) + "'",
            "'" + str(max_rows_value) + "'",
            "'" + str(props.force_mode) + "'"
        ]

        params = ",".join(arguments)
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    # --- GenerateRows.loadProperties -----------------------------------------
    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        p = self.convertToParameterMap(properties.parameters)

        # --- turn the stored text "['seed1']" back into a real list -------------
        raw_rel = p.get('relation_name', '')
        try:
            relation_name_list = (
                json.loads(raw_rel.replace("'", '"'))
                if raw_rel.strip() not in ['', '[]']
                else []
            )
        except json.JSONDecodeError:
            # if it's something like 'seed1' just wrap it in a list
            relation_name_list = [raw_rel.strip()] if raw_rel.strip() else []

        return GenerateRows.GenerateRowsProperties(
            relation_name=relation_name_list,  # <-- now always a list
            schema=p.get("schema", "").lstrip("'").rstrip("'") if p.get("schema", "") else "",
            init_expr=p.get('init_expr').lstrip("'").rstrip("'"),
            condition_expr=p.get('condition_expr').lstrip("'").rstrip("'"),
            loop_expr=p.get('loop_expr').lstrip("'").rstrip("'"),
            column_name=p.get('column_name').lstrip("'").rstrip("'"),
            max_rows=p.get('max_rows').lstrip("'").rstrip("'"),
            force_mode=p.get('force_mode').lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("init_expr", properties.init_expr),
                MacroParameter("condition_expr", properties.condition_expr),
                MacroParameter("loop_expr", properties.loop_expr),
                MacroParameter("column_name", properties.column_name),
                MacroParameter("max_rows", properties.max_rows),
                MacroParameter("force_mode", properties.force_mode)
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
            relation_name=relation_name
        )
        return component.bindProperties(newProperties)
