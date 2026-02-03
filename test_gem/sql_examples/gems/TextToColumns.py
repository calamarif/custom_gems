import re
from dataclasses import dataclass

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class TextToColumns(MacroSpec):
    name: str = "TextToColumns"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Parse"
    minNumOfInputPorts: int = 1

    @dataclass(frozen=True)
    class TextToColumnsProperties(MacroProperties):
        # properties for the component with default values
        columnNames: str = ""
        relation_name: List[str] = field(default_factory=list)
        delimiter: str = ""
        split_strategy: Optional[str] = ""
        noOfColumns: int = 1
        leaveExtraCharLastCol: str = "Leave extra in last column"
        splitColumnPrefix: str = "root"
        splitColumnSuffix: str = "generated"
        splitRowsColumnName: str = "generated_column"

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
                Ports(),
                "content"
            )
            .addColumn(
                StackLayout()
                .addElement(
                    StackLayout(height="100%")
                    .addElement(
                        TitleElement("Select Column to Split")
                    )
                    .addElement(
                        StepContainer()
                        .addElement(
                            Step()
                                .addElement(
                                    StackLayout(height="100%")
                                        .addElement(
                                            SchemaColumnsDropdown("", appearance = "minimal")
                                            .bindSchema("component.ports.inputs[0].schema")
                                            .bindProperty("columnNames")
                                            .showErrorsFor("columnNames")
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
                                            .addElement(TitleElement("Delimiter"))
                                            .addElement(
                                                TextBox("").bindPlaceholder("delimiter").bindProperty("delimiter")
                                            )
                                            .addElement(
                                                AlertBox(
                                                    variant="success",
                                                    _children=[
                                                        Markdown(
                                                            "**Column Split Delimiter Examples:**"
                                                            "\n"
                                                            "- **Tab-separated values:**"
                                                            "\n"
                                                            "   **Delimiter:** \\t"
                                                            "\n"
                                                            "   Example: Value1<tab>Value2<tab>Value3"
                                                            "\n"
                                                            "- **Newline-separated values:**"
                                                            "\n"
                                                            "   **Delimiter:** \\n"
                                                            "\n"
                                                            "   Example: Value1\\nValue2\\nValue3"
                                                            "\n"
                                                            "- **Pipe-separated values:**"
                                                            "\n"
                                                            "   **Delimiter:** |"
                                                            "\n"
                                                            "   Example: Value1|Value2|nValue3"
                                                        )
                                                    ]
                                                )
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
                                        .addElement(
                                            RadioGroup("Select Split Strategy")
                                            .addOption("Split to columns", "splitColumns")
                                            .addOption("Split to rows", "splitRows")
                                            .bindProperty("split_strategy")
                                        )
                                        .addElement(
                                            Condition()
                                            .ifEqual(PropExpr("component.properties.split_strategy"), StringExpr("splitColumns"))
                                            .then(
                                                StackLayout(height="100%")
                                                .addElement(
                                                    ColumnsLayout(gap="1rem", height="100%")
                                                    .addColumn(
                                                            NumberBox("Number of columns", placeholder=1,requiredMin=1)
                                                            .bindProperty("noOfColumns")
                                                    )
                                                    .addColumn()
                                                    .addColumn()
                                                    .addColumn()
                                                    .addColumn()
                                                )
                                                .addElement(
                                                    ColumnsLayout(gap="1rem", height="100%")
                                                    .addColumn(
                                                        SelectBox(titleVar="Extra Characters", defaultValue="Leave extra in last column")
                                                        .addOption("Leave extra in last column", "leaveExtraCharLastCol")
                                                        .bindProperty("leaveExtraCharLastCol")
                                                    )
                                                    .addColumn(
                                                        TextBox("Column Prefix")
                                                        .bindPlaceholder("Enter Generated Column Prefix")
                                                        .bindProperty("splitColumnPrefix")
                                                    )
                                                    .addColumn(
                                                        TextBox("Column Suffix")
                                                        .bindPlaceholder("Enter Generated Column Suffix")
                                                        .bindProperty("splitColumnSuffix")
                                                    )
                                                )
                                            )
                                        )
                                        .addElement(
                                            Condition()
                                            .ifEqual(PropExpr("component.properties.split_strategy"), StringExpr("splitRows"))
                                            .then(
                                                ColumnsLayout(gap="1rem", height="100%")
                                                .addColumn(
                                                    TextBox("Generated Column Name")
                                                    .bindPlaceholder("Enter Generated Column Name")
                                                    .bindProperty("splitRowsColumnName")
                                                )
                                                .addColumn()
                                                .addColumn()
                                            )
                                        )
                                )
                        )
                )
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(TextToColumns, self).validate(context, component)
        if len(component.properties.columnNames) == 0:
            diagnostics.append(
                Diagnostic("properties.columnNames", "column name can not be empty", SeverityLevelEnum.Error))
        if len(component.properties.delimiter) == 0:
            diagnostics.append(
                Diagnostic("properties.delimiter", "delimiter can not be empty", SeverityLevelEnum.Error))
        if len(component.properties.split_strategy) == 0:
            diagnostics.append(
                Diagnostic("properties.split_strategy", "split strategy can not be empty", SeverityLevelEnum.Error))
        if component.properties.split_strategy == "splitColumns":
            if component.properties.noOfColumns < 1:
                diagnostics.append(
                    Diagnostic("properties.noOfColumns", "No of columns should be more than or equals to 1",
                               SeverityLevelEnum.Error))
            if len(component.properties.splitColumnPrefix) == 0:
                diagnostics.append(
                    Diagnostic("properties.splitColumnPrefix", "Please provide a prefix for generated column",
                               SeverityLevelEnum.Error))
            if len(component.properties.splitColumnSuffix) == 0:
                diagnostics.append(
                    Diagnostic("properties.splitColumnSuffix", "Please provide a suffix for generated column",
                               SeverityLevelEnum.Error))
        if component.properties.split_strategy == "splitRows":
            if len(component.properties.splitRowsColumnName) == 0:
                diagnostics.append(
                    Diagnostic("properties.splitRowsColumnName", "Please provide a generated column name",
                               SeverityLevelEnum.Error))

        # Extract all column names from the schema
        field_names = [field["name"] for field in component.ports.inputs[0].schema["fields"]]

        if len(component.properties.columnNames) > 0:
            if component.properties.columnNames not in field_names:
                diagnostics.append(
                    Diagnostic("component.properties.columnNames", f"Selected column {component.properties.columnNames} is not present in input schema.",
                               SeverityLevelEnum.Error))

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the newState's state and return the new state
        relation_name = self.get_relation_names(component, context)
        return (replace(newState, properties=replace(newState.properties, relation_name=relation_name)))

    def apply(self, props: TextToColumnsProperties) -> str:
        # You can now access self.relation_name here
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Get the Single Table Name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        # Handle delimiter with special characters
        escaped_delimiter = re.escape(props.delimiter).replace("\\", "\\\\\\")

        arguments = [
            "'" + table_name + "'",
            "'" + props.columnNames + "'",
            "\"" + escaped_delimiter + "\"",
            "'" + props.split_strategy + "'",
            str(props.noOfColumns),
            "'" + props.leaveExtraCharLastCol + "'",
            "'" + props.splitColumnPrefix + "'",
            "'" + props.splitColumnSuffix + "'",
            "'" + props.splitRowsColumnName + "'"
        ]
        params = ",".join([param for param in arguments])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        print(f"The name of the parametersMap is {parametersMap}")
        return TextToColumns.TextToColumnsProperties(
            relation_name=parametersMap.get('relation_name'),
            columnNames=parametersMap.get('columnNames'),
            delimiter=parametersMap.get('delimiter'),
            split_strategy=parametersMap.get('split_strategy'),
            noOfColumns=int(parametersMap.get('noOfColumns')),
            leaveExtraCharLastCol=parametersMap.get('leaveExtraCharLastCol'),
            splitColumnPrefix=parametersMap.get('splitColumnPrefix'),
            splitColumnSuffix=parametersMap.get('splitColumnSuffix'),
            splitRowsColumnName=parametersMap.get('splitRowsColumnName')
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("columnNames", properties.columnNames),
                MacroParameter("delimiter", properties.delimiter),
                MacroParameter("split_strategy", properties.split_strategy),
                MacroParameter("noOfColumns", str(properties.noOfColumns)),
                MacroParameter("leaveExtraCharLastCol", properties.leaveExtraCharLastCol),
                MacroParameter("splitColumnPrefix", properties.splitColumnPrefix),
                MacroParameter("splitColumnSuffix", properties.splitColumnSuffix),
                MacroParameter("splitRowsColumnName", properties.splitRowsColumnName)
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)
        return (replace(component, properties=replace(component.properties, relation_name=relation_name)))