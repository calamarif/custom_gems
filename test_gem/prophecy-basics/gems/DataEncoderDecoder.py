import dataclasses
import json

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, base64, unbase64, hex as pyspark_hex, unhex, encode, decode, expr


class DataEncoderDecoder(MacroSpec):
    name: str = "DataEncoderDecoder"
    projectName: str = "prophecy_basics"
    category: str = "Transform"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class DataEncoderDecoderProperties(MacroProperties):
        # properties for the component with default values
        relation_name: List[str] = field(default_factory=list)
        schema: str = ""
        column_names: List[str] = field(default_factory=list)
        prefix_suffix_option: str = "Prefix"
        new_column_add_method: str = "inplace_substitute"
        prefix_suffix_added: str = "new_"
        enc_dec_method: str = ""
        enc_dec_charSet: str = "UTF-8"
        aes_enc_dec_mode: str = "GCM"
        aes_enc_dec_secretScope_key: str = ""
        aes_enc_dec_secretKey_key: str = ""
        aes_enc_dec_secretScope_aad: str = ""
        aes_enc_dec_secretKey_aad: str = ""
        aes_enc_dec_secretScope_iv: str = ""
        aes_enc_dec_secretKey_iv: str = ""

    def dialog(self) -> Dialog:
        aes_encrypt_condition = Condition().ifEqual(
            PropExpr("component.properties.enc_dec_method"), StringExpr("aes_encrypt")
        )

        # aes_decrypt_condition = Condition().ifEqual(
        #     PropExpr("component.properties.enc_dec_method"), StringExpr("aes_decrypt")
        # )

        # try_aes_decrypt_condition = Condition().ifEqual(
        #     PropExpr("component.properties.enc_dec_method"), StringExpr("try_aes_decrypt")
        # )

        encode_condition = Condition().ifEqual(
            PropExpr("component.properties.enc_dec_method"), StringExpr("encode")
        )

        decode_condition = Condition().ifEqual(
            PropExpr("component.properties.enc_dec_method"), StringExpr("decode")
        )

        new_column_condition = Condition().ifEqual(
            PropExpr("component.properties.new_column_add_method"), BooleanExpr(False)
        )

        selectBoxNewColumns = (
            RadioGroup("")
            .addOption(
                "Substitute the new columns in place",
                "inplace_substitute",
                description=(
                    "This option will substitute the original columns to have encoded/decoded value with same name"
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
            .bindProperty("new_column_add_method")
        )

        encode_decode_params_ui = StackLayout(
            gap="1rem", height="100%", direction="vertical", width="100%"
        ).addElement(
            SelectBox("Charset to use to encode/decode")
            .bindProperty("enc_dec_charSet")
            .withDefault("UTF-8")
            .addOption("'US-ASCII': Seven-bit ASCII, ISO646-US", "US-ASCII")
            .addOption(
                "'ISO-8859-1': ISO Latin Alphabet No. 1, ISO-LATIN-1", "ISO-8859-1"
            )
            .addOption("'UTF-8': Eight-bit UCS Transformation Format", "UTF-8")
            .addOption(
                "'UTF-16BE': Sixteen-bit UCS Transformation Format, big-endian byte order",
                "UTF-16BE",
            )
            .addOption(
                "'UTF-16LE': Sixteen-bit UCS Transformation Format, little-endian byte order",
                "UTF-16LE",
            )
            .addOption(
                "'UTF-16': Sixteen-bit UCS Transformation Format, byte order identified by an optional byte-order mark",
                "UTF-16",
            )
        )

        # try_aes_decrypt_params_ui = (
        #     StackLayout(gap="1rem", height="100%",direction="vertical", width="100%")
        #     .addElement(StepContainer()
        #     .addElement(
        #         Step()
        #         .addElement(
        #             StackLayout(height="100%")
        #             .addElement(TitleElement("Provide secret scope/key for encryption key, It must be 16, 24, or 32 bytes long *"))
        #             .addElement(
        #                 ColumnsLayout(gap="1rem", height="100%")
        #                 .addColumn(
        #                     TextBox("Secret Scope").bindProperty("aes_enc_dec_secretScope_key").bindPlaceholder(""), "50%"
        #                 )
        #                 .addColumn(
        #                     TextBox("Secret Key").bindProperty("aes_enc_dec_secretKey_key").bindPlaceholder(""), "50%"
        #                 )
        #             )
        #         )
        #     )
        #     )
        #     .addElement(SelectBox("mode").bindProperty("aes_enc_dec_mode").withDefault("GCM")
        #                 .addOption("Galois/Counter Mode (GCM)", "GCM")
        #                 .addOption("Electronic CodeBook (ECB)", "ECB")
        #                 )
        #     .addElement(
        #         Condition().ifEqual(PropExpr("component.properties.aes_enc_dec_mode"), StringExpr("GCM")).then(
        #             StepContainer()
        #             .addElement(
        #                 Step()
        #                 .addElement(
        #                     StackLayout(height="100%")
        #                     .addElement(TitleElement("Provide secret scope/key for encryption authenticated additional data(AAD)"))
        #                     .addElement(
        #                         ColumnsLayout(gap="1rem", height="100%")
        #                         .addColumn(
        #                             TextBox("Secret Scope").bindProperty("aes_enc_dec_secretScope_aad").bindPlaceholder(""), "50%"
        #                         )
        #                         .addColumn(
        #                             TextBox("Secret Key").bindProperty("aes_enc_dec_secretKey_aad").bindPlaceholder(""), "50%"
        #                         )
        #                     )
        #                 )
        #             )
        #         )
        #     )
        # )

        # aes_decrypt_params_ui = (
        #     StackLayout(gap="1rem", height="100%",direction="vertical", width="100%")
        #     .addElement(
        #         StepContainer()
        #         .addElement(
        #             Step()
        #             .addElement(
        #                 StackLayout(height="100%")
        #                 .addElement(TitleElement("Provide secret scope/key for encryption key, It must be 16, 24, or 32 bytes long *"))
        #                 .addElement(
        #                     ColumnsLayout(gap="1rem", height="100%")
        #                     .addColumn(
        #                         TextBox("Secret Scope").bindProperty("aes_enc_dec_secretScope_key").bindPlaceholder(""), "50%"
        #                     )
        #                     .addColumn(
        #                         TextBox("Secret Key").bindProperty("aes_enc_dec_secretKey_key").bindPlaceholder(""), "50%"
        #                     )
        #                 )
        #             )
        #         )
        #     )
        #     .addElement(SelectBox("mode").bindProperty("aes_enc_dec_mode").withDefault("GCM")
        #                 .addOption("Galois/Counter Mode (GCM)", "GCM")
        #                 .addOption("Cipher-Block Chaining (CBC)", "CBC")
        #                 .addOption("Electronic CodeBook (ECB)", "ECB")
        #                 )
        #     .addElement(
        #         Condition().ifEqual(PropExpr("component.properties.aes_enc_dec_mode"), StringExpr("GCM")).then(
        #             StepContainer()
        #             .addElement(
        #                 Step()
        #                 .addElement(
        #                     StackLayout(height="100%")
        #                     .addElement(TitleElement("Provide secret scope/key for encryption authenticated additional data(AAD)"))
        #                     .addElement(
        #                         ColumnsLayout(gap="1rem", height="100%")
        #                         .addColumn(
        #                             TextBox("Secret Scope").bindProperty("aes_enc_dec_secretScope_aad").bindPlaceholder(""), "50%"
        #                         )
        #                         .addColumn(
        #                             TextBox("Secret Key").bindProperty("aes_enc_dec_secretKey_aad").bindPlaceholder(""), "50%"
        #                         )
        #                     )
        #                 )
        #             )
        #         )
        #     )
        # )

        aes_encrypt_params_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical", width="100%")
            .addElement(
                StepContainer().addElement(
                    Step().addElement(
                        StackLayout(height="100%")
                        .addElement(
                            TitleElement(
                                "Provide Databricks secret scope/key for encryption key, It must be 16, 24, or 32 bytes long *"
                            )
                        )
                        .addElement(
                            ColumnsLayout(gap="1rem", height="100%")
                            .addColumn(
                                TextBox("Secret Scope")
                                .bindProperty("aes_enc_dec_secretScope_key")
                                .bindPlaceholder(""),
                                "50%",
                            )
                            .addColumn(
                                TextBox("Secret Key")
                                .bindProperty("aes_enc_dec_secretKey_key")
                                .bindPlaceholder(""),
                                "50%",
                            )
                        )
                    )
                )
            )
            .addElement(
                SelectBox("mode")
                .bindProperty("aes_enc_dec_mode")
                .withDefault("GCM")
                .addOption("Galois/Counter Mode (GCM)", "GCM")
                .addOption("Cipher-Block Chaining (CBC)", "CBC")
                .addOption("Electronic CodeBook (ECB)", "ECB")
            )
            .addElement(
                Condition()
                .ifEqual(
                    PropExpr("component.properties.aes_enc_dec_mode"), StringExpr("GCM")
                )
                .then(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(
                                TitleElement(
                                    "Provide Databricks secret scope/key for encryption authenticated additional data(AAD)"
                                )
                            )
                            .addElement(
                                ColumnsLayout(gap="1rem", height="100%")
                                .addColumn(
                                    TextBox("Secret Scope")
                                    .bindProperty("aes_enc_dec_secretScope_aad")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                                .addColumn(
                                    TextBox("Secret Key")
                                    .bindProperty("aes_enc_dec_secretKey_aad")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                            )
                        )
                    )
                )
            )
            .addElement(
                Condition()
                .ifEqual(
                    PropExpr("component.properties.aes_enc_dec_mode"), StringExpr("GCM")
                )
                .then(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(
                                TitleElement(
                                    "Provide Databricks secret scope/key for initialization vector(iv), STRING expression when specified, must be 12-bytes long"
                                )
                            )
                            .addElement(
                                ColumnsLayout(gap="1rem", height="100%")
                                .addColumn(
                                    TextBox("Secret Scope")
                                    .bindProperty("aes_enc_dec_secretScope_iv")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                                .addColumn(
                                    TextBox("Secret Key")
                                    .bindProperty("aes_enc_dec_secretKey_iv")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                            )
                        )
                    )
                )
            )
            .addElement(
                Condition()
                .ifEqual(
                    PropExpr("component.properties.aes_enc_dec_mode"), StringExpr("CBC")
                )
                .then(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(
                                TitleElement(
                                    "Provide Databricks secret scope/key for initialization vector(iv), STRING expression when specified, must be 16-bytes"
                                )
                            )
                            .addElement(
                                ColumnsLayout(gap="1rem", height="100%")
                                .addColumn(
                                    TextBox("Secret Scope")
                                    .bindProperty("aes_enc_dec_secretScope_iv")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                                .addColumn(
                                    TextBox("Secret Key")
                                    .bindProperty("aes_enc_dec_secretKey_iv")
                                    .bindPlaceholder(""),
                                    "50%",
                                )
                            )
                        )
                    )
                )
            )
        )

        dialog = Dialog("encoder_decoder").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Select columns to encode/decode"))
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
                            .addElement(TitleElement("Select encode / decode option"))
                            .addElement(
                                Condition()
                                    .ifEqual(PropExpr("$.sql.metainfo.providerType"), StringExpr("ProphecyManaged"))
                                    .then(
                                        SelectBox("Choose your encoding/decoding method")
                                        .bindProperty("enc_dec_method")
                                        .withStyle({"width": "100%"})
                                        .withDefault("")
                                        .addOption("base64", "base64")
                                        .addOption("unbase64", "unbase64")
                                        .addOption("hex", "hex")
                                        .addOption("unhex", "unhex")                                        
                                    )
                                    .otherwise(
                                        SelectBox("Choose your encoding/decoding method")
                                        .bindProperty("enc_dec_method")
                                        .withStyle({"width": "100%"})
                                        .withDefault("")
                                        .addOption("base64", "base64")
                                        .addOption("unbase64", "unbase64")
                                        .addOption("hex", "hex")
                                        .addOption("unhex", "unhex")
                                        .addOption("encode", "encode")
                                        .addOption("decode", "decode")
                                        .addOption("aes_encrypt", "aes_encrypt")
                                        # .addOption("aes_decrypt", "aes_decrypt")
                                        # .addOption("try_aes_decrypt", "try_aes_decrypt")
                                    )                       
                            )
                            .addElement(
                                aes_encrypt_condition.then(aes_encrypt_params_ui)
                            )
                            # .addElement(
                            #     aes_decrypt_condition.then(
                            #         aes_decrypt_params_ui
                            #     )
                            # )
                            # .addElement(
                            #     try_aes_decrypt_condition.then(
                            #         try_aes_decrypt_params_ui
                            #     )
                            # )
                            .addElement(encode_condition.then(encode_decode_params_ui))
                            .addElement(decode_condition.then(encode_decode_params_ui))
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Transformed column options"))
                            .addElement(selectBoxNewColumns)
                            .addElement(
                                Condition()
                                .ifEqual(
                                    PropExpr(
                                        "component.properties.new_column_add_method"
                                    ),
                                    StringExpr("prefix_suffix_substitute"),
                                )
                                .then(
                                    StackLayout(height="100%").addElement(
                                        ColumnsLayout(gap="1rem", height="100%")
                                        .addColumn(
                                            SelectBox("Select type")
                                            .addOption("Prefix", "Prefix")
                                            .addOption("Suffix", "Suffix")
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
                        )
                    )
                )
            )
        )
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        # Validate the component's state
        diagnostics = super(DataEncoderDecoder, self).validate(context, component)
        enc_dec_method = component.properties.enc_dec_method
        aes_enc_dec_secretScope_key = component.properties.aes_enc_dec_secretScope_key
        aes_enc_dec_secretKey_key = component.properties.aes_enc_dec_secretKey_key
        aes_enc_dec_secretScope_aad = component.properties.aes_enc_dec_secretScope_aad
        aes_enc_dec_secretKey_aad = component.properties.aes_enc_dec_secretKey_aad
        aes_enc_dec_secretKey_iv = component.properties.aes_enc_dec_secretKey_iv
        aes_enc_dec_secretScope_iv = component.properties.aes_enc_dec_secretScope_iv

        schema_columns = []
        schema_js = json.loads(component.properties.schema)
        for js in schema_js:
            schema_columns.append(js["name"])

        doing_aes_encryption = None
        if enc_dec_method in ("aes_decrypt", "try_aes_decrypt"):
            doing_aes_encryption = False
        elif enc_dec_method == "aes_encrypt":
            doing_aes_encryption = True

        if len(component.properties.column_names) == 0:
            diagnostics.append(
                Diagnostic(
                    "component.properties.column_names",
                    f"Select atleast one column from the input port dataset dropdown",
                    SeverityLevelEnum.Error,
                )
            )
        if len(component.properties.column_names) > 0:
            missingKeyColumns = [
                col
                for col in component.properties.column_names
                if col not in schema_columns
            ]
            if missingKeyColumns:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.column_names",
                        f"Selected columns {missingKeyColumns} are not present in input schema.",
                        SeverityLevelEnum.Error,
                    )
                )
        if component.properties.new_column_add_method == "prefix_suffix_substitute":
            if component.properties.prefix_suffix_option is None:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.prefix_suffix_option",
                        f"Select atleast one option Prefix/Suffix for new column names",
                        SeverityLevelEnum.Error,
                    )
                )
            if component.properties.prefix_suffix_added is None:
                diagnostics.append(
                    Diagnostic(
                        "component.properties.prefix_suffix_option",
                        f"Enter the prefix/suffix text to be added to new column",
                        SeverityLevelEnum.Error,
                    )
                )
        if enc_dec_method == "":
            diagnostics.append(
                Diagnostic(
                    "component.properties.enc_dec_method",
                    f"Select one encoding/decoding method from the listed dropdown",
                    SeverityLevelEnum.Error,
                )
            )

        if doing_aes_encryption is not None:
            if aes_enc_dec_secretScope_key == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretScope_key",
                        f"Secret scope for {'encryption' if doing_aes_encryption == True else 'decryption'} key should not be empty",
                        SeverityLevelEnum.Error,
                    )
                )
            if aes_enc_dec_secretKey_key == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretKey_key",
                        f"Secret key for {'encryption' if doing_aes_encryption == True else 'decryption'} key should not be empty",
                        SeverityLevelEnum.Error,
                    )
                )

            if aes_enc_dec_secretScope_aad == "" and aes_enc_dec_secretKey_aad != "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretScope_aad",
                        f"Secret scope for {'encryption' if doing_aes_encryption == True else 'decryption'} AAD should not be empty",
                        SeverityLevelEnum.Error,
                    )
                )
            if aes_enc_dec_secretScope_aad != "" and aes_enc_dec_secretKey_aad == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretKey_aad",
                        f"Secret Key for {'encryption' if doing_aes_encryption == True else 'decryption'} AAD should not be empty",
                        SeverityLevelEnum.Error,
                    )
                )

            if aes_enc_dec_secretScope_iv == "" and aes_enc_dec_secretKey_iv != "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretScope_iv",
                        f"Secret scope for {'encryption' if doing_aes_encryption == True else 'decryption'} iv should not be empty",
                        SeverityLevelEnum.Error,
                    )
                )
            if aes_enc_dec_secretScope_iv != "" and aes_enc_dec_secretKey_iv == "":
                diagnostics.append(
                    Diagnostic(
                        "component.properties.aes_enc_dec_secretKey_iv",
                        f"Secret Key for {'encryption' if doing_aes_encryption == True else 'decryption'} iv should not be empty",
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

        old_enc_method, old_enc_mode = (
            oldState.properties.enc_dec_method,
            oldState.properties.aes_enc_dec_mode,
        )
        new_enc_method, new_enc_mode = (
            newState.properties.enc_dec_method,
            newState.properties.aes_enc_dec_mode,
        )

        if old_enc_method != new_enc_method or old_enc_mode != new_enc_mode:
            (
                aes_enc_dec_secretScope_key,
                aes_enc_dec_secretKey_key,
                aes_enc_dec_secretScope_iv,
                aes_enc_dec_secretKey_iv,
                aes_enc_dec_secretScope_aad,
                aes_enc_dec_secretKey_aad,
            ) = ("", "", "", "", "", "")
        else:
            aes_enc_dec_secretScope_iv, aes_enc_dec_secretKey_iv = (
                newState.properties.aes_enc_dec_secretScope_iv,
                newState.properties.aes_enc_dec_secretKey_iv,
            )
            aes_enc_dec_secretScope_aad, aes_enc_dec_secretKey_aad = (
                newState.properties.aes_enc_dec_secretScope_aad,
                newState.properties.aes_enc_dec_secretKey_aad,
            )

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
            aes_enc_dec_secretScope_iv=aes_enc_dec_secretScope_iv,
            aes_enc_dec_secretKey_iv=aes_enc_dec_secretKey_iv,
            aes_enc_dec_secretScope_aad=aes_enc_dec_secretScope_aad,
            aes_enc_dec_secretKey_aad=aes_enc_dec_secretKey_aad,
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: DataEncoderDecoderProperties) -> str:
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
            safe_str(props.enc_dec_method),
            safe_str(props.enc_dec_charSet),
            safe_str(props.aes_enc_dec_secretScope_key),
            safe_str(props.aes_enc_dec_secretKey_key),
            safe_str(props.aes_enc_dec_mode),
            safe_str(props.aes_enc_dec_secretScope_aad),
            safe_str(props.aes_enc_dec_secretKey_aad),
            safe_str(props.aes_enc_dec_secretScope_iv),
            safe_str(props.aes_enc_dec_secretKey_iv),
            safe_str(props.prefix_suffix_option),
            safe_str(props.new_column_add_method),
            safe_str(props.prefix_suffix_added),
        ]

        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return DataEncoderDecoder.DataEncoderDecoderProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            schema=parametersMap.get("schema"),
            column_names=json.loads(
                parametersMap.get("column_names").replace("'", '"')
            ),
            enc_dec_method=parametersMap.get('enc_dec_method').lstrip("'").rstrip("'"),
            enc_dec_charSet=parametersMap.get('enc_dec_charSet').lstrip("'").rstrip("'"),
            aes_enc_dec_secretScope_key=parametersMap.get('aes_enc_dec_secretScope_key').lstrip("'").rstrip("'"),
            aes_enc_dec_secretKey_key=parametersMap.get('aes_enc_dec_secretKey_key').lstrip("'").rstrip("'"),
            aes_enc_dec_mode=parametersMap.get('aes_enc_dec_mode').lstrip("'").rstrip("'"),
            aes_enc_dec_secretScope_aad=parametersMap.get('aes_enc_dec_secretScope_aad').lstrip("'").rstrip("'"),
            aes_enc_dec_secretKey_aad=parametersMap.get('aes_enc_dec_secretKey_aad').lstrip("'").rstrip("'"),
            aes_enc_dec_secretScope_iv=parametersMap.get('aes_enc_dec_secretScope_iv').lstrip("'").rstrip("'"),
            aes_enc_dec_secretKey_iv=parametersMap.get('aes_enc_dec_secretKey_iv').lstrip("'").rstrip("'"),

            prefix_suffix_option=parametersMap.get("prefix_suffix_option"),
            new_column_add_method=parametersMap.get("new_column_add_method"),
            prefix_suffix_added=parametersMap.get("prefix_suffix_added"),
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
                MacroParameter("enc_dec_method", str(properties.enc_dec_method)),
                MacroParameter("enc_dec_charSet", str(properties.enc_dec_charSet)),
                MacroParameter(
                    "aes_enc_dec_secretScope_key",
                    str(properties.aes_enc_dec_secretScope_key),
                ),
                MacroParameter(
                    "aes_enc_dec_secretKey_key",
                    str(properties.aes_enc_dec_secretKey_key),
                ),
                MacroParameter("aes_enc_dec_mode", str(properties.aes_enc_dec_mode)),
                MacroParameter(
                    "aes_enc_dec_secretScope_aad",
                    str(properties.aes_enc_dec_secretScope_aad),
                ),
                MacroParameter(
                    "aes_enc_dec_secretKey_aad",
                    str(properties.aes_enc_dec_secretKey_aad),
                ),
                MacroParameter(
                    "aes_enc_dec_secretScope_iv",
                    str(properties.aes_enc_dec_secretScope_iv),
                ),
                MacroParameter(
                    "aes_enc_dec_secretKey_iv", str(properties.aes_enc_dec_secretKey_iv)
                ),
                MacroParameter(
                    "prefix_suffix_option", str(properties.prefix_suffix_option)
                ),
                MacroParameter(
                    "new_column_add_method", str(properties.new_column_add_method)
                ),
                MacroParameter(
                    "prefix_suffix_added", str(properties.prefix_suffix_added)
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
        enc_dec_method = self.props.enc_dec_method
        enc_dec_charSet = self.props.enc_dec_charSet
        new_column_add_method = self.props.new_column_add_method
        prefix_suffix_option = self.props.prefix_suffix_option
        prefix_suffix_added = self.props.prefix_suffix_added

        result_df = in0

        if enc_dec_method == "base64":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, base64(col(cname)))

        elif enc_dec_method == "unbase64":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, decode(unbase64(col(cname)), "UTF-8"))

        elif enc_dec_method == "hex":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, hex(col(cname)))

        elif enc_dec_method == "unhex":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, decode(unhex(col(cname)), "UTF-8"))

        elif enc_dec_method == "encode":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, encode(col(cname), enc_dec_charSet))

        elif enc_dec_method == "decode":
            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                result_df = result_df.withColumn(target, decode(col(cname), enc_dec_charSet))

        elif enc_dec_method == "aes_encrypt":
            aes_enc_dec_secretScope_key = self.props.aes_enc_dec_secretScope_key
            aes_enc_dec_secretKey_key = self.props.aes_enc_dec_secretKey_key
            aes_enc_dec_mode = self.props.aes_enc_dec_mode
            aes_enc_dec_secretScope_iv = self.props.aes_enc_dec_secretScope_iv
            aes_enc_dec_secretKey_iv = self.props.aes_enc_dec_secretKey_iv
            aes_enc_dec_secretScope_aad = self.props.aes_enc_dec_secretScope_aad
            aes_enc_dec_secretKey_aad = self.props.aes_enc_dec_secretKey_aad

            for cname in column_names:
                target = cname if new_column_add_method == "inplace_substitute" else (
                    f"{prefix_suffix_added}{cname}" if prefix_suffix_option == "Prefix" else f"{cname}{prefix_suffix_added}"
                )
                args = [
                    f"`{cname}`",
                    f"secret('{aes_enc_dec_secretScope_key}', '{aes_enc_dec_secretKey_key}')",
                    f"'{aes_enc_dec_mode}'",
                    "'DEFAULT'"
                ]
                if aes_enc_dec_secretScope_iv and aes_enc_dec_secretKey_iv:
                    args.append(f"secret('{aes_enc_dec_secretScope_iv}', '{aes_enc_dec_secretKey_iv}')")
                else:
                    args.append('""')
                if aes_enc_dec_secretScope_aad and aes_enc_dec_secretKey_aad:
                    args.append(f"secret('{aes_enc_dec_secretScope_aad}', '{aes_enc_dec_secretKey_aad}')")
                aes_expr = f"base64(aes_encrypt({', '.join(args)}))"
                result_df = result_df.withColumn(target, expr(aes_expr))

        return result_df
