import dataclasses
from dataclasses import dataclass, field
from typing import List

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class BRE_SQL_Gem_basic(MacroSpec):
    name: str = "BRE_SQL_Gem_basic"
    projectName: str = "SQLGems" # This should be changed to the actual project name if different
    category: str = "Transform"
    minNumOfInputPorts: int = 1
    maxNumOfInputPorts: int = 1
    maxNumOfOutputPorts: int = 1

    @dataclass(frozen=True)
    class BRE_SQL_Gem_basicProperties(MacroProperties):
        # properties for the component with default values
        input_column: SColumn = field(default=None)
        output_column: str = ""
        rule_condition: str = ""
        rule_output_value: str = ""
        schema: str = ''
        input_table: str = ""

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
        dialog = Dialog("BRE_SQL_Gem_basic") \
            .addElement(
                ColumnsLayout(gap="1rem", height="100%")
                .addColumn(
                    StackLayout(height="100%")
                    .addElement(
                        StackLayout()
                        .addElement(
                            # This will be the Input Column selection
                            SchemaColumnsDropdown(
                                "Input Column",
                                description="Select an existing column from the input dataset to apply the business rule on."
                            )
                            .bindProperty("input_column")
                            .bindSchema("component.ports.inputs[0].schema")
                        )
                        .addElement(
                            # This will be the Output Column input
                            TextBox(
                                "Output Column",
                                description="Specify the name for the new output column that will store the result of the business rule. If the column already exists, it will be updated."
                            )
                            .bindProperty("output_column")
                            .bindPlaceholder("e.g., CalculatedValue")
                        )
                        .addElement(
                            # This will be the Condition input
                            ExpressionBox(
                                "Condition",
                                description="Define the condition. Use 'Input_Column' to refer to the selected input column. Example: Input_Column > 100"
                            )
                            .bindProperty("rule_condition")
                            .bindPlaceholder(
                                "e.g., Input_Column > 100"
                            )
                            .withGroupBuilder(GroupBuilderType.EXPRESSION)
                            .withUnsupportedExpressionBuilderTypes([ExpressionBuilderType.AGGREGATE])
                        )
                        .addElement(
                            # This will be the Output Value input
                            ExpressionBox(
                                "Output Value",
                                description="Define the value to assign if the condition is met. Example: 'Value is High'"
                            )
                            .bindProperty("rule_output_value")
                            .bindPlaceholder(
                                "e.g., 'this row is greater than 100'"
                            )
                            .withGroupBuilder(GroupBuilderType.EXPRESSION)
                            .withUnsupportedExpressionBuilderTypes([ExpressionBuilderType.AGGREGATE])
                        )
                    ), "2fr" # This column takes 2 parts of the width
                )
                .addColumn(
                    Ports(), "1fr" # This column takes 1 part of the width
                )
            )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(BRE_SQL_Gem_basic, self).validate(context, component)
        props = component.properties

        if props.input_column is None or props.input_column.columnName == "":
            diagnostics.append(
                Diagnostic("component.properties.input_column", "Please select an input column.",
                           SeverityLevelEnum.Error))

        if props.output_column == "":
            diagnostics.append(
                Diagnostic("component.properties.output_column", "Please provide an output column name.",
                           SeverityLevelEnum.Error))

        if props.rule_condition == "":
            diagnostics.append(
                Diagnostic("component.properties.rule_condition", "Please provide the condition.",
                           SeverityLevelEnum.Error))

        if props.rule_output_value == "":
            diagnostics.append(
                Diagnostic("component.properties.rule_output_value", "Please provide the output value.",
                           SeverityLevelEnum.Error))

        if props.input_column is not None and props.input_column.columnName != "" and props.schema != "":
            input_column_name = props.input_column.columnName
            schema_fields = [field["name"] for field in json.loads(props.schema)]
            if input_column_name not in schema_fields:
                diagnostics.append(
                    Diagnostic("component.properties.input_column",
                               f"Input column '{input_column_name}' not found in the input schema.",
                               SeverityLevelEnum.Error))

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        
        relation_names = self.get_relation_names(newState, context)
        input_table = relation_names[0] if relation_names else ""

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            input_table=input_table
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: BRE_SQL_Gem_basicProperties) -> str:
        input_col_name = props.input_column.columnName if props.input_column else ""
        return f"{{{{ BRE_SQL_Gem_basic(input_table='{props.input_table}', input_column='{input_col_name}', output_column='{props.output_column}', rule_condition=\"\"\"{props.rule_condition}\"\"\", rule_output_value=\"\"\"{props.rule_output_value}\"\"\") }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        return BRE_SQL_Gem_basic.BRE_SQL_Gem_basicProperties(
            input_column=SColumn(parametersMap.get("input_column", "")),
            output_column=parametersMap.get("output_column", ""),
            rule_condition=parametersMap.get("rule_condition", ""),
            rule_output_value=parametersMap.get("rule_output_value", ""),
            schema=parametersMap.get("schema", ""),
            input_table=parametersMap.get("input_table", "")
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("input_column", properties.input_column.columnName),
                MacroParameter("output_column", properties.output_column),
                MacroParameter("rule_condition", properties.rule_condition),
                MacroParameter("rule_output_value", properties.rule_output_value),
                MacroParameter("schema", properties.schema),
                MacroParameter("input_table", properties.input_table)
            ]
        )
