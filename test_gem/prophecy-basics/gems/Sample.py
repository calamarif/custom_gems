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


class Sample(MacroSpec):
    name: str = "Sample"
    projectName: str = "prophecy_basics"
    category: str = "Prepare"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        # ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class SampleProperties(MacroProperties):
        # properties for the component with default values
        dataColumns: Optional[List[str]] = field(default_factory=list)
        schema: str = ""
        relation_name: List[str] = field(default_factory=list)
        # Current Tab
        sampleLevelSelection: str = "sampleDataset"
        # From Create Samples Side
        randomSeed: int = 1002
        # From Create Samples Side
        currentModeSelection: str = "firstN"
        numberN: int = 80

    def dialog(self) -> Dialog:

        sample = (
            StackLayout(gap=("1rem"), height=("100bh"))
            .addElement(
                StepContainer(gap=("1rem")).addElement(
                    Step().addElement(
                        StackLayout(height="100%")
                        .addElement(
                            SelectBox("Sampling Level")
                            .addOption("Sample from Entire Dataset", "sampleDataset")
                            .addOption("Sample from Within Group", "sampleGroup")
                            .bindProperty("sampleLevelSelection")
                        )
                        .addElement(
                            SelectBox("Sample Type")
                            .addOption(
                                "Random N Rows", "randomN"
                            )  # Returns random N rows.
                            .addOption(
                                "Random N% of rows", "randomNPercent"
                            )  # Returns N percent of rows. This option requires the data to pass through the tool twice: once to calculate the count of rows and again to return the specified percent of rows.
                            .addOption(
                                "First N rows", "firstN"
                            )  # Returns every row in the data from the beginning of the data through row N.
                            .addOption(
                                "Last N rows", "lastN"
                            )  # Starting from the row that is N rows away from the end of the data, returns every row through to the end of the data.
                            .addOption(
                                "Every Nth row", "oneOfN"
                            )  # Returns the first row of every group of N rows.
                            .addOption(
                                "Skip first N rows", "skipN"
                            )  # Returns all rows in the data starting after row N.
                            .addOption(
                                "1 in N chance per row", "oneInN"
                            )  # Randomly determines if each row is included in the sample, independent of the inclusion of any other rows. This method of selection results in N being an approximation.
                            .addOption(
                                "First N% of rows", "nPercent"
                            )  # Returns N percent of rows. This option requires the data to pass through the tool twice: once to calculate the count of rows and again to return the specified percent of rows.
                            .bindProperty("currentModeSelection")
                        )
                    )
                )
            )
            .addElement(
                Condition()
                .ifEqual(
                    PropExpr("component.properties.sampleLevelSelection"),
                    StringExpr("sampleGroup"),
                )
                .then(
                    StepContainer().addElement(
                        Step().addElement(
                            SchemaColumnsDropdown(
                                "Grouping Columns", appearance="minimal"
                            )
                            .withMultipleSelection()
                            .bindSchema("component.ports.inputs[0].schema")
                            .bindProperty("dataColumns")
                            .showErrorsFor("dataColumns")
                        )
                    )
                )
            )
            .addElement(
                StepContainer()
                .addElement(
                    Condition()
                    .ifEqual(
                        PropExpr("component.properties.currentModeSelection"),
                        StringExpr("nPercent"),
                    )
                    .then(
                        Step().addElement(
                            NumberBox(
                                "Sample Value (Percentage of records)", placeholder=80
                            ).bindProperty("numberN")
                        )
                    )
                    .otherwise(
                        Condition()
                        .ifEqual(
                            PropExpr("component.properties.currentModeSelection"),
                            StringExpr("randomNPercent"),
                        )
                        .then(
                            Step().addElement(
                                NumberBox(
                                    "Sample Value (Percentage of records)",
                                    placeholder=80,
                                ).bindProperty("numberN")
                            )
                        )
                        .otherwise(
                            Step().addElement(
                                NumberBox(
                                    "Sample Value (Number of records)", placeholder=100
                                ).bindProperty("numberN")
                            )
                        )
                    )
                )
                .addElement(
                    Condition()
                    .ifEqual(
                        PropExpr("component.properties.currentModeSelection"),
                        StringExpr("randomNPercent"),
                    )
                    .then(
                        Step().addElement(
                            NumberBox(
                                "Random Seed for Sample", placeholder=1001
                            ).bindProperty("randomSeed")
                        )
                    )
                    .otherwise(
                        Condition()
                        .ifEqual(
                            PropExpr("component.properties.currentModeSelection"),
                            StringExpr("randomN"),
                        )
                        .then(
                            Step().addElement(
                                NumberBox(
                                    "Random Seed for Sample", placeholder=1001
                                ).bindProperty("randomSeed")
                            )
                        )
                    )
                )
            )
        )

        # TODO: Conditions -> for validation, headings etc.

        return Dialog("Macro").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(sample)
        )

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

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:

        diagnostics = super(Sample, self).validate(context, component)

        missingDataColumns = []
        schemaFields = json.loads(
            str(component.ports.inputs[0].schema).replace("'", '"')
        )
        fieldsArray = [field["name"].upper() for field in schemaFields["fields"]]

        for col in component.properties.dataColumns:
            if col.upper() not in fieldsArray:
                missingDataColumns.append(col)

        if missingDataColumns:
            diagnostics.append(
                Diagnostic(
                    "properties.dataColumns",
                    f"Data columns {missingDataColumns} are not present in input schema.",
                    SeverityLevelEnum.Error,
                )
            )
        # Validate the component's state
        # 1. For 2 First N% of rows should be <= 100%
        # 2. For 1, Estimation and Validation estimates should be <= 1
        # 3. For 2, for all else N < total num rows
        return diagnostics

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

    def apply(self, props: SampleProperties) -> str:
        # generate the actual macro call given the component's state
        table_name: str = ",".join(str(rel) for rel in props.relation_name)
        # Get existing column names
        resolved_macro_name = f"{self.projectName}.{self.name}"
        if props.sampleLevelSelection == "sampleDataset":
            dataColumns = []
        else:
            dataColumns = props.dataColumns
        non_empty_param = ",".join(
            [
                "'" + table_name + "'",
                str(dataColumns),
                str(props.randomSeed),
                f"'{props.currentModeSelection}'",
                str(props.numberN),
                ]
        )
        print(f"[DEBUG_DEBUG] APPLY METHOD PARAMS = { non_empty_param }")

        # Sample(relation_name, groupCols, randomSeed, currentModeSelection, numberN)
        return f"{{{{ {resolved_macro_name}({non_empty_param}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        props = Sample.SampleProperties(
            relation_name=parametersMap.get("relation_name"),
            dataColumns=json.loads(parametersMap.get("dataColumns").replace("'", '"')),
            randomSeed=int(parametersMap.get("randomSeed")),
            currentModeSelection=parametersMap.get("currentModeSelection"),
            numberN=int(parametersMap.get("numberN")),
        )
        return props

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", str(properties.relation_name)),
                MacroParameter("dataColumns", json.dumps(properties.dataColumns)),
                MacroParameter("randomSeed", str(properties.randomSeed)),
                MacroParameter("currentModeSelection", properties.currentModeSelection),
                MacroParameter("numberN", str(properties.numberN)),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)
        return replace(
            component,
            properties=replace(component.properties, relation_name=relation_name),
        )
