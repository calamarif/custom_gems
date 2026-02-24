import dataclasses
import json

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import SparkSession
from pyspark.sql.functions import *


class DataMasking(MacroSpec):
    name: str = "DataMasking"
    projectName: str = "prophecy_basics"
    category: str = "Prepare"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class DataMaskingProperties(MacroProperties):
        # properties for the component with default values
        relation_name: List[str] = field(default_factory=list)
        schema: str = ""
        column_names: List[str] = field(default_factory=list)
        masking_method: str = ""
        upper_char_substitute: str = ""
        lower_char_substitute: str = ""
        digit_char_substitute: str = ""
        other_char_substitute: str = ""
        sha2_bit_length: str = ""
        prefix_suffix_option: str = "Prefix"
        prefix_suffix_added: str = ""
        combined_hash_column_name: str = ""
        masked_column_add_method: str = "inplace_substitute"

    def dialog(self) -> Dialog:
        mask_condition = Condition().ifEqual(
            PropExpr("component.properties.masking_method"), StringExpr("mask")
        )

        hash_condition = Condition().ifEqual(
            PropExpr("component.properties.masking_method"), StringExpr("hash")
        )

        not_hash_condition = Condition().ifNotEqual(
            PropExpr("component.properties.masking_method"), StringExpr("hash")
        )

        sha2_condition = Condition().ifEqual(
            PropExpr("component.properties.masking_method"), StringExpr("sha2")
        )

        mask_params_ui = StackLayout(height="100%").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    TextBox("Uppercase character replacement")
                    .bindProperty("upper_char_substitute")
                    .bindPlaceholder(
                        "Default value is 'X'. Specify NULL to retain original character"
                    )
                )
                .addElement(
                    TextBox("Lowercase character replacement")
                    .bindProperty("lower_char_substitute")
                    .bindPlaceholder(
                        "Default value is 'x'. Specify NULL to retain original character"
                    )
                )
            )
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    TextBox("Digit replacement")
                    .bindProperty("digit_char_substitute")
                    .bindPlaceholder(
                        "Default value is 'n'. Specify NULL to retain original character"
                    )
                )
                .addElement(
                    TextBox("Special character replacement")
                    .bindProperty("other_char_substitute")
                    .bindPlaceholder(
                        "Default value is NULL. Specify NULL to retain original character."
                    )
                )
            )
        )

        selectBox_nonHash = (
            RadioGroup("")
            .addOption(
                "Substitute the new columns in place",
                "inplace_substitute",
                description=(
                    "This option will substitute the original columns to have masked value with same name"
                ),
            )
            .addOption(
                "Add new columns with a prefix/suffix attached",
                "prefix_suffix_substitute",
                description="This option will keep the original columns intact and add new columns with added prefix/suffix to respective columns",
            )
            .setOptionType("button")
            .setVariant("medium")
            .setButtonStyle("solid")
            .bindProperty("masked_column_add_method")
        )
        selectBox_Hash = (
            RadioGroup("")
            .addOption(
                "Substitute the new columns in place",
                "inplace_substitute",
                description=(
                    "This option will substitute the original columns to have masked value with same name"
                ),
            )
            .addOption(
                "Add new columns with a prefix/suffix attached",
                "prefix_suffix_substitute",
                description="This option will keep the original columns intact and add new columns with added prefix/suffix to respective columns",
            )
            .addOption(
                "Apply a single hash to all the selected columns at once",
                "combinedHash_substitute",
                description="This option will apply a single hash to all the selected columns at once",
            )
            .setOptionType("button")
            .setVariant("medium")
            .setButtonStyle("solid")
            .bindProperty("masked_column_add_method")
        )

        sha2_params_ui = StackLayout(
            gap="1rem", height="100%", direction="vertical", width="100%"
        ).addElement(
            Condition()
                .ifEqual(PropExpr("$.sql.metainfo.providerType"), StringExpr("ProphecyManaged"))
                .then(
                    SelectBox("Select the bit length")
                    .bindProperty("sha2_bit_length")
                    .withDefault("256")
                    .addOption("256", "256")                
                )
                .otherwise(
                    SelectBox("Select the bit length")
                    .bindProperty("sha2_bit_length")
                    .withDefault("")
                    .addOption("224", "224")
                    .addOption("256", "256")
                    .addOption("384", "384")
                    .addOption("512", "512")                    
                )
        )

        dialog = Dialog("masking_dialog_box").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Select masking columns"))
                            .addElement(
                                SchemaColumnsDropdown("", appearance="minimal")
                                .withMultipleSelection()
                                .bindSchema("component.ports.inputs[0].schema")
                                .bindProperty("column_names")
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Masking configuration"))
                            .addElement(
                                Condition()
                                    .ifEqual(PropExpr("$.sql.metainfo.providerType"), StringExpr("ProphecyManaged"))
                                    .then(
                                        SelectBox("Select masking strategy")
                                        .bindProperty("masking_method")
                                        .withStyle({"width": "100%"})
                                        .withDefault("")
                                        .addOption("hash", "hash")
                                        .addOption("sha", "sha")
                                        .addOption("sha2", "sha2")
                                        .addOption("md5", "md5")
                                    )
                                    .otherwise(
                                        SelectBox("Select masking strategy")
                                        .bindProperty("masking_method")
                                        .withStyle({"width": "100%"})
                                        .withDefault("")
                                        .addOption("hash", "hash")
                                        .addOption("sha", "sha")
                                        .addOption("sha2", "sha2")
                                        .addOption("md5", "md5")
                                        .addOption("mask", "mask")
                                        .addOption("crc32", "crc32")                                        
                                    )
                            )
                            .addElement(mask_condition.then(mask_params_ui))
                            .addElement(sha2_condition.then(sha2_params_ui))
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Masked column options"))
                            .addElement(
                                hash_condition.then(selectBox_Hash).otherwise(
                                    selectBox_nonHash
                                )
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr(
                                        "component.properties.masked_column_add_method"
                                    ),
                                    StringExpr("prefix_suffix_substitute"),
                                )
                                .then(
                                    StackLayout(height="100%").addElement(
                                        ColumnsLayout(gap="1rem", height="100%")
                                        .addColumn(
                                            SelectBox("Select type")
                                            .addOption("prefix", "Prefix")
                                            .addOption("suffix", "Suffix")
                                            .bindProperty("prefix_suffix_option"),
                                            "50%",
                                        )
                                        .addColumn(
                                            TextBox("Enter the value")
                                            .bindPlaceholder("Example: new_")
                                            .bindProperty("prefix_suffix_added"),
                                            "50%",
                                        )
                                    )
                                )
                            )
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr(
                                        "component.properties.masked_column_add_method"
                                    ),
                                    StringExpr("combinedHash_substitute"),
                                )
                                .then(
                                    TextBox("new column name for combined hash")
                                    .bindPlaceholder("")
                                    .bindProperty("combined_hash_column_name")
                                )
                            )
                        )
                    )
                )
            )
        )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(DataMasking, self).validate(context, component)

        schema_columns = []
        schema_js = json.loads(component.properties.schema)
        for js in schema_js:
            schema_columns.append(js["name"].lower())

        if len(component.properties.column_names) == 0:
            diagnostics.append(
                Diagnostic(
                    "component.properties.column_names",
                    f"Select atleast one column to apply masking on",
                    SeverityLevelEnum.Error,
                )
            )
        elif len(component.properties.column_names) > 0:
            missingKeyColumns = [
                col
                for col in component.properties.column_names
                if col.lower() not in schema_columns
            ]
            if missingKeyColumns:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.column_names",
                        f"Selected columns {missingKeyColumns} are not present in input schema.",
                        SeverityLevelEnum.Error,
                    )
                )
        if component.properties.masking_method == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.masking_method",
                    f"Select one masking method",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.masked_column_add_method == "prefix_suffix_substitute":
            if component.properties.prefix_suffix_option == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.prefix_suffix_option",
                        f"Select one option out of Prefix/Suffix for new column names",
                        SeverityLevelEnum.Error,
                    )
                )
            if component.properties.prefix_suffix_added == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.prefix_suffix_option",
                        f"Enter the prefix/suffix value to be added to new column",
                        SeverityLevelEnum.Error,
                    )
                )
        if component.properties.masked_column_add_method == "combinedHash_substitute":
            if component.properties.combined_hash_column_name == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.combined_hash_column_name",
                        f"Enter the new column name for combined hash",
                        SeverityLevelEnum.Error,
                    )
                )
        if (
            component.properties.masking_method == "sha2"
            and component.properties.sha2_bit_length == ""
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.masking_method",
                    f"bit length for sha2 masking cannot be empty.",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.masking_method == "mask" and (
            (component.properties.upper_char_substitute).upper() != "NULL"
            and len(component.properties.upper_char_substitute) > 1
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.upper_char_substitute",
                    f"length for upperChar substitute key cannot be greater than 1",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.masking_method == "mask" and (
            (component.properties.lower_char_substitute).upper() != "NULL"
            and len(component.properties.lower_char_substitute) > 1
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.lower_char_substitute",
                    f"length for lowerChar substitute key cannot be greater than 1",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.masking_method == "mask" and (
            (component.properties.digit_char_substitute).upper() != "NULL"
            and len(component.properties.digit_char_substitute) > 1
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.digit_char_substitute",
                    f"length for digitChar substitute key cannot be greater than 1",
                    SeverityLevelEnum.Error,
                )
            )
        if component.properties.masking_method == "mask" and (
            (component.properties.other_char_substitute).upper() != "NULL"
            and len(component.properties.other_char_substitute) > 1
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.other_char_substitute",
                    f"length for otherChar substitute key cannot be greater than 1",
                    SeverityLevelEnum.Error,
                )
            )

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

    def apply(self, props: DataMaskingProperties) -> str:
        # Generate the actual macro call given the component's state
        
        resolved_macro_name = f"{self.projectName}.{self.name}"
        schema_columns = [js["name"] for js in json.loads(props.schema)]
        remaining_columns = ", ".join(
            list(set(schema_columns) - set(props.column_names))
        )

        def safe_str(val):
            if val is None or val == "":
                return "''"
            if isinstance(val, list):
                return str(val)
            return f"'{val}'"

        arguments = [
            str(props.relation_name),
            safe_str(props.column_names),
            safe_str(remaining_columns),
            safe_str(props.masking_method),
            safe_str(
                props.upper_char_substitute
                if props.upper_char_substitute.upper() != "NULL"
                else props.upper_char_substitute.upper()
            ),
            safe_str(
                props.lower_char_substitute
                if props.lower_char_substitute.upper() != "NULL"
                else props.lower_char_substitute.upper()
            ),
            safe_str(
                props.digit_char_substitute
                if props.digit_char_substitute.upper() != "NULL"
                else props.digit_char_substitute.upper()
            ),
            safe_str(
                props.other_char_substitute
                if props.other_char_substitute.upper() != "NULL"
                else props.other_char_substitute.upper()
            ),
            safe_str(props.sha2_bit_length),
            safe_str(props.masked_column_add_method),
            safe_str(props.prefix_suffix_option),
            safe_str(props.prefix_suffix_added),
            safe_str(props.combined_hash_column_name),
        ]

        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return DataMasking.DataMaskingProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            schema=parametersMap.get("schema"),
            column_names=json.loads(
                parametersMap.get("column_names").replace("'", '"')
            ),
            masking_method=parametersMap.get('masking_method').lstrip("'").rstrip("'"),
            upper_char_substitute=parametersMap.get('upper_char_substitute').lstrip("'").rstrip("'"),
            lower_char_substitute=parametersMap.get('lower_char_substitute').lstrip("'").rstrip("'"),
            digit_char_substitute=parametersMap.get('digit_char_substitute').lstrip("'").rstrip("'"),
            other_char_substitute=parametersMap.get('other_char_substitute').lstrip("'").rstrip("'"),
            sha2_bit_length=parametersMap.get('sha2_bit_length').lstrip("'").rstrip("'"),
            masked_column_add_method=parametersMap.get('masked_column_add_method').lstrip("'").rstrip("'"),
            prefix_suffix_option=parametersMap.get("prefix_suffix_option"),
            prefix_suffix_added=parametersMap.get("prefix_suffix_added"),
            combined_hash_column_name=parametersMap.get('combined_hash_column_name').lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("column_names", json.dumps(properties.column_names)),
                MacroParameter("masking_method", str(properties.masking_method)),
                MacroParameter(
                    "upper_char_substitute", str(properties.upper_char_substitute)
                ),
                MacroParameter(
                    "lower_char_substitute", str(properties.lower_char_substitute)
                ),
                MacroParameter(
                    "digit_char_substitute", str(properties.digit_char_substitute)
                ),
                MacroParameter(
                    "other_char_substitute", str(properties.other_char_substitute)
                ),
                MacroParameter("sha2_bit_length", str(properties.sha2_bit_length)),
                MacroParameter(
                    "masked_column_add_method", str(properties.masked_column_add_method)
                ),
                MacroParameter(
                    "prefix_suffix_option", str(properties.prefix_suffix_option)
                ),
                MacroParameter(
                    "prefix_suffix_added", str(properties.prefix_suffix_added)
                ),
                MacroParameter(
                    "combined_hash_column_name",
                    str(properties.combined_hash_column_name),
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
        column_names = self.props.column_names
        masking_method = self.props.masking_method
        masked_column_add_method = self.props.masked_column_add_method
        prefix_suffix_option = self.props.prefix_suffix_option
        prefix_suffix_added = self.props.prefix_suffix_added
        combined_hash_column_name = self.props.combined_hash_column_name

        result_df = in0

        if masking_method == "mask":
            for cname in column_names:
                args = [f"`{cname}`"]
                subs = [
                    ("upperChar", getattr(self.props, "upper_char_substitute")),
                    ("lowerChar", getattr(self.props, "lower_char_substitute")),
                    ("digitChar", getattr(self.props, "digit_char_substitute")),
                    ("otherChar", getattr(self.props, "other_char_substitute")),
                ]
                for param, val in subs:
                    if val is None:
                        continue
                    v = str(val)
                    if v.upper() == "NULL":
                        args.append(f"{param} => NULL")
                    elif v != "":
                        args.append(f"{param} => '{v}'")

                mask_expr = f"mask({', '.join(args)})"
                target = cname if masked_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, expr(mask_expr))

        elif masking_method == "hash":
            if masked_column_add_method == "combinedHash_substitute":
                hash_expr = hash(*[col(c) for c in column_names])
                result_df = result_df.withColumn(combined_hash_column_name, hash_expr)
            else:
                for cname in column_names:
                    hash_expr = hash(col(cname))
                    target = cname if masked_column_add_method == "inplace_substitute" else (
                        f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                    )
                    result_df = result_df.withColumn(target, hash_expr)

        elif masking_method == "sha2":
            sha2_bit_length = int(self.props.sha2_bit_length) if self.props.sha2_bit_length else 256
            for cname in column_names:
                sha2_expr = sha2(col(cname).cast("string"), sha2_bit_length)
                target = cname if masked_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, sha2_expr)

        elif masking_method == "sha":
            for cname in column_names:
                sha_expr = sha1(col(cname).cast("string"))
                target = cname if masked_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, sha_expr)

        elif masking_method == "md5":
            for cname in column_names:
                md5_expr = md5(col(cname).cast("string"))
                target = cname if masked_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, md5_expr)

        elif masking_method == "crc32":
            for cname in column_names:
                crc32_expr = crc32(col(cname).cast("string"))
                target = cname if masked_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, crc32_expr)

        return result_df
