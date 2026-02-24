import json
import re
import dataclasses

from prophecy.cb.server.base.ComponentBuilderBase import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import SparkSession
from pyspark.sql.functions import *


class TextToColumns(MacroSpec):
    name: str = "TextToColumns"
    projectName: str = "prophecy_basics"
    category: str = "Parse"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

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
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout()
                .addElement(
                    StackLayout(height="100%")
                    .addElement(TitleElement("Select Column to Split"))
                    .addElement(
                        StepContainer().addElement(
                            Step().addElement(
                                StackLayout(height="100%").addElement(
                                    SchemaColumnsDropdown("", appearance="minimal")
                                    .bindSchema("component.ports.inputs[0].schema")
                                    .bindProperty("columnNames")
                                    .showErrorsFor("columnNames")
                                )
                            )
                        )
                    )
                    .addElement(
                        StepContainer().addElement(
                            Step().addElement(
                                StackLayout(height="100%")
                                .addElement(TitleElement("Delimiter"))
                                .addElement(
                                    TextBox("")
                                    .bindPlaceholder("delimiter")
                                    .bindProperty("delimiter")
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
                                        ],
                                    )
                                )
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(
                                RadioGroup("Select Split Strategy")
                                .addOption("Split to columns", "splitColumns")
                                .addOption("Split to rows", "splitRows")
                                .bindProperty("split_strategy")
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr("component.properties.split_strategy"),
                                    StringExpr("splitColumns"),
                                )
                                .then(
                                    StackLayout(height="100%")
                                    .addElement(
                                        ColumnsLayout(gap="1rem", height="100%")
                                        .addColumn(
                                            NumberBox(
                                                "Number of columns",
                                                placeholder=1,
                                                requiredMin=1,
                                            ).bindProperty("noOfColumns")
                                        )
                                        .addColumn()
                                        .addColumn()
                                        .addColumn()
                                        .addColumn()
                                    )
                                    .addElement(
                                        ColumnsLayout(gap="1rem", height="100%")
                                        .addColumn(
                                            SelectBox(
                                                titleVar="Extra Characters",
                                                defaultValue="Leave extra in last column",
                                            )
                                            .addOption(
                                                "Leave extra in last column",
                                                "leaveExtraCharLastCol",
                                            )
                                            .bindProperty("leaveExtraCharLastCol")
                                        )
                                        .addColumn(
                                            TextBox("Column Prefix")
                                            .bindPlaceholder(
                                                "Enter Generated Column Prefix"
                                            )
                                            .bindProperty("splitColumnPrefix")
                                        )
                                        .addColumn(
                                            TextBox("Column Suffix")
                                            .bindPlaceholder(
                                                "Enter Generated Column Suffix"
                                            )
                                            .bindProperty("splitColumnSuffix")
                                        )
                                    )
                                )
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr("component.properties.split_strategy"),
                                    StringExpr("splitRows"),
                                )
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
                Diagnostic(
                    "properties.columnNames",
                    "column name can not be empty",
                    SeverityLevelEnum.Error,
                )
            )
        if len(component.properties.delimiter) == 0:
            diagnostics.append(
                Diagnostic(
                    "properties.delimiter",
                    "delimiter can not be empty",
                    SeverityLevelEnum.Error,
                )
            )
        if len(component.properties.split_strategy) == 0:
            diagnostics.append(
                Diagnostic(
                    "properties.split_strategy",
                    "split strategy can not be empty",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.split_strategy == "splitColumns":
            if component.properties.noOfColumns < 1:
                diagnostics.append(
                    Diagnostic(
                        "properties.noOfColumns",
                        "No of columns should be more than or equals to 1",
                        SeverityLevelEnum.Error,
                    )
                )
            if len(component.properties.splitColumnPrefix) == 0:
                diagnostics.append(
                    Diagnostic(
                        "properties.splitColumnPrefix",
                        "Please provide a prefix for generated column",
                        SeverityLevelEnum.Error,
                    )
                )
            if len(component.properties.splitColumnSuffix) == 0:
                diagnostics.append(
                    Diagnostic(
                        "properties.splitColumnSuffix",
                        "Please provide a suffix for generated column",
                        SeverityLevelEnum.Error,
                    )
                )
        if component.properties.split_strategy == "splitRows":
            if len(component.properties.splitRowsColumnName) == 0:
                diagnostics.append(
                    Diagnostic(
                        "properties.splitRowsColumnName",
                        "Please provide a generated column name",
                        SeverityLevelEnum.Error,
                    )
                )

        # Extract all column names from the schema
        field_names = [
            field["name"] for field in component.ports.inputs[0].schema["fields"]
        ]

        if len(component.properties.columnNames) > 0:
            if component.properties.columnNames not in field_names:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.columnNames",
                        f"Selected column {component.properties.columnNames} is not present in input schema.",
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

    def apply(self, props: TextToColumnsProperties) -> str:
        # You can now access self.relation_name here
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Handle delimiter with special characters
        escaped_delimiter = re.escape(props.delimiter).replace("\\", "\\\\\\")

        arguments = [
            str(props.relation_name),
            "'" + props.columnNames + "'",
            '"' + escaped_delimiter + '"',
            "'" + props.split_strategy + "'",
            str(props.noOfColumns),
            "'" + props.leaveExtraCharLastCol + "'",
            "'" + props.splitColumnPrefix + "'",
            "'" + props.splitColumnSuffix + "'",
            "'" + props.splitRowsColumnName + "'",
        ]
        params = ",".join([param for param in arguments])
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        print(f"The name of the parametersMap is {parametersMap}")
        return TextToColumns.TextToColumnsProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            columnNames=parametersMap.get('columnNames').lstrip("'").rstrip("'"),
            delimiter=parametersMap.get('delimiter').lstrip('"').rstrip('"'),
            split_strategy=parametersMap.get('split_strategy').lstrip("'").rstrip("'"),
            noOfColumns=int(parametersMap.get("noOfColumns")),
            leaveExtraCharLastCol=parametersMap.get('leaveExtraCharLastCol').lstrip("'").rstrip("'"),
            splitColumnPrefix=parametersMap.get('splitColumnPrefix').lstrip("'").rstrip("'"),
            splitColumnSuffix=parametersMap.get('splitColumnSuffix').lstrip("'").rstrip("'"),
            splitRowsColumnName=parametersMap.get('splitRowsColumnName').lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("columnNames", properties.columnNames),
                MacroParameter("delimiter", properties.delimiter),
                MacroParameter("split_strategy", properties.split_strategy),
                MacroParameter("noOfColumns", str(properties.noOfColumns)),
                MacroParameter(
                    "leaveExtraCharLastCol", properties.leaveExtraCharLastCol
                ),
                MacroParameter("splitColumnPrefix", properties.splitColumnPrefix),
                MacroParameter("splitColumnSuffix", properties.splitColumnSuffix),
                MacroParameter("splitRowsColumnName", properties.splitRowsColumnName),
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
        col_name = self.props.columnNames
        col_expr = col(col_name)
        delimiter = self.props.delimiter.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r")
        original_delimiter = delimiter
        import re
        special_regex_chars = r'\.^$*+?{}[]|()'
        if delimiter in ["\t", "\n", "\r"]:
            split_delimiter = delimiter
        else:
            split_delimiter: SubstituteDisabled = re.escape(delimiter) if any(c in special_regex_chars for c in delimiter) else delimiter

        placeholder = "%%DELIM%%"
        tmp_arr_col = "__split_arr_tmp__"
        tmp_size_col = "__split_arr_size_tmp__"

        if self.props.split_strategy == "splitColumns":
            replaced_col = regexp_replace(col_expr, split_delimiter, placeholder)
            split_array_expr = split(replaced_col, placeholder)
            result_df = in0.withColumn(tmp_arr_col, split_array_expr).withColumn(tmp_size_col, size(col(tmp_arr_col)))

            for i in range(1, self.props.noOfColumns):
                token_col = when(
                    col(tmp_size_col) > i - 1,
                    trim(regexp_replace(col(tmp_arr_col)[i - 1], r'^"|"$', ''))
                ).otherwise(None)
                output_col = f"{self.props.splitColumnPrefix}_{i}_{self.props.splitColumnSuffix}"
                result_df = result_df.withColumn(output_col, token_col)

            last_col_name = f"{self.props.splitColumnPrefix}_{self.props.noOfColumns}_{self.props.splitColumnSuffix}"
            if self.props.leaveExtraCharLastCol == "Leave extra in last column":
                remaining = slice(col(tmp_arr_col), self.props.noOfColumns, col(tmp_size_col))
                last_col = when(
                    col(tmp_size_col) >= self.props.noOfColumns,
                    array_join(remaining, original_delimiter)
                ).otherwise(None)
            else:
                last_col = when(
                    col(tmp_size_col) > self.props.noOfColumns - 1,
                    trim(regexp_replace(col(tmp_arr_col)[self.props.noOfColumns - 1], r'^"|"$', ''))
                ).otherwise(None)

            return result_df.withColumn(last_col_name, last_col).drop(tmp_arr_col, tmp_size_col)

        elif self.props.split_strategy == "splitRows":
            safe_col = when(col_expr.isNull(), lit("")).otherwise(col_expr)
            replaced_col = regexp_replace(safe_col, split_delimiter, placeholder)
            split_array_expr = split(replaced_col, placeholder)
            result_df = in0.withColumn(tmp_arr_col, split_array_expr).withColumn(tmp_size_col, size(col(tmp_arr_col)))

            result_df = result_df.select(
                [c for c in in0.columns if c != col_name] + [explode(col(tmp_arr_col)).alias("col_temp")])
            result_df = result_df.filter((col("col_temp") != "") & col("col_temp").isNotNull())

            cleaned = trim(
                regexp_replace(
                    regexp_replace(col("col_temp"), r'[{}_]', ' '),
                    r'\s+', ' '
                )
            )

            result_df = result_df.withColumn(self.props.splitRowsColumnName, cleaned)
            return result_df.drop("col_temp", tmp_arr_col, tmp_size_col)

        else:
            return in0
