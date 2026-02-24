import dataclasses
import json

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import SparkSession, Window, DataFrame
from pyspark.sql.functions import row_number, count, lit, expr


@dataclass(frozen=True)
class ColumnExpr:
    expression: str
    format: str


@dataclass(frozen=True)
class OrderByRule:
    expression: ColumnExpr
    sortType: str = "asc"


class FindDuplicates(MacroSpec):
    name: str = "FindDuplicates"
    projectName: str = "prophecy_basics"
    category: str = "Prepare"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class FindDuplicatesProperties(MacroProperties):
        # properties for the component with default values
        relation_name: List[str] = field(default_factory=list)
        schema: str = ""
        generationMethod: str = "allCols"
        groupByColumnNames: List[str] = field(default_factory=list)
        orderByColumns: List[OrderByRule] = field(default_factory=list)
        column_group_rownum_condition: str = ""
        grouped_count_rownum: str = ""
        lower_limit: str = ""
        upper_limit: str = ""
        output_type: str = "unique"

    def dialog(self) -> Dialog:

        order_by_table = BasicTable(
            "OrderByTable",
            height="200px",
            columns=[
                Column(  # 1st column – expression editor
                    "Order By Columns",
                    "expression.expression",
                    ExpressionBox(ignoreTitle=True, language="sql")
                    .bindPlaceholders()
                    .withSchemaSuggestions()
                    .bindLanguage("${record.expression.format}"),
                ),
                Column(  # 2nd column – ASC / DESC etc.
                    "Sort strategy",
                    "sortType",
                    SelectBox("")
                    .addOption("ascending nulls first", "asc")
                    .addOption("ascending nulls last", "asc_nulls_last")
                    .addOption("descending nulls first", "desc_nulls_first")
                    .addOption("descending nulls last", "desc"),
                    width="25%",
                ),
            ],
        )

        generationMethod = StepContainer().addElement(
            Step().addElement(
                StackLayout(height="100%").addElement(
                    SelectBox("Unique rows generation scope")
                    .addOption("Uniqueness across all columns", "allCols")
                    .addOption("Uniqueness across selected columns", "selectedCols")
                    .bindProperty("generationMethod")
                )
            )
        )

        between_condition = Condition().ifEqual(
            PropExpr("component.properties.column_group_rownum_condition"),
            StringExpr("between"),
        )

        selectBox = (
            RadioGroup("Output records selection strategy ")
            .addOption(
                "Unique",
                "unique",
                description=(
                    "Returns the unique records from the dataset based on the selected columns combination"
                ),
            )
            .addOption(
                "Duplicate",
                "duplicate",
                description="Returns the duplicate records from the dataset based on the selected columns combination",
            )
            .addOption(
                "Custom group count",
                "custom_group_count",
                description="Returns the records with grouped column count as per below selected options",
            )
            .addOption(
                "Custom row number",
                "custom_row_number",
                description="Filter records by custom row number condition",
            )
            .setOptionType("button")
            .setVariant("medium")
            .setButtonStyle("solid")
            .bindProperty("output_type")
        )

        return Dialog("FindDuplicates").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(generationMethod)
                .addElement(
                    Condition()
                    .ifEqual(
                        PropExpr("component.properties.generationMethod"),
                        StringExpr("selectedCols"),
                    )
                    .then(
                        StepContainer().addElement(
                            Step().addElement(
                                StackLayout(height="100%")
                                .addElement(
                                    TitleElement("Configure Grouping and Sorting")
                                )
                                .addElement(TitleElement("Group By Columns"))
                                .addElement(
                                    SchemaColumnsDropdown("")
                                    .withMultipleSelection()
                                    .bindSchema("component.ports.inputs[0].schema")
                                    .bindProperty("groupByColumnNames")
                                )
                                .addElement(
                                    TitleElement("Order rows within each group")
                                )
                                .addElement(
                                    order_by_table.bindProperty("orderByColumns")
                                )
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer(gap="1rem").addElement(
                        Step().addElement(
                            StackLayout(height="100%", gap="1rem")
                            .addElement(selectBox)
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr("component.properties.output_type"),
                                    StringExpr("custom_group_count"),
                                )
                                .then(
                                    StackLayout(height="100%", gap="1rem")
                                    .addElement(
                                        TitleElement(
                                            "Select options for grouped count records"
                                        )
                                    )
                                    .addElement(
                                        StackLayout(height="100%", gap="1rem")
                                        .addElement(
                                            SelectBox(
                                                "Select the Filter type for column group count"
                                            )
                                            .bindProperty(
                                                "column_group_rownum_condition"
                                            )
                                            .withStyle({"width": "100%"})
                                            .withDefault("")
                                            .addOption(
                                                "Group count equal to", "equal_to"
                                            )
                                            .addOption(
                                                "Group count less than", "less_than"
                                            )
                                            .addOption(
                                                "Group count greater than",
                                                "greater_than",
                                            )
                                            .addOption(
                                                "Group count not equal to",
                                                "not_equal_to",
                                            )
                                            .addOption("Group count between", "between")
                                        )
                                        .addElement(
                                            Condition()
                                            .ifEqual(
                                                PropExpr(
                                                    "component.properties.column_group_rownum_condition"
                                                ),
                                                StringExpr("between"),
                                            )
                                            .then(
                                                TextBox("Lower limit (inclusive)")
                                                .bindProperty("lower_limit")
                                                .bindPlaceholder("")
                                            )
                                            .otherwise(
                                                TextBox("Grouped count")
                                                .bindProperty("grouped_count_rownum")
                                                .bindPlaceholder("")
                                            )
                                        )
                                        .addElement(
                                            between_condition.then(
                                                TextBox("Upper limit (inclusive)")
                                                .bindProperty("upper_limit")
                                                .bindPlaceholder("")
                                            )
                                        )
                                    )
                                )
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr("component.properties.output_type"),
                                    StringExpr("custom_row_number"),
                                )
                                .then(
                                    StackLayout(height="100%", gap="1rem")
                                    .addElement(
                                        TitleElement(
                                            "Select options for custom row number records"
                                        )
                                    )
                                    .addElement(
                                        StackLayout(height="100%", gap="1rem")
                                        .addElement(
                                            SelectBox(
                                                "Select the Filter type for custom row number records"
                                            )
                                            .bindProperty(
                                                "column_group_rownum_condition"
                                            )
                                            .withStyle({"width": "100%"})
                                            .withDefault("")
                                            .addOption(
                                                "Row number equal to", "equal_to"
                                            )
                                            .addOption(
                                                "Row number less than", "less_than"
                                            )
                                            .addOption(
                                                "Row number greater than",
                                                "greater_than",
                                            )
                                            .addOption(
                                                "Row number not equal to",
                                                "not_equal_to",
                                            )
                                            .addOption("Row number between", "between")
                                        )
                                        .addElement(
                                            Condition()
                                            .ifEqual(
                                                PropExpr(
                                                    "component.properties.column_group_rownum_condition"
                                                ),
                                                StringExpr("between"),
                                            )
                                            .then(
                                                TextBox("Lower limit (inclusive)")
                                                .bindProperty("lower_limit")
                                                .bindPlaceholder("")
                                            )
                                            .otherwise(
                                                TextBox("Row number")
                                                .bindProperty("grouped_count_rownum")
                                                .bindPlaceholder("")
                                            )
                                        )
                                        .addElement(
                                            between_condition.then(
                                                TextBox("Upper limit (inclusive)")
                                                .bindProperty("upper_limit")
                                                .bindPlaceholder("")
                                            )
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
        diagnostics = super(FindDuplicates, self).validate(context, component)

        schema_columns = []
        schema_js = json.loads(component.properties.schema)
        for js in schema_js:
            schema_columns.append(js["name"].lower())

        if component.properties.generationMethod != "allCols":
            if len(component.properties.groupByColumnNames) == 0:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.groupByColumnNames",
                        f"Select atleast one column from the dropdown",
                        SeverityLevelEnum.Error,
                    )
                )
            if len(component.properties.groupByColumnNames) > 0:
                missingKeyColumns = [
                    col
                    for col in component.properties.groupByColumnNames
                    if col not in component.properties.schema
                ]
                if missingKeyColumns:
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.groupByColumnNames",
                            f"Selected columns {missingKeyColumns} are not present in input schema.",
                            SeverityLevelEnum.Error,
                        )
                    )
        if component.properties.output_type in (
                "custom_group_count",
                "custom_row_number",
        ):
            if component.properties.column_group_rownum_condition == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.column_group_rownum_condition",
                        f"Select one option from the given dropdown for custom filter",
                        SeverityLevelEnum.Error,
                    )
                )
            if component.properties.column_group_rownum_condition == "between":
                if (component.properties.lower_limit).isdigit() == False:
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.lower_limit",
                            f"Specify the lower limit value for grouped column count.",
                            SeverityLevelEnum.Error,
                        )
                    )
                if (component.properties.upper_limit).isdigit() == False:
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.upper_limit",
                            f"Specify the upper limit value for grouped column count.",
                            SeverityLevelEnum.Error,
                        )
                    )
                if (
                        (component.properties.upper_limit).isdigit()
                        and (component.properties.lower_limit).isdigit()
                        and int(component.properties.upper_limit)
                        < int(component.properties.lower_limit)
                ):
                    diagnostics.append(
                        Diagnostic(
                            "component.properties.column_group_rownum_condition",
                            f"upper limit value should be greater than lower limit value for grouped column count.",
                            SeverityLevelEnum.Error,
                        )
                    )
            elif (component.properties.grouped_count_rownum).isdigit() == False:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.grouped_count_rownum",
                        f"Group count should be a non-negative integer value",
                        SeverityLevelEnum.Error,
                    )
                )

        for idx, rule in enumerate(component.properties.orderByColumns):
            expr_text = (rule.expression.expression or "").strip()
            if rule.sortType and expr_text == "":
                diagnostics.append(
                    Diagnostic(
                        f"component.properties.orderByColumns[{idx}].expression.expression",
                        "Order column expression is required when a sort direction is selected.",
                        SeverityLevelEnum.Error,
                    )
                )

        return diagnostics

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

    def apply(self, props: FindDuplicatesProperties) -> str:
        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        schema_columns = []
        schema_js = json.loads(props.schema)
        for js in schema_js:
            schema_columns.append(js["name"].lower())

        order_rules: List[dict] = [
            {"expression": {"expression": expr, "format": r.expression.format}, "sortType": r.sortType}
            for r in props.orderByColumns
            for expr in [(r.expression.expression or "").strip()]  # temp var
            if expr  # keep non-empty
        ]

        def safe_str(val):
            if val is None or val == "":
                return "''"
            if isinstance(val, list):
                return str(val)
            return f"'{val}'"

        arguments = [
            str(props.relation_name),
            safe_str(props.groupByColumnNames),
            safe_str(props.column_group_rownum_condition),
            safe_str(props.output_type),
            safe_str(props.grouped_count_rownum),
            safe_str(props.lower_limit),
            safe_str(props.upper_limit),
            safe_str(props.generationMethod),
            safe_str(schema_columns),
            safe_str(order_rules),
        ]

        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)

        return FindDuplicates.FindDuplicatesProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            schema=parametersMap.get("schema"),
            groupByColumnNames=json.loads(
                parametersMap.get("groupByColumnNames").replace("'", '"')
            ),
            column_group_rownum_condition=parametersMap.get(
                "column_group_rownum_condition"
            ).lstrip("'").rstrip("'"),
            grouped_count_rownum=parametersMap.get("grouped_count_rownum").lstrip("'").rstrip("'"),
            lower_limit=parametersMap.get("lower_limit").lstrip("'").rstrip("'"),
            upper_limit=parametersMap.get("upper_limit").lstrip("'").rstrip("'"),
            output_type=parametersMap.get("output_type").lstrip("'").rstrip("'"),
            generationMethod=parametersMap.get('generationMethod').lstrip("'").rstrip("'"),
            orderByColumns=json.loads(
                parametersMap.get("orderByColumns").replace("'", '"')
            ),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter(
                    "groupByColumnNames", json.dumps(properties.groupByColumnNames)
                ),
                MacroParameter(
                    "column_group_rownum_condition",
                    str(properties.column_group_rownum_condition),
                ),
                MacroParameter(
                    "grouped_count_rownum", str(properties.grouped_count_rownum)
                ),
                MacroParameter("lower_limit", str(properties.lower_limit)),
                MacroParameter("upper_limit", str(properties.upper_limit)),
                MacroParameter("output_type", str(properties.output_type)),
                MacroParameter("generationMethod", str(properties.generationMethod)),
                MacroParameter(
                    "orderByColumns", json.dumps(properties.orderByColumns)
                ),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": field["name"], "dataType": field["dataType"]["type"]}
            for field in schema["fields"]
        ]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
        )
        return component.bindProperties(newProperties)

    def applyPython(self, spark: SparkSession, in0: DataFrame) -> DataFrame:

        if self.props.generationMethod == "selectedCols":
            group_cols = self.props.groupByColumnNames
            order_rules = self.props.orderByColumns
            order_cols = map(lambda x:
                             expr(x.expression.expression).asc() if (
                                     x.sortType == "asc") else expr(x.expression.expression).asc_nulls_last()
                             if (x.sortType == "asc_nulls_last") else expr(
                                 x.expression.expression).desc_nulls_first() if (
                                     x.sortType == "desc_nulls_first") else expr(x.expression.expression).desc(),
                             order_rules) if len(order_rules) > 0 else [lit(1)]
        else:
            group_cols = in0.columns
            order_cols = [lit(1)]

        window_rownum = Window.partitionBy(*group_cols).orderBy(*order_cols)
        window_count = Window.partitionBy(*group_cols)

        if self.props.output_type == "unique":
            res = in0.withColumn("temp_row_number", row_number().over(window_rownum)).filter(
                col("temp_row_number") == 1).drop("temp_row_number")
        elif self.props.output_type == "duplicate":
            res = in0.withColumn("temp_row_number", row_number().over(window_rownum)).filter(
                col("temp_row_number") > 1).drop("temp_row_number")
        elif self.props.output_type == "custom_group_count":
            cond = self.props.column_group_rownum_condition
            res = in0.withColumn("temp_row_count", count(lit(1)).over(window_count))
            if cond == "between":
                res = res.filter(
                    col("temp_row_count").between(int(self.props.lower_limit), int(self.props.upper_limit))).drop(
                    "temp_row_count")
            elif cond == "equal_to":
                res = res.filter(col("temp_row_count") == int(self.props.grouped_count_rownum)).drop("temp_row_count")
            elif cond == "not_equal_to":
                res = res.filter(col("temp_row_count") != int(self.props.grouped_count_rownum)).drop("temp_row_count")
            elif cond == "less_than":
                res = res.filter(col("temp_row_count") < int(self.props.grouped_count_rownum)).drop("temp_row_count")
            elif cond == "greater_than":
                res = res.filter(col("temp_row_count") > int(self.props.grouped_count_rownum)).drop("temp_row_count")
            else:
                res = res.drop("temp_row_count")
        elif self.props.output_type == "custom_row_number":
            cond = self.props.column_group_rownum_condition
            res = in0.withColumn("temp_row_num", row_number().over(window_rownum))
            if cond == "between":
                res = res.filter(
                    col("temp_row_num").between(int(self.props.lower_limit), int(self.props.upper_limit))).drop(
                    "temp_row_num")
            elif cond == "equal_to":
                res = res.filter(col("temp_row_num") == int(self.props.grouped_count_rownum)).drop("temp_row_num")
            elif cond == "not_equal_to":
                res = res.filter(col("temp_row_num") != int(self.props.grouped_count_rownum)).drop("temp_row_num")
            elif cond == "less_than":
                res = res.filter(col("temp_row_num") < int(self.props.grouped_count_rownum)).drop("temp_row_num")
            elif cond == "greater_than":
                res = res.filter(col("temp_row_num") > int(self.props.grouped_count_rownum)).drop("temp_row_num")
            else:
                res = res.drop("temp_row_num")
        else:
            res = in0

        return res
