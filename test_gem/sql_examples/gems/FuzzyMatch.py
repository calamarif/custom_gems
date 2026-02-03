import dataclasses
from collections import defaultdict

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class MatchField(ABC):
    pass


class FuzzyMatch(MacroSpec):
    name: str = "FuzzyMatch"
    projectName: str = "SnowflakeSqlBasics"
    category: str = "Transform"
    minNumOfInputPorts: int = 1

    @dataclass(frozen=True)
    class AddMatchField(MatchField):
        columnName: str = ""
        matchFunction: str = "custom"

    @dataclass(frozen=True)
    class FuzzyMatchProperties(MacroProperties):
        # properties for the component with default values
        mode: str = ""
        sourceIdCol: str = ""
        recordIdCol: str = ""
        matchThresholdPercentage: int = 80
        activeTab: str = "configuration"
        includeSimilarityScore: bool = False
        matchFields: List[MatchField] = field(default_factory=list)
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

    def onButtonClick(self, state: Component[FuzzyMatchProperties]):
        _matchFields = state.properties.matchFields
        _matchFields.append(self.AddMatchField())
        return state.bindProperties(dataclasses.replace(state.properties, matchFields=_matchFields))

    def dialog(self) -> Dialog:
        configurations = (
            StackLayout()
            .addElement(TitleElement("Configuration"))
            .addElement(
                SelectBox("Merge/Purge Mode")
                .addOption("Purge mode (All Records Compared)", "PURGE")
                .addOption("Merge (Only Records from a Different Source are Compared)", "MERGE")
                .bindProperty("mode")
            )
            .addElement(
                Condition()
                .ifEqual(
                    PropExpr("component.properties.mode"),
                    StringExpr("MERGE"),
                )
                .then(
                    SchemaColumnsDropdown("Source ID Field")
                    .withSearchEnabled()
                    .bindSchema("component.ports.inputs[0].schema")
                    .bindProperty("sourceIdCol")
                    .showErrorsFor("sourceIdCol")
                )
            )
            .addElement(
                SchemaColumnsDropdown("Record ID Field")
                .bindSchema("component.ports.inputs[0].schema")
                .bindProperty("recordIdCol")
                .showErrorsFor("recordIdCol")
            )
            .addElement(
                NumberBox("Match Threshold percentage",
                          placeholder="80",
                          minValueVar=0,
                          maxValueVar=100,
                          )
                .bindProperty("matchThresholdPercentage"),
            )
            .addElement(
                Checkbox("Include similarity score column").bindProperty(
                    "includeSimilarityScore")
            )
        )

        matchFunction = (SelectBox("Match Function")
                         .addOption("Custom", "custom")
                         .addOption("Exact", "exact")
                         .addOption("Equals", "equals")
                         .addOption("Address", "address")
                         .addOption("Name", "name")
                         .addOption("Phone", "phone")
                         .bindProperty("record.AddMatchField.matchFunction")
                         )

        matchFields = StackLayout(gap=("1rem"), height=("100bh")) \
            .addElement(TitleElement("Transformations")) \
            .addElement(
            OrderedList("Match Fields")
            .bindProperty("matchFields")
            .setEmptyContainerText("Add a match field")
            .addElement(
                ColumnsLayout(("1rem"), alignY=("end"))
                .addColumn(
                    ColumnsLayout("1rem")
                    .addColumn(
                        SchemaColumnsDropdown("Field Name")
                        .bindSchema("component.ports.inputs[0].schema")
                        .bindProperty("record.AddMatchField.columnName")
                        , "0.5fr")
                    .addColumn(
                        matchFunction,
                        "0.5fr"
                    )
                )
                .addColumn(ListItemDelete("delete"), width="content")
            )
        ) \
            .addElement(SimpleButtonLayout("Add Match Field", self.onButtonClick))

        tabs = Tabs() \
            .bindProperty("activeTab") \
            .addTabPane(
            TabPane("Configuration", "configuration").addElement(configurations)
        ).addTabPane(
            TabPane("Match Fields", "match_fields").addElement(matchFields)
        )

        return Dialog("FuzzyMatch") \
            .addElement(
            ColumnsLayout(gap=("1rem"), height=("100%"))
            .addColumn(
                Ports(), "content"
            )
            .addColumn(VerticalDivider(), width="content")
            .addColumn(tabs)
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(FuzzyMatch, self).validate(context, component)

        if len(component.properties.mode) == 0:
            diagnostics.append(
                Diagnostic("component.properties.mode", "Please select Merge/Purge mode",
                           SeverityLevelEnum.Error))

        if component.properties.mode == "PURGE":
            if len(component.properties.recordIdCol) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.recordIdCol", "Please select a Record Id",
                               SeverityLevelEnum.Error))

            if len(component.properties.matchFields) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.matchFields", "Please add a match field",
                               SeverityLevelEnum.Error))

        if component.properties.mode == "MERGE":
            if len(component.properties.sourceIdCol) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.sourceIdCol", "Please select a Source Id",
                               SeverityLevelEnum.Error))

            if len(component.properties.recordIdCol) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.recordIdCol", "Please select a Record Id",
                               SeverityLevelEnum.Error))

            if len(component.properties.matchFields) == 0:
                diagnostics.append(
                    Diagnostic("component.properties.matchFields", "Please add a match field",
                               SeverityLevelEnum.Error))

        # Extract all column names from the schema
        field_names = [field["name"] for field in component.ports.inputs[0].schema["fields"]]

        if len(component.properties.recordIdCol) > 0:
            if component.properties.recordIdCol not in field_names:
                diagnostics.append(
                    Diagnostic("component.properties.recordIdCol", f"Selected recordId column {component.properties.recordIdCol} is not present in input schema.",
                               SeverityLevelEnum.Error))

        if len(component.properties.sourceIdCol) > 0:
            if component.properties.sourceIdCol not in field_names:
                diagnostics.append(
                    Diagnostic("component.properties.sourceIdCol", f"Selected sourceId column {component.properties.sourceIdCol} is not present in input schema.",
                               SeverityLevelEnum.Error))

        # Extract column names from matchFields
        match_field_columns = [field.columnName for field in component.properties.matchFields if field.columnName]
        # Identify missing columns
        missing_match_columns = [col for col in match_field_columns if col not in field_names]

        # Append diagnostic if any are missing
        if missing_match_columns:
            diagnostics.append(
                Diagnostic(
                    "component.properties.matchFields",
                    f"Selected matchField columns {missing_match_columns} are not present in input schema.",
                    SeverityLevelEnum.Error
                )
            )

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        relation_name = self.get_relation_names(newState, context)
        return (replace(newState, properties=replace(newState.properties, relation_name=relation_name)))

    def apply(self, props: FuzzyMatchProperties) -> str:
        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Get the Single Table Name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)

        # Group match fields by their match function.
        grouped_match_fields = defaultdict(list)
        for field in props.matchFields:
            grouped_match_fields[field.matchFunction].append(field.columnName)

        # Convert defaultdict to a regular dict.
        match_fields_map = dict(grouped_match_fields)

        arguments = [
            "'" + table_name + "'",
            "'" + props.mode + "'",
            "'" + props.sourceIdCol + "'",
            "'" + props.recordIdCol + "'",
            str(match_fields_map),
            str(props.matchThresholdPercentage),
            str(props.includeSimilarityScore).lower()
        ]
        params = ",".join([param for param in arguments])
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return FuzzyMatch.FuzzyMatchProperties(
            relation_name=parametersMap.get('relation_name'),
            mode=parametersMap.get('mode'),
            sourceIdCol=parametersMap.get('sourceIdCol'),
            recordIdCol=parametersMap.get('recordIdCol'),
            matchThresholdPercentage=float(parametersMap.get('matchThresholdPercentage')),
            includeSimilarityScore=parametersMap.get('includeSimilarityScore').lower() == 'true'
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("mode", properties.mode),
                MacroParameter("sourceIdCol", properties.sourceIdCol),
                MacroParameter("recordIdCol", properties.recordIdCol),
                MacroParameter("matchThresholdPercentage", str(properties.matchThresholdPercentage)),
                MacroParameter("includeSimilarityScore", str(properties.includeSimilarityScore).lower())
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)
        return (replace(component, properties=replace(component.properties, relation_name=relation_name)))