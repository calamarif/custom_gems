
import dataclasses
import json
from dataclasses import dataclass

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class DynamicSelect(MacroSpec):
    name: str = "DynamicSelect"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Transform"
    minNumOfInputPorts: int = 1


    @dataclass(frozen=True)
    class DynamicSelectProperties(MacroProperties):
        # properties for the component with default values
        selectUsing: str = "SELECT_FIELD_TYPES"
        # DATA TYPES
        boolTypeChecked: bool = False
        strTypeChecked: bool = False
        intTypeChecked: bool = False
        shortTypeChecked: bool = False
        byteTypeChecked: bool = False
        longTypeChecked: bool = False
        floatTypeChecked: bool = False
        doubleTypeChecked: bool = False
        decimalTypeChecked: bool = False
        binaryTypeChecked: bool = False
        dateTypeChecked: bool = False
        timestampTypeChecked: bool = False
        structTypeChecked: bool = False
        schema: str = ''
        relation_name: List[str] = field(default_factory=list)
        targetTypes: str = ''
        # custom expression
        customExpression: str = ""

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
        return Dialog("DynamicSelect").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                Ports(),
                "content"
            )
            .addColumn(VerticalDivider(), width="content")
            .addColumn(
                StackLayout(gap=("1rem"), width="50%", height=("100bh"))
                .addElement(
                    StepContainer()
                        .addElement(
                            Step()
                                .addElement(
                                    StackLayout(height="100%")
                                        .addElement(TitleElement("Configuration"))
                                        .addElement(
                                            SelectBox("")
                                            .addOption("Select field types", "SELECT_FIELD_TYPES")
                                            .addOption("Select via expression", "SELECT_EXPR")
                                            .bindProperty("selectUsing")
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
                                            Condition()
                                            .ifEqual(
                                                PropExpr("component.properties.selectUsing"),
                                                StringExpr("SELECT_FIELD_TYPES"),
                                            )
                                            .then(
                                                StackLayout(gap=("1rem"), width="50%")
                                                .addElement(TitleElement("Select Field types"))
                                                .addElement(Checkbox("Boolean", "boolTypeChecked"))
                                                .addElement(Checkbox("String", "strTypeChecked"))
                                                .addElement(Checkbox("Integer", "intTypeChecked"))
                                                .addElement(Checkbox("Short", "shortTypeChecked"))
                                                .addElement(Checkbox("Byte", "byteTypeChecked"))
                                                .addElement(Checkbox("Long", "longTypeChecked"))
                                                .addElement(Checkbox("Float", "floatTypeChecked"))
                                                .addElement(Checkbox("Double", "doubleTypeChecked"))
                                                .addElement(Checkbox("Decimal", "decimalTypeChecked"))
                                                .addElement(Checkbox("Binary", "binaryTypeChecked"))
                                                .addElement(Checkbox("Date", "dateTypeChecked"))
                                                .addElement(Checkbox("Timestamp", "timestampTypeChecked"))
                                                .addElement(Checkbox("Struct", "structTypeChecked"))
                                            )
                                            .otherwise(
                                                StackLayout()
                                                .addElement(
                                                    TextBox("Enter Custom SQL Expression")
                                                    .bindPlaceholder(
                                                        """contains(column_name, 'user')""")
                                                    .bindProperty("customExpression")
                                                )
                                                .addElement(
                                                    AlertBox(
                                                        variant="success",
                                                        _children=[
                                                            Markdown(
                                                                "We can use following metadata columns in our expressions"
                                                                "\n"
                                                                "* **column_name** - Name of column, eg. name, country\n"
                                                                "* **column_type** - Type of column, eg. String \n"
                                                                "* **field_number** - Index of column in dataframe, eg. 0 for first column\n"
                                                            )
                                                        ]
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
        # Validate the component's state
        diagnostics = super(DynamicSelect, self).validate(context, component)
        if component.properties.selectUsing == "SELECT_FIELD_TYPES" and not (
            component.properties.boolTypeChecked or
            component.properties.strTypeChecked or
            component.properties.intTypeChecked or
            component.properties.shortTypeChecked or
            component.properties.byteTypeChecked or
            component.properties.longTypeChecked or
            component.properties.floatTypeChecked or
            component.properties.doubleTypeChecked or
            component.properties.decimalTypeChecked or
            component.properties.binaryTypeChecked or
            component.properties.dateTypeChecked or
            component.properties.timestampTypeChecked or
            component.properties.structTypeChecked
        ):
            diagnostics.append(
                Diagnostic("component.properties.selectUsing",
                           "Please select a field type from the options available", SeverityLevelEnum.Error))

        if component.properties.selectUsing == "SELECT_EXPR":
            if len(component.properties.customExpression) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.selectUsing",
                               "Please provide an expression", SeverityLevelEnum.Error))

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        target_types = []
        if newState.properties.boolTypeChecked:
            target_types.append("Boolean")
        if newState.properties.strTypeChecked:
            target_types.append("String")
        if newState.properties.intTypeChecked:
            target_types.append("Integer")
        if newState.properties.shortTypeChecked:
            target_types.append("Short")
        if newState.properties.byteTypeChecked:
            target_types.append("Byte")
        if newState.properties.longTypeChecked:
            target_types.append("Long")
        if newState.properties.floatTypeChecked:
            target_types.append("Float")
        if newState.properties.doubleTypeChecked:
            target_types.append("Double")
        if newState.properties.decimalTypeChecked:
            target_types.append("Decimal")
        if newState.properties.binaryTypeChecked:
            target_types.append("Binary")
        if newState.properties.dateTypeChecked:
            target_types.append("Date")
        if newState.properties.timestampTypeChecked:
            target_types.append("Timestamp")
        if newState.properties.structTypeChecked:
            target_types.append("Struct")

        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            targetTypes=json.dumps(target_types),
            relation_name = relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: DynamicSelectProperties) -> str:
        # Get the table name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"
        relation = "'" + table_name + "'"
        schema = props.schema
        targetTypes = props.targetTypes
        selectUsing = f"'{props.selectUsing}'"
        customExpression = "\"" + props.customExpression + "\""
        params = ",".join(x for x in [relation, schema, targetTypes, selectUsing, customExpression])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        targetTypesList = json.loads(parametersMap.get('targetTypes').replace("'", '"'))  # Parse targetTypes once
        return DynamicSelect.DynamicSelectProperties(
            relation_name=parametersMap.get('relation_name'),
            schema=parametersMap.get('schema'),
            targetTypes=parametersMap.get('targetTypes'),
            customExpression=parametersMap.get('customExpression'),
            selectUsing=parametersMap.get('selectUsing')[1:-1],
            boolTypeChecked="Boolean" in targetTypesList,
            strTypeChecked="String" in targetTypesList,
            intTypeChecked="Integer" in targetTypesList,
            shortTypeChecked="Short" in targetTypesList,
            byteTypeChecked="Byte" in targetTypesList,
            longTypeChecked="Long" in targetTypesList,
            floatTypeChecked="Float" in targetTypesList,
            doubleTypeChecked="Double" in targetTypesList,
            decimalTypeChecked="Decimal" in targetTypesList,
            binaryTypeChecked="Binary" in targetTypesList,
            dateTypeChecked="Date" in targetTypesList,
            timestampTypeChecked="Timestamp" in targetTypesList,
            structTypeChecked="Struct" in targetTypesList
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("targetTypes", properties.targetTypes),
                MacroParameter("customExpression", properties.customExpression),
                MacroParameter("selectUsing", properties.selectUsing),
            ],
        )
    def updateInputPortSlug(self, component: Component, context: SqlContext):
        # Handle changes in the component's state and return the new state
        target_types = []
        if component.properties.boolTypeChecked:
            target_types.append("Boolean")
        if component.properties.strTypeChecked:
            target_types.append("String")
        if component.properties.intTypeChecked:
            target_types.append("Integer")
        if component.properties.shortTypeChecked:
            target_types.append("Short")
        if component.properties.byteTypeChecked:
            target_types.append("Byte")
        if component.properties.longTypeChecked:
            target_types.append("Long")
        if component.properties.floatTypeChecked:
            target_types.append("Float")
        if component.properties.doubleTypeChecked:
            target_types.append("Double")
        if component.properties.decimalTypeChecked:
            target_types.append("Decimal")
        if component.properties.binaryTypeChecked:
            target_types.append("Binary")
        if component.properties.dateTypeChecked:
            target_types.append("Date")
        if component.properties.timestampTypeChecked:
            target_types.append("Timestamp")
        if component.properties.structTypeChecked:
            target_types.append("Struct")

        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            targetTypes=json.dumps(target_types),
            relation_name = relation_name
        )
        return component.bindProperties(newProperties)