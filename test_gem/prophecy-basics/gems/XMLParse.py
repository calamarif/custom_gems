import json
import dataclasses

from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import SparkSession
from pyspark.sql.functions import *


class XMLParse(MacroSpec):
    name: str = "XMLParse"
    projectName: str = "prophecy_basics"
    category: str = "Parse"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        # ProviderTypeEnum.ProphecyManaged,
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class XMLParseProperties(MacroProperties):
        # properties for the component with default values
        columnName: str = ""
        relation_name: List[str] = field(default_factory=list)
        parsingMethod: str = "parseFromSampleRecord"
        sampleRecord: Optional[str] = None
        sampleSchema: Optional[str] = None

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
        methodRadioGroup = (
            RadioGroup("Parsing method")
            .addOption(
                "Parse from sample record",
                "parseFromSampleRecord",
                description=("Provide a sample record to parse the schema from"),
            )
            .addOption(
                "Parse from schema",
                "parseFromSchema",
                description="Provide sample schema in SQL struct format to parse the data with",
            )
            .setOptionType("button")
            .setVariant("medium")
            .setButtonStyle("solid")
            .bindProperty("parsingMethod")
        )

        sampleRecordTextXML = (
            TextArea("Sample XML record to parse schema from", 20)
            .bindProperty("sampleRecord")
            .bindPlaceholder(
                """<root>
  <person>
    <id>1</id>
    <name>
      <first>John</first>
      <last>Doe</last>
    </name>
    <address>
      <street>Main St</street>
      <city>Springfield</city>
      <zip>12345</zip>
    </address>
  </person>
</root>"""
            )
        )
        return Dialog("ColumnParser").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(TitleElement("Select Column to Parse"))
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%").addElement(
                                SchemaColumnsDropdown("", appearance="minimal")
                                .bindSchema("component.ports.inputs[0].schema")
                                .bindProperty("columnName")
                                .showErrorsFor("columnName")
                            )
                        )
                    )
                )
                .addElement(methodRadioGroup)
                .addElement(
                    Condition()
                    .ifEqual(
                        PropExpr("component.properties.parsingMethod"),
                        StringExpr("parseFromSampleRecord"),
                    )
                    .then(sampleRecordTextXML)
                )
                .addElement(
                    Condition()
                    .ifEqual(
                        PropExpr("component.properties.parsingMethod"),
                        StringExpr("parseFromSchema"),
                    )
                    .then(
                        TextArea("Schema struct to parse the column", 20)
                        .bindProperty("sampleSchema")
                        .bindPlaceholder(
                            """STRUCT<
  root: STRUCT<
    person: STRUCT<
      id: INT,
      name: STRUCT<
        first: STRING,
        last: STRING
      >,
      address: STRUCT<
        street: STRING,
        city: STRING,
        zip: INT
      >
    >
  >
>"""
                        )
                    )
                ),
                "1fr",
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(XMLParse, self).validate(context, component)

        if (
            component.properties.columnName is None
            or component.properties.columnName == ""
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.columnName",
                    "Please select a column for the operation",
                    SeverityLevelEnum.Error,
                )
            )
        else:
            # Extract all column names from the schema
            field_names = [
                field["name"] for field in component.ports.inputs[0].schema["fields"]
            ]
            if component.properties.columnName not in field_names:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.columnName",
                        f"Selected column {component.properties.columnName} is not present in input schema.",
                        SeverityLevelEnum.Error,
                    )
                )

        if (
            component.properties.parsingMethod is None
            or component.properties.parsingMethod == ""
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.parsingMethod",
                    "Please select a parsing method",
                    SeverityLevelEnum.Error,
                )
            )
        else:
            if component.properties.parsingMethod == "parseFromSchema":
                if (
                    component.properties.sampleSchema is None
                    or component.properties.sampleSchema == ""
                ):
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.sampleSchema",
                            "Please provide a valid SQL struct schema",
                            SeverityLevelEnum.Error,
                        )
                    )
            elif component.properties.parsingMethod == "parseFromSampleRecord":
                if (
                    component.properties.sampleRecord is None
                    or component.properties.sampleRecord == ""
                ):
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.sampleRecord",
                            "Please provide a valid sample xml record",
                            SeverityLevelEnum.Error,
                        )
                    )
            else:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.parsingMethod",
                        "Invalid Parsing method selected",
                        SeverityLevelEnum.Error,
                    )
                )

        return diagnostics

    def onChange(
        self, context: SqlContext, oldState: Component, newState: Component
    ) -> Component:
        # Handle changes in the newState's state and return the new state
        relation_name = self.get_relation_names(newState, context)
        newProperties = dataclasses.replace(
            newState.properties,
            relation_name=relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: XMLParseProperties) -> str:
        # You can now access self.relation_name here
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Get the Single Table Name
        sampleRecord: str = props.sampleRecord if props.sampleRecord is not None else ""
        sampleSchema: str = props.sampleSchema if props.sampleSchema is not None else ""

        arguments = [
            str(props.relation_name),
            "'" + props.columnName + "'",
            "'" + props.parsingMethod + "'",
            "'" + sampleRecord + "'",
            "'" + sampleSchema + "'",
        ]
        params = ",".join([param for param in arguments])
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        print(f"The name of the parametersMap is {parametersMap}")
        return XMLParse.XMLParseProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            columnName=parametersMap.get('columnName').lstrip("'").rstrip("'"),
            parsingMethod=parametersMap.get('parsingMethod').lstrip("'").rstrip("'"),
            sampleRecord=parametersMap.get("sampleRecord").lstrip("'").rstrip("'"),
            sampleSchema=parametersMap.get("sampleSchema").lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("columnName", properties.columnName),
                MacroParameter("parsingMethod", properties.parsingMethod),
                MacroParameter("sampleRecord", properties.sampleRecord),
                MacroParameter("sampleSchema", properties.sampleSchema),
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
        if self.props.parsingMethod == "parseFromSchema":
            if not self.props.sampleSchema or self.props.sampleSchema == "":
                res = in0
            else:
                schema_str = self.props.sampleSchema.replace("\n", " ").strip()
                quoted_col = f"`{self.props.columnName}`"
                alias_col = f"`{self.props.columnName}_parsed`"
                res = in0.selectExpr(
                    "*",
                    f"from_xml({quoted_col}, '{schema_str}') as {alias_col}"
                )

        elif self.props.parsingMethod == "parseFromSampleRecord":
            if not self.props.sampleRecord or self.props.sampleRecord == "":
                res = in0
            else:
                import re
                # Replace newlines and normalize whitespace
                sample_str = self.props.sampleRecord.replace("\n", " ").strip()
                sample_str = re.sub(r'\s+', ' ', sample_str)
                # Escape backslashes first, then double quotes
                sample_str_escaped = sample_str.replace("\\", "\\\\").replace('"', '\\"')
                
                quoted_col = f"`{self.props.columnName}`"
                alias_col = f"`{self.props.columnName}_parsed`"
                res = in0.selectExpr(
                    "*",
                    f"from_xml({quoted_col}, schema_of_xml(\"{sample_str_escaped}\")) as {alias_col}"
                )
        else:
            res = in0

        return res
