from dataclasses import dataclass
import json

from collections import defaultdict
from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class XMLParse(MacroSpec):
    name: str = "XMLParse"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Parse"

    @dataclass(frozen=True)
    class XMLParseProperties(MacroProperties):
        # properties for the component with default values
        columnNames: List[str] = field(default_factory=list)
        relation_name: List[str] = field(default_factory=list)
        columnSuffix: str = "parsed"

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
        return Dialog("Macro").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                Ports(allowInputAddOrDelete=True),
                "content"
            )
            .addColumn(
                StackLayout()
                .addElement(
                    StackLayout(height="100%")
                    .addElement(
                        StackLayout()
                        .addElement(
                            AlertBox(
                                variant="success",
                                _children=[
                                    Markdown(
                                        "**Important Settings Required!**"
                                        "\n"
                                        "To use this feature, please enable the following settings in Output tab"
                                        "\n"
                                        "   - **Enable Custom Schema**"
                                        "\n"
                                        "   - **Run Infer from Cluster**"
                                    )
                                ]
                            )
                        )
                        .addElement(
                            StepContainer()
                                .addElement(
                                    Step()
                                        .addElement(
                                            StackLayout(height="100%")
                                                .addElement(
                                                    SchemaColumnsDropdown("Select Column to Split", appearance = "minimal")
                                                    .withSearchEnabled()
                                                    .withMultipleSelection()
                                                    .bindSchema("component.ports.inputs[0].schema")
                                                    .bindProperty("columnNames")
                                                    .showErrorsFor("columnNames")
                                                )
                                                .addElement(
                                                    ColumnsLayout(gap="1rem", height="100%")
                                                    .addColumn(
                                                        TextBox("Parsed Column Suffix")
                                                        .bindPlaceholder("Enter Parsed Column Suffix")
                                                        .bindProperty("columnSuffix"),"20%"
                                                    )
                                                )
                                        )
                                )
                        )
                    )
                )
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(XMLParse, self).validate(context, component)

        if len(component.properties.columnNames) == 0:
            diagnostics.append(
                Diagnostic("component.properties.columnNames", "Please select a column for the operation",
                           SeverityLevelEnum.Error))

        if len(component.properties.columnSuffix) == 0:
            diagnostics.append(
                Diagnostic("properties.columnSuffix", "Please provide a suffix for generated column",
                           SeverityLevelEnum.Error))

        # Extract all column names from the schema
        field_names = [field["name"] for field in component.ports.inputs[0].schema["fields"]]

        if len(component.properties.columnNames) > 0 :
            missingKeyColumns = [col for col in component.properties.columnNames if
                                 col not in field_names]
            if missingKeyColumns:
                diagnostics.append(
                    Diagnostic("component.properties.columnNames", f"Selected columns {missingKeyColumns} are not present in input schema.", SeverityLevelEnum.Error)
                )

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the newState's state and return the new state
        relation_name = self.get_relation_names(component, context)
        return (replace(newState, properties=replace(newState.properties, relation_name=relation_name)))

    def apply(self, props: XMLParseProperties) -> str:
        # You can now access self.relation_name here
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Get the Single Table Name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        arguments = [
            "'" + table_name + "'",
            str(props.columnNames),
            "'" + props.columnSuffix + "'"
        ]
        params = ",".join([param for param in arguments])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        print(f"The name of the parametersMap is {parametersMap}")
        return XMLParse.XMLParseProperties(
            relation_name=parametersMap.get('relation_name'),
            columnNames=json.loads(parametersMap.get('columnNames').replace("'", '"')),
            columnSuffix=parametersMap.get('columnSuffix')
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", properties.relation_name),
                MacroParameter("columnNames", json.dumps(properties.columnNames)),
                MacroParameter("columnSuffix", properties.columnSuffix)
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)
        return (replace(component, properties=replace(component.properties, relation_name=relation_name)))