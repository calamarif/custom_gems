import dataclasses
import json
from dataclasses import dataclass

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class MultiColumnEdit(MacroSpec):
    name: str = "MultiColumnEdit"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Prepare"
    minNumOfInputPorts: int = 1

    @dataclass(frozen=True)
    class MultiColumnEditProperties(MacroProperties):
        # properties for the component with default values
        columnNames: List[str] = field(default_factory=list)
        schema: str = ''
        prefixSuffixOption: str = "Prefix"
        prefixSuffixToBeAdded: str = ""
        changeOutputFieldName: bool = False
        expressionToBeApplied: str = ""
        relation_name: List[str] = field(default_factory=list)

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
        dialog = Dialog("MultiColumnEdit") \
            .addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer()
                    .addElement(
                        Step()
                        .addElement(
                            StackLayout(height="100%")
                            .addElement(
                                SchemaColumnsDropdown("Selected columns to edit", appearance = "minimal")
                                .withMultipleSelection().bindSchema("component.ports.inputs[0].schema").bindProperty(
                                    "columnNames")
                            )
                            .addElement(
                                StackLayout(height="100%")
                                .addElement(
                                    Checkbox(
                                        "Maintain the original columns and add prefix/suffix to the new column").bindProperty(
                                        "changeOutputFieldName")
                                )
                                .addElement(
                                    ColumnsLayout(gap="1rem", height="100%")
                                    .addColumn(
                                        SelectBox("").addOption("Prefix", "Prefix").addOption("Suffix",
                                                                                              "Suffix").bindProperty(
                                            "prefixSuffixOption"), "10%"
                                    )
                                    .addColumn(
                                        TextBox("").bindPlaceholder("Example: new_").bindProperty(
                                            "prefixSuffixToBeAdded"), "20%"
                                    )
                                    .addColumn()
                                )
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer()
                    .addElement(
                        Step()
                        .addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Build a single expression to apply to all selected columns"))
                            .addElement(
                                ExpressionBox(language="sql")
                                .bindProperty("expressionToBeApplied")
                                .bindPlaceholder(
                                    "Write sql expression considering `column_value` as column value and `column_name` as column name string literal. Example:\nFor column value: column_value * 100\nFor column name: upper(column_name)")
                                .withGroupBuilder(GroupBuilderType.EXPRESSION)
                                .withUnsupportedExpressionBuilderTypes([ExpressionBuilderType.INCREMENTAL_EXPRESSION])
                            )
                        )
                    )
                )
                .addElement(
                    AlertBox(
                        variant="success",
                        _children=[
                            Markdown(
                                "**In Select Expression, use column_name to refer to the column’s name and column_value to apply logic on its value** \n\n"
                                "* **column_name** : Use **column_name** as a placeholder in your expression—it will automatically apply the logic to each selected column in the table. \n\n"
                                "* **column_value** : Use **column_value** as a placeholder in your expression—it dynamically represents the value of each selected column when applying the logic. \n\n"
                                "Let's understand from a simple example \n\n"
                                "**Input:**\n\n"
                                "| id | country | first_name | age |\n"
                                "|----|---------|------------|------|\n"
                                "| 1  | usa     | John       | 50   |\n\n"


                                "➤ **Example of column_name**\n"
                                "✔ Selected columns to edit are **country, first_name**\n"
                                "✔ Expression: **upper(column_name)** \n\n"

                                "**Output:**\n\n"
                                "| id | country | first_name | age |\n"
                                "|----|---------|------------|------|\n"
                                "| 1  | USA     | JOHN       | 50   |\n\n"

                                "➤ **Example of column_value**\n"
                                "✔ Selected column to edit is **age**\n"
                                "✔ Expression: **column_value*1.5** \n\n"
                                "**Output:**\n\n"
                                "| id | country | first_name | age |\n"
                                "|----|---------|------------|------|\n"
                                "| 1  | USA     | JOHN       | 75   |\n\n"
                            )
                        ]
                    )
                )
            )
        )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(MultiColumnEdit, self).validate(context, component)
        props = component.properties

        if len(component.properties.columnNames) == 0:
            diagnostics.append(
                Diagnostic("component.properties.columnNames", "Please select a column for the operation",
                           SeverityLevelEnum.Error))

        if len(component.properties.expressionToBeApplied) == 0:
            diagnostics.append(
                Diagnostic("component.properties.expressionToBeApplied", "Please give an expression to apply",
                           SeverityLevelEnum.Error))

        if component.properties.changeOutputFieldName:
            if len(component.properties.prefixSuffixOption) > 0:
                if len(component.properties.prefixSuffixToBeAdded) == 0:
                    diagnostics.append(
                        Diagnostic("component.properties.prefixSuffixToBeAdded", "Please add prefix or suffix",
                                   SeverityLevelEnum.Error))

        if len(component.properties.columnNames) > 0 :
            missingKeyColumns = [col for col in component.properties.columnNames if
                                 col not in component.properties.schema]
            if missingKeyColumns:
                diagnostics.append(
                    Diagnostic("component.properties.columnNames", f"Selected columns {missingKeyColumns} are not present in input schema.", SeverityLevelEnum.Error)
                )

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: MultiColumnEditProperties) -> str:

        # Get the table name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        # Get existing column names
        allColumnNames = [field["name"] for field in json.loads(props.schema)]

        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        arguments = [
            "'" + table_name + "'",
            "\"" + props.expressionToBeApplied + "\"",
            str(allColumnNames),
            str(props.columnNames),
            str(props.changeOutputFieldName).lower(),
            "'" + props.prefixSuffixOption + "'",
            "'" + props.prefixSuffixToBeAdded + "'"
        ]
        params = ",".join([param for param in arguments])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # Load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return MultiColumnEdit.MultiColumnEditProperties(
            relation_name=parametersMap.get('relation_name'),
            schema=parametersMap.get('schema'),
            columnNames=json.loads(parametersMap.get('columnNames').replace("'", '"')),
            expressionToBeApplied=parametersMap.get('expressionToBeApplied'),
            changeOutputFieldName=parametersMap.get('changeOutputFieldName').lower() == "true",
            prefixSuffixOption=parametersMap.get('prefixSuffixOption'),
            prefixSuffixToBeAdded=parametersMap.get('prefixSuffixToBeAdded')
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert the component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("columnNames", json.dumps(properties.columnNames)),
                MacroParameter("expressionToBeApplied", properties.expressionToBeApplied),
                MacroParameter("changeOutputFieldName", str(properties.changeOutputFieldName).lower()),
                MacroParameter("prefixSuffixOption", properties.prefixSuffixOption),
                MacroParameter("prefixSuffixToBeAdded", properties.prefixSuffixToBeAdded)
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name
        )
        return component.bindProperties(newProperties)