import dataclasses
import json
from dataclasses import dataclass

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class MultiColumnRename(MacroSpec):
    name: str = "MultiColumnRename"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Prepare"
    minNumOfInputPorts: int = 1

    @dataclass(frozen=True)
    class MultiColumnRenameProperties(MacroProperties):
        # properties for the component with default values
        schema: str = ''
        columnNames: List[str] = field(default_factory=list)
        renameMethod: str = ""
        editOperation: str = "Add"
        editType: str = ""
        editWith: str = ""
        suffix: str = ""
        customExpression: str = ""
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
        horizontalDivider = HorizontalDivider()
        renameMethod = SelectBox("") \
            .addOption("Edit prefix/suffix", "editPrefixSuffix") \
            .addOption("Advanced rename", "advancedRename") \
            .bindProperty("renameMethod")

        dialog = Dialog("MultiColumnRename") \
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
                            .addElement(TitleElement("Select columns to rename"))
                            .addElement(
                                SchemaColumnsDropdown("", appearance = "minimal")
                                .withMultipleSelection()
                                .bindSchema("component.ports.inputs[0].schema")
                                .bindProperty("columnNames")
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
                            .addElement(TitleElement("Rename method"))
                            .addElement(
                                ColumnsLayout(gap="1rem", height="100%")
                                .addColumn(renameMethod, "1fr")
                                .addColumn(
                                    StackLayout(height="100%")
                                    .addElement(
                                        Condition()
                                        .ifEqual(
                                            PropExpr("component.properties.renameMethod"),
                                            StringExpr("editPrefixSuffix")
                                        )
                                        .then(
                                            ColumnsLayout(gap="1rem", height="100%")
                                            .addColumn(
                                                SelectBox("").addOption("Prefix", "Prefix").addOption("Suffix",
                                                                                                      "Suffix").bindProperty(
                                                    "editType")
                                            )
                                            .addColumn(
                                                TextBox("").bindPlaceholder("NEW_").bindProperty("editWith")
                                            )
                                            .addColumn()
                                        )
                                    )
                                    , "3fr"
                                )
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr("component.properties.renameMethod"),
                                    StringExpr("advancedRename")
                                )
                                .then(
                                    ColumnsLayout(gap=("1rem"), height=("100%"))
                                    .addColumn(
                                        StackLayout(height="100%")
                                        .addElement(
                                            ExpressionBox(language="sql")
                                            .bindPlaceholder(
                                                "Write sql expression considering `column_name` as column name string literal. Example:\n For column name: upper(column_name)")
                                            .withGroupBuilder(GroupBuilderType.EXPRESSION)
                                            .withUnsupportedExpressionBuilderTypes(
                                                [ExpressionBuilderType.INCREMENTAL_EXPRESSION])
                                            .bindProperty("customExpression")
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
                .addElement(
                    AlertBox(
                        variant="success",
                        _children=[
                            Markdown(
                                "**In Advanced rename, use column_name to refer to the column’s name** \n\n"
                                "* **column_name** : Use **column_name** as a placeholder in your expression—it will automatically apply the logic to each selected column in the table. \n\n"
                                "Let's understand from a simple example \n\n"
                                "**Input:**\n\n"
                                "| id | country | first_name | age |\n"
                                "|----|---------|------------|------|\n"
                                "| 1  | usa     | John       | 50   |\n\n"


                                "➤ **Example of column_name**\n"
                                "✔ Selected columns to rename are **country, first_name**\n"
                                "✔ Expression: **concat(column_name,'_new')** \n\n"

                                "**Output:**\n\n"
                                "| id | country_new | first_name_new | age |\n"
                                "|----|-------------|----------------|------|\n"
                                "| 1  | usa         | John           | 50   |\n\n"
                            )
                        ]
                    )
                )
            )
        )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(MultiColumnRename, self).validate(context, component)
        props = component.properties

        if len(component.properties.columnNames) == 0:
            diagnostics.append(
                Diagnostic("component.properties.columnNames", "Select Column to Rename", SeverityLevelEnum.Error))

        if len(component.properties.renameMethod) == 0:
            diagnostics.append(
                Diagnostic("component.properties.renameMethod", "Select Rename Method", SeverityLevelEnum.Error))

        if (
                component.properties.renameMethod == "editPrefixSuffix" and
                (
                        len(component.properties.editType) == 0 or
                        len(component.properties.editWith) == 0
                )
        ):
            diagnostics.append(
                Diagnostic("component.properties.renameMethod", "Missing Properties for Edit prefix/suffix Operation",
                           SeverityLevelEnum.Error))

        if (component.properties.renameMethod == "advancedRename" and len(component.properties.customExpression) == 0):
            diagnostics.append(
                Diagnostic("component.properties.advancedRename", "Missing Properties for Advanced rename",
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

    def apply(self, props: MultiColumnRenameProperties) -> str:
        # Get the table name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        # Get existing column names
        allColumnNames = [field["name"] for field in json.loads(props.schema)]

        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"
        arguments = [
            "'" + table_name + "'",
            str(props.columnNames),
            "'" + str(props.renameMethod) + "'",
            str(allColumnNames),
            "'" + str(props.editType) + "'",
            "'" + str(props.editWith) + "'",
            '"' + str(props.customExpression) + '"'
        ]
        params = ",".join([param for param in arguments])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:

        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return MultiColumnRename.MultiColumnRenameProperties(
            relation_name=parametersMap.get('relation_name'),
            schema=parametersMap.get('schema'),
            columnNames=json.loads(parametersMap.get('columnNames').replace("'", '"')),
            renameMethod=parametersMap.get('renameMethod'),
            editOperation=parametersMap.get('editOperation'),
            editType=parametersMap.get('editType'),
            editWith=parametersMap.get('editWith'),
            customExpression=parametersMap.get('customExpression')
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("columnNames", json.dumps(properties.columnNames)),
                MacroParameter("renameMethod", properties.renameMethod),
                MacroParameter("editOperation", properties.editOperation),
                MacroParameter("editType", properties.editType),
                MacroParameter("editWith", properties.editWith),
                MacroParameter("customExpression", properties.customExpression)
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