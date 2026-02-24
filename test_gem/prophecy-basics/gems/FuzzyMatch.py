import dataclasses
import json
from collections import defaultdict

from prophecy.cb.sql.Component import *
from prophecy.cb.server.base.ComponentBuilderBase import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
import json

from pyspark.sql import *
from pyspark.sql.functions import *


class MatchField(ABC):
    pass


class FuzzyMatch(MacroSpec):
    name: str = "FuzzyMatch"
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
        return state.bindProperties(
            dataclasses.replace(state.properties, matchFields=_matchFields)
        )

    def dialog(self) -> Dialog:
        configurations = (
            StackLayout()
            .addElement(TitleElement("Configuration"))
            .addElement(
                SelectBox("Merge/Purge Mode")
                .addOption("Purge mode (All Records Compared)", "PURGE")
                .addOption(
                    "Merge (Only Records from a Different Source are Compared)", "MERGE"
                )
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
                NumberBox(
                    "Match Threshold percentage",
                    placeholder="80",
                    minValueVar=0,
                    maxValueVar=100,
                ).bindProperty("matchThresholdPercentage"),
            )
            .addElement(
                Checkbox("Include similarity score column").bindProperty(
                    "includeSimilarityScore"
                )
            )
        )

        matchFunction = (
            SelectBox("Match Function")
            .addOption("Custom", "custom")
            .addOption("Exact", "exact")
            .addOption("Equals", "equals")
            .addOption("Address", "address")
            .addOption("Name", "name")
            .addOption("Phone", "phone")
            .bindProperty("record.AddMatchField.matchFunction")
        )

        matchFields = (
            StackLayout(gap=("1rem"), height=("100%"))
            .addElement(TitleElement("Transformations"))
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
                            .bindProperty("record.AddMatchField.columnName"),
                            "0.5fr",
                        )
                        .addColumn(matchFunction, "0.5fr")
                    )
                    .addColumn(ListItemDelete("delete"), width="content")
                )
            )
            .addElement(SimpleButtonLayout("Add Match Field", self.onButtonClick))
        )

        tabs = (
            Tabs()
            .bindProperty("activeTab")
            .addTabPane(
                TabPane("Configuration", "configuration").addElement(configurations)
            )
            .addTabPane(TabPane("Match Fields", "match_fields").addElement(matchFields))
        )

        return Dialog("FuzzyMatch").addElement(
            ColumnsLayout(gap=("1rem"), height=("100%"))
            .addColumn(Ports(), "content")
            .addColumn(VerticalDivider(), width="content")
            .addColumn(tabs)
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(FuzzyMatch, self).validate(context, component)

        if len(component.properties.mode) == 0:
            diagnostics.append(
                Diagnostic(
                    "component.properties.mode",
                    "Please select Merge/Purge mode",
                    SeverityLevelEnum.Error,
                )
            )

        if component.properties.mode == "PURGE":
            if len(component.properties.recordIdCol) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.recordIdCol",
                        "Please select a Record Id",
                        SeverityLevelEnum.Error,
                    )
                )

            if len(component.properties.matchFields) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.matchFields",
                        "Please add a match field",
                        SeverityLevelEnum.Error,
                    )
                )

        if component.properties.mode == "MERGE":
            if len(component.properties.sourceIdCol) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.sourceIdCol",
                        "Please select a Source Id",
                        SeverityLevelEnum.Error,
                    )
                )

            if len(component.properties.recordIdCol) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.recordIdCol",
                        "Please select a Record Id",
                        SeverityLevelEnum.Error,
                    )
                )

            if len(component.properties.matchFields) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.matchFields",
                        "Please add a match field",
                        SeverityLevelEnum.Error,
                    )
                )

        # Extract all column names from the schema
        field_names = [
            field["name"] for field in component.ports.inputs[0].schema["fields"]
        ]

        if len(component.properties.recordIdCol) > 0:
            if component.properties.recordIdCol not in field_names:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.recordIdCol",
                        f"Selected recordId column {component.properties.recordIdCol} are not present in input schema.",
                        SeverityLevelEnum.Error,
                    )
                )

        if len(component.properties.sourceIdCol) > 0:
            if component.properties.sourceIdCol not in field_names:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.sourceIdCol",
                        f"Selected sourceId column {component.properties.sourceIdCol} are not present in input schema.",
                        SeverityLevelEnum.Error,
                    )
                )

        # Extract column names from matchFields
        match_field_columns = [
            field.columnName
            for field in component.properties.matchFields
            if field.columnName
        ]
        # Identify missing columns
        missing_match_columns = [
            col for col in match_field_columns if col not in field_names
        ]

        # Append diagnostic if any are missing
        if missing_match_columns:
            diagnostics.append(
                Diagnostic(
                    "component.properties.matchFields",
                    f"Selected matchField columns {missing_match_columns} are not present in input schema.",
                    SeverityLevelEnum.Error,
                )
            )

        return diagnostics

    def onChange(
        self, context: SqlContext, oldState: Component, newState: Component
    ) -> Component:
        # Handle changes in the component's state and return the new state
        relation_name = self.get_relation_names(newState, context)
        newProperties = dataclasses.replace(
            newState.properties,
            relation_name=relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: FuzzyMatchProperties) -> str:
        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        match_fields_list = [
            {"columnName": field.columnName, "matchFunction": field.matchFunction}
            for field in props.matchFields
        ]

        arguments = [
            str(props.relation_name),
            "'" + props.mode + "'",
            "'" + props.sourceIdCol + "'",
            "'" + props.recordIdCol + "'",
            str(match_fields_list),
            str(props.matchThresholdPercentage),
            str(props.includeSimilarityScore).lower(),
        ]
        params = ",".join([param for param in arguments])
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        matchFields = []
        matchFieldsJson = json.loads(parametersMap.get("matchFields").replace("'", '"'))
        for fld in matchFieldsJson:
            matchFields.append(
                self.AddMatchField(
                    columnName=fld.get("columnName"),
                    matchFunction=fld.get("matchFunction")
                )
            )
        return FuzzyMatch.FuzzyMatchProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            mode=parametersMap.get('mode').lstrip("'").rstrip("'"),
            sourceIdCol=parametersMap.get('sourceIdCol').lstrip("'").rstrip("'"),
            recordIdCol=parametersMap.get('recordIdCol').lstrip("'").rstrip("'"),
            matchThresholdPercentage=float(
                parametersMap.get("matchThresholdPercentage")
            ),
            includeSimilarityScore=parametersMap.get("includeSimilarityScore").lower()
            == "true",
            matchFields=matchFields,
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        matchFieldsJsonList = json.dumps([{
            "columnName": fld.columnName,
            "matchFunction": fld.matchFunction
        }
            for fld in properties.matchFields
        ])
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("mode", properties.mode),
                MacroParameter("sourceIdCol", properties.sourceIdCol),
                MacroParameter("recordIdCol", properties.recordIdCol),
                MacroParameter(
                    "matchThresholdPercentage", str(properties.matchThresholdPercentage)
                ),
                MacroParameter(
                    "includeSimilarityScore",
                    str(properties.includeSimilarityScore).lower(),
                ),
                MacroParameter(
                    "matchFields", matchFieldsJsonList
                ),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)
        newProperties = dataclasses.replace(
            component.properties,
            relation_name=relation_name
        )
        return component.bindProperties(newProperties)

    def applyPython(self, spark: SparkSession, in0: DataFrame) -> DataFrame:
        if not (self.props.matchFields and (self.props.mode == "PURGE" or self.props.mode == "MERGE")):
            return in0

        selects: SubstituteDisabled = []
        for field in self.props.matchFields:
            key = field.matchFunction
            col_name = field.columnName

            if key in ("custom", "name", "address"):
                column_value = upper(regexp_replace(col(col_name).cast("string"), r"[^\w\s]", ""))
            else:
                column_value = col(col_name).cast("string")

            if key == "custom":
                func_name = "LEVENSHTEIN"
            elif key == "name":
                func_name = "LEVENSHTEIN"
            elif key == "phone":
                func_name = "EQUALS"
            elif key == "address":
                func_name = "LEVENSHTEIN"
            elif key == "exact":
                func_name = "EXACT"
            elif key == "equals":
                func_name = "EQUALS"
            else:
                func_name = "LEVENSHTEIN"

            base_cols = [
                col(self.props.recordIdCol).cast("string").alias("record_id"),
                upper(lit(col_name)).alias("column_name"),
                column_value.alias("column_value"),
                lit(func_name).alias("function_name")
            ]

            if self.props.mode == "MERGE":
                base_cols.insert(1, col(self.props.sourceIdCol).cast("string").alias("source_id"))

            selects.append(in0.select(*base_cols))

        match_function: SubstituteDisabled = selects[0]
        for x in selects[1:]:
            match_function = match_function.unionByName(x, allowMissingColumns=True)

        df0: SubstituteDisabled = match_function.alias("df0")
        df1: SubstituteDisabled = match_function.alias("df1")

        join_cond: SubstituteDisabled = (
                (col("df0.function_name") == col("df1.function_name")) &
                (col("df0.column_name") == col("df1.column_name")) &
                (col("df0.record_id") != col("df1.record_id"))
        )

        if self.props.mode == "MERGE":
            join_cond = join_cond & (col("df0.source_id") != col("df1.source_id"))

        cross_joined: SubstituteDisabled = df0.join(df1, join_cond).select(
            col("df0.record_id").alias("record_id1"),
            col("df1.record_id").alias("record_id2"),
            *( [col("df0.source_id").alias("source_id1"), col("df1.source_id").alias("source_id2")] if self.props.mode == "MERGE" else [] ),
            col("df0.column_value").alias("column_value_1"),
            col("df1.column_value").alias("column_value_2"),
            col("df0.column_name").alias("column_name"),
            col("df0.function_name").alias("function_name")
        )

        similarity: SubstituteDisabled = when(col("function_name") == "LEVENSHTEIN",
                                              (1 - (levenshtein(col("column_value_1"), col("column_value_2")) /
                                                    greatest(length(col("column_value_1")), length(col("column_value_2"))))) * 100
                                              ).when(
            (col("function_name") == "EXACT") &
            (col("column_value_1") == reverse(col("column_value_2"))) &
            (col("column_value_2") == reverse(col("column_value_1"))),
            100.0
        ).when(
            (col("function_name") == "EXACT") &
            ((col("column_value_1") != reverse(col("column_value_2"))) |
             (col("column_value_2") == reverse(col("column_value_1")))),
            0.0
        ).when(
            (col("function_name") == "EQUALS") & (col("column_value_1") == col("column_value_2")),
            100.0
        ).when(
            (col("function_name") == "EQUALS") & (col("column_value_1") != col("column_value_2")),
            0.0
        ).otherwise(
            (1 - (levenshtein(col("column_value_1"), col("column_value_2")) /
                  greatest(length(col("column_value_1")), length(col("column_value_2"))))) * 100
        )

        imposed = cross_joined.withColumn("similarity_score", similarity)

        replaced : SubstituteDisabled = imposed.select(
            when(col("record_id1").cast("long") >= col("record_id2").cast("long"), col("record_id1")).otherwise(col("record_id2")).alias("record_id1"),
            when(col("record_id1").cast("long") >= col("record_id2").cast("long"), col("record_id2")).otherwise(col("record_id1")).alias("record_id2"),
            col("column_name"),
            col("function_name"),
            col("similarity_score")
        )

        final_output = replaced.groupBy("record_id1", "record_id2").agg(round(avg("similarity_score"), 2).alias("similarity_score"))

        threshold: SubstituteDisabled = float(self.props.matchThresholdPercentage or 0)

        if self.props.includeSimilarityScore:
            return final_output.filter(col("similarity_score") >= threshold).select("record_id1", "record_id2", "similarity_score")
        else:
            return final_output.filter(col("similarity_score") >= threshold).select("record_id1", "record_id2")
