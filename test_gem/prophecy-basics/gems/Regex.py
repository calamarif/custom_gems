
import dataclasses
from dataclasses import dataclass, field
import json
import re

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql.window import Window

from collections import defaultdict
from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


@dataclass(frozen=True)
class ColumnParse:
    columnName: str
    dataType: str
    rgxExpression: str


class Regex(MacroSpec):
    name: str = "Regex"
    projectName: str = "prophecy_basics"
    category: str = "Parse"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        # ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class RegexProperties(MacroProperties):
        # properties for the component with default values
        selectedColumnName: str = ""
        schema: str = ''
        relation_name: List[str] = field(default_factory=list)
        regexExpression: str = ""
        caseInsensitive: bool = False
        allowBlankTokens: bool = False
        outputMethod: str = "replace"
        # Replace
        replacementText: Optional[str] = ""
        copyUnmatchedText: bool = False
        # Tokenize
        tokenizeOutputMethod: str = "splitColumns"
        noOfColumns: int = 1
        extraColumnsHandling: str = "dropExtraWithoutWarning"
        splitRowsColumnName: str = "generated_column"
        outputRootName: str = "generated"
        # Parse
        parseColumns: List[ColumnParse] = field(default_factory=list)
        # Match
        matchColumnName: str = "regex_match"
        errorIfNotMatched: bool = False


    def dialog(self) -> Dialog:
        return Dialog("MacroRegex").addElement(
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
                        TitleElement("Select column to parse")
                    )
                    .addElement(
                        SchemaColumnsDropdown("")
                        .bindSchema("component.ports.inputs[0].schema")
                        .bindProperty("selectedColumnName")
                        .showErrorsFor("selectedColumnName")
                    )
                    .addElement(
                        StepContainer()
                        .addElement(
                            Step()
                            .addElement(
                                StackLayout(height="100%")
                                .addElement(TitleElement("Regex"))
                                .addElement(
                                    TextBox("").bindPlaceholder("Regex Expression").bindProperty("regexExpression")
                                )
                                .addElement(
                                    Checkbox("Case Insensitive Matching").bindProperty("caseInsensitive")
                                )
                                .addElement(
                                    AlertBox(
                                        variant="success",
                                        _children=[
                                            Markdown(
                                                "**Common Regex Pattern Examples:**"
                                                "\n"
                                                "- **Email extraction:**"
                                                "\n"
                                                "**Pattern:** `([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})`"
                                                "\n"
                                                "Example: Extract user and domain from john.doe@company.com"
                                                "\n"
                                                "- **Phone number parsing:**"
                                                "\n"
                                                "**Pattern:** `(\d{3})-(\d{3})-(\d{4})`"
                                                "\n"
                                                "Example: Parse (555)-123-4567 into area code, exchange, number"
                                                "\n"
                                                "- **Date extraction (MM/DD/YYYY):**"
                                                "\n"
                                                "**Pattern:** `(\d{1,2})/(\d{1,2})/(\d{4})`"
                                                "\n"
                                                "Example: Extract 12/25/2023 into month, day, year"
                                                "\n"
                                                "- **Word tokenization:**"
                                                "\n"
                                                "**Pattern:** `([^\s]+)`"
                                                "\n"
                                                "Example: Split \"Hello World Example\" into individual words"
                                                "\n"
                                                "- **Comma-separated values:**"
                                                "\n"
                                                "**Pattern:** `([^,]+)`"
                                                "\n"
                                                "Example: Split \"Value1,Value2,Value3\" into separate values"
                                                "\n"
                                                "- **Extract numbers only:**"
                                                "\n"
                                                "**Pattern:** `(\d+)`"
                                                "\n"
                                                "Example: Extract 123 from \"Price: $123.45\""
                                                "\n"
                                                "- **URL components:**"
                                                "\n"
                                                "**Pattern:** `https?://([^/]+)(/.*)?`"
                                                "\n"
                                                "Example: Extract domain and path from URLs"
                                                "\n"
                                                "- **Remove special characters:**"
                                                "\n"
                                                "**Pattern:** `[^a-zA-Z0-9\s]`"
                                                "\n"
                                                "Example: Remove punctuation, keep letters, numbers, spaces"
                                                "\n"
                                                "- **Match uppercase words:**"
                                                "\n"
                                                "**Pattern:** `\b[A-Z]{2,}\b`"
                                                "\n"
                                                "Example: Find acronyms like \"USA\", \"API\", \"SQL\""
                                                "\n"
                                                "- **Extract text between quotes:**"
                                                "\n"
                                                "**Pattern:** `([^\"]*)`"
                                                "\n"
                                                "Example: Extract content from \"quoted text\""
                                            )
                                        ]
                                    )
                                )
                            )
                        )
                        .addElement(
                            RadioGroup("Output strategy")
                            .addOption(
                                "Replace",
                                "replace",
                                description=("Replace matched text with replacement text")
                            )
                            .addOption(
                                "Tokenize",
                                "tokenize",
                                description=("Split the incoming data using a regular expression")
                            )
                            .addOption(
                                "Parse",
                                "parse",
                                description=("Separate the value into new columns based on regex groups defined.")
                            )
                            .addOption(
                                "Match",
                                "match",
                                description=("Create new column with 1/0 value, based on the column value matching the regex expression.")
                            )
                            .setOptionType("button")
                            .setVariant("medium")
                            .setButtonStyle("solid")
                            .bindProperty("outputMethod")
                        )
                    )
                    .addElement(
                        StepContainer()
                        .addElement(
                            # Replace Method Configuration
                            Condition()
                            .ifEqual(PropExpr("component.properties.outputMethod"), StringExpr("replace"))
                            .then(
                                Step()
                                .addElement(
                                    StackLayout(height="100%")
                                    .addElement(TitleElement("Replace Configuration"))
                                    .addElement(
                                        TextBox("Replacement Text")
                                        .bindPlaceholder("Enter replacement expression")
                                        .bindProperty("replacementText")
                                    )
                                    .addElement(
                                        Checkbox("Copy Unmatched Text to Output")
                                        .bindProperty("copyUnmatchedText")
                                    )
                                )
                            ).otherwise(
                                # Tokenize Method Configuration
                                Condition()
                                .ifEqual(PropExpr("component.properties.outputMethod"), StringExpr("tokenize"))
                                .then(
                                    Step()
                                    .addElement(
                                        StackLayout(height="100%")
                                        .addElement(TitleElement("Tokenize Configuration"))
                                        .addElement(
                                            RadioGroup("Select Split Strategy")
                                            .addOption("Split to columns", "splitColumns")
                                            .addOption("Split to rows", "splitRows")
                                            .bindProperty("tokenizeOutputMethod")
                                        ).addElement(
                                            Checkbox("Allow Blank Tokens").bindProperty("allowBlankTokens")
                                        )
                                        .addElement(
                                            TextBox("Output Root Name")
                                            .bindPlaceholder("Enter Generated Column Suffix")
                                            .bindProperty("outputRootName")
                                        )
                                        .addElement(
                                            Condition()
                                            .ifEqual(PropExpr("component.properties.tokenizeOutputMethod"), StringExpr("splitColumns"))
                                            .then(
                                                StackLayout(height="100%")
                                                .addElement(
                                                    ColumnsLayout(gap="1rem", height="100%")
                                                    .addColumn(
                                                        NumberBox("Number of columns", placeholder=1, requiredMin=1)
                                                        .bindProperty("noOfColumns")
                                                    )
                                                    .addColumn(
                                                        SelectBox(titleVar="For Extra Columns")
                                                        .addOption("Drop Extra without Warning", "dropExtraWithoutWarning")
                                                        .addOption("Drop Extra with Error", "dropExtraWithError")
                                                        .addOption("Save all remaining text into last generated column", "saveAllRemainingText")
                                                        .bindProperty("extraColumnsHandling")
                                                    )
                                                )
                                            )
                                        )
                                    )
                                ).otherwise(
                                    # Parse Method Configuration
                                    Condition()
                                    .ifEqual(PropExpr("component.properties.outputMethod"), StringExpr("parse"))
                                    .then(
                                        Step()
                                        .addElement(
                                            StackLayout(height="100%")
                                            .addElement(TitleElement("Parse Configuration"))
                                            .addElement(
                                                StackLayout(height="100%")
                                                .addElement(
                                                    AlertBox(
                                                        variant="info",
                                                        _children=[
                                                            Markdown("Configure the output columns for parsed groups. Each capture group in your regex will create a new column.")
                                                        ]
                                                    )
                                                )
                                                .addElement(
                                                    StepContainer()
                                                    .addElement(
                                                        Step().addElement(
                                                            BasicTable("Parse Columns Table", height="200px", columns=[
                                                                Column(
                                                                    "New Column Name",
                                                                    "columnName",
                                                                    TextBox("")
                                                                    .bindPlaceholder("Column Name")
                                                                ),
                                                                Column(
                                                                    "Select Data Type",
                                                                    "dataType",
                                                                    SelectBox("")
                                                                    .addOption("String", "string")
                                                                    .addOption("Integer", "int")
                                                                    .addOption("Double", "double")
                                                                    .addOption("Boolean", "bool")
                                                                    .addOption("Date", "date")
                                                                    .addOption("DateTime", "datetime"),
                                                                    width="20%"
                                                                ),
                                                                Column(
                                                                    "Regex Expression",
                                                                    "rgxExpression",
                                                                    TextBox("", disabledView=True)
                                                                    .bindPlaceholder("Auto-generated from regex groups"),
                                                                    width="35%"
                                                                )
                                                            ])
                                                            .bindProperty("parseColumns")
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    ).otherwise(
                                        # Match Method Configuration
                                        Condition()
                                        .ifEqual(PropExpr("component.properties.outputMethod"), StringExpr("match"))
                                        .then(
                                            Step()
                                            .addElement(
                                                StackLayout(height="100%")
                                                .addElement(TitleElement("Match Configuration"))
                                                .addElement(
                                                    TextBox("Column name for match status")
                                                    .bindPlaceholder("Enter name for match result column")
                                                    .bindProperty("matchColumnName")
                                                )
                                                .addElement(
                                                    Checkbox("Error if not Matched")
                                                    .bindProperty("errorIfNotMatched")
                                                )
                                                .addElement(
                                                    AlertBox(
                                                        variant="info",
                                                        _children=[
                                                            Markdown("This will add a new column containing 1 if the regex matched, 0 if it did not match.")
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
                )
            )
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
        # Validate the component's state
        diagnostics = super().validate(context, component)
        props = component.properties

        # Check if columnName is provided
        if not hasattr(props, 'selectedColumnName') or not props.selectedColumnName or len(props.selectedColumnName.strip()) == 0:
            diagnostics.append(
                Diagnostic("component.properties.selectedColumnName", "Column Name is required and cannot be empty", SeverityLevelEnum.Error))

        # Check if regexExpression is provided
        if not hasattr(props, 'regexExpression') or not props.regexExpression or len(props.regexExpression.strip()) == 0:
            diagnostics.append(
                Diagnostic("component.properties.regexExpression", "Regex Expression is required and cannot be empty", SeverityLevelEnum.Error))

        # Validate regex pattern
        if len(props.regexExpression.strip()) > 0:
            import re
            try:
                re.compile(props.regexExpression)
            except re.error as e:
                diagnostics.append(
                    Diagnostic("component.properties.regexExpression", "Invalid regular expression", SeverityLevelEnum.Error))


        # Validate that columnName exists in input schema
        if (hasattr(props, 'selectedColumnName') and props.selectedColumnName and
                hasattr(props, 'schema') and props.schema):
            if props.selectedColumnName not in props.schema:
                diagnostics.append(
                    Diagnostic("component.properties.selectedColumnName", f"Selected column '{props.selectedColumnName}' is not present in input schema.", SeverityLevelEnum.Error))

        return diagnostics

    def extract_capturing_groups(self, pattern):
        """Extract individual capturing group patterns from a regex string."""
        if not pattern:
            return []
        groups = []
        i = 0
        while i < len(pattern):
            # Check if current character is an opening parenthesis
            if pattern[i] == '(':
                # Check if it's escaped
                if i > 0 and pattern[i-1] == '\\':
                    i += 1
                    continue

                # Check if it's a non-capturing group (?:...) or other special groups (?=...), (?!...), etc.
                if i + 1 < len(pattern) and pattern[i+1] == '?':
                    # Find the end of this non-capturing group and skip it
                    paren_count = 1
                    j = i + 2  # Skip the '(' and '?'
                    while j < len(pattern) and paren_count > 0:
                        # Handle escaped characters
                        if pattern[j] == '\\' and j + 1 < len(pattern):
                            j += 2
                            continue
                        elif pattern[j] == '(':
                            paren_count += 1
                        elif pattern[j] == ')':
                            paren_count -= 1
                        j += 1
                    i = j
                    continue

                # This is a capturing group - find its end
                start = i
                paren_count = 1
                j = i + 1

                while j < len(pattern) and paren_count > 0:
                    # Handle escaped characters (skip both the backslash and the next character)
                    if pattern[j] == '\\' and j + 1 < len(pattern):
                        j += 2
                        continue
                    elif pattern[j] == '(':
                        paren_count += 1
                    elif pattern[j] == ')':
                        paren_count -= 1
                    j += 1

                if paren_count == 0:
                    # Extract the group including the parentheses
                    group = pattern[start:j]
                    groups.append(group)
                i = j
            else:
                i += 1
        return groups

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(newState, context)

        # Generate ColumnParse objects based on regex capturing groups
        parse_columns = []
        if hasattr(newState.properties, 'regexExpression') and newState.properties.regexExpression:
            try:
                # Validate regex first
                compiled_regex = re.compile(newState.properties.regexExpression)

                # Extract individual capturing group patterns
                group_patterns = self.extract_capturing_groups(newState.properties.regexExpression)
                num_groups = len(group_patterns)

                # Get existing parseColumns if they exist
                existing_parse_columns = []
                if hasattr(newState.properties, 'parseColumns') and newState.properties.parseColumns:
                    existing_parse_columns = newState.properties.parseColumns

                # Create or update ColumnParse objects for each capturing group
                for i, group_pattern in enumerate(group_patterns, 1):
                    # Check if we already have configuration for this group index
                    existing_col = None
                    if i <= len(existing_parse_columns):
                        existing_col = existing_parse_columns[i-1]

                    if existing_col:
                        # Preserve existing configuration but update regex expression
                        parse_columns.append(ColumnParse(
                            columnName=existing_col.columnName,
                            dataType=existing_col.dataType,
                            rgxExpression=group_pattern
                        ))
                    else:
                        # Create new column with smart defaults
                        default_name = f"regex_col{i}"
                        default_type = self.infer_data_type_from_pattern(group_pattern)

                        parse_columns.append(ColumnParse(
                            columnName=default_name,
                            dataType=default_type,
                            rgxExpression=group_pattern
                        ))

                # If there are fewer groups now than before, truncate the list
                # This handles cases where the regex was modified to have fewer groups
                parse_columns = parse_columns[:num_groups]

            except re.error:
                # If regex is invalid, preserve existing parseColumns if any
                if hasattr(newState.properties, 'parseColumns') and newState.properties.parseColumns:
                    parse_columns = newState.properties.parseColumns
                else:
                    parse_columns = []

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
            parseColumns=parse_columns
        )
        return newState.bindProperties(newProperties)


    def infer_data_type_from_pattern(self, regex_pattern):
        """Infer likely data type from regex pattern."""
        pattern_lower = regex_pattern.lower()

        # Remove outer parentheses for analysis
        inner_pattern = regex_pattern.strip('()')

        # Check for common numeric patterns
        if any(indicator in inner_pattern for indicator in ['\\d', '[0-9]', 'digit']):
            # Check for decimal patterns
            if any(decimal_indicator in inner_pattern for decimal_indicator in ['\\.', '\\.']):
                return "double"
            # Check for specific digit counts that suggest integers
            elif '\\d{1,2}' in inner_pattern or '\\d{1,3}' in inner_pattern:
                return "int"
            elif '\\d+' in inner_pattern or '\\d{' in inner_pattern:
                return "int"

        # Check for boolean-like patterns
        elif any(bool_pattern in pattern_lower for bool_pattern in ['true|false', 'yes|no', 'y|n', '0|1']):
            return "bool"

        # Check for date patterns
        elif any(date_indicator in inner_pattern for date_indicator in ['\\d{4}', '\\d{2}[-/]\\d{2}', 'yyyy', 'mm', 'dd']):
            return "date"

        # Default to String for everything else
        return "string"

    def apply(self, props: RegexProperties) -> str:
        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"
        # Get the Single Table Name
        table_name: str = ",".join(str(rel) for rel in props.relation_name)
        # Create JSON string - json.dumps() handles double quotes, but we need to escape
        # single quotes for SQL string literals. The safe_str() function will handle this.
        parse_columns_list = [
            {
                "columnName": fld.columnName,
                "dataType": fld.dataType,
                "rgxExpression": fld.rgxExpression
            }
            for fld in props.parseColumns
        ]

        def safe_str(val):
            """
            Safely convert a value to a SQL string literal, handling None and empty strings.

            For regex expressions: This escapes single quotes for the SQL string literal parameter.
            The macro will then receive the unescaped value and escape it again via
            escape_regex_pattern() for use in the actual SQL query. This two-stage escaping
            is correct and necessary.

            Note: Backslashes in regex expressions are NOT escaped here - they are preserved
            as part of the regex pattern and will be handled by escape_regex_pattern() in the macro.
            """
            if val is None or val == "":
                return "''"
            if isinstance(val, str):
                # Escape single quotes for SQL string literals ('' represents a single quote in SQL)
                # This is the first stage of escaping - for the macro parameter
                escaped = val.replace("'", "''")
                return f"'{escaped}'"
            if isinstance(val, list):
                return str(val)
            return f"'{str(val)}'"

        parameter_list = [
            safe_str(props.relation_name),
            safe_str(parse_columns_list),
            safe_str(props.schema),
            safe_str(props.selectedColumnName),
            safe_str(props.regexExpression),  # Regex expression - escaped for SQL string literal parameter
            safe_str(props.outputMethod),
            str(props.caseInsensitive).lower(),
            str(props.allowBlankTokens).lower(),
            safe_str(props.replacementText),
            str(props.copyUnmatchedText).lower(),
            safe_str(props.tokenizeOutputMethod),
            str(props.noOfColumns),
            safe_str(props.extraColumnsHandling),
            safe_str(props.outputRootName),
            safe_str(props.matchColumnName),
            str(props.errorIfNotMatched).lower(),
        ]
        # Join all parameters - don't filter out empty strings, use "''" instead
        non_empty_param = ",".join(parameter_list)
        return f'{{{{ {resolved_macro_name}({non_empty_param}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        parseColumns = []
        # Double-escape backslashes and convert quotes to make valid JSON for json.loads()
        parseCols = json.loads(parametersMap.get('parseColumns').replace('\\', '\\\\').replace("'", '"'))
        for fld in parseCols:
            parseColumns.append(
                ColumnParse(
                    columnName=fld.get("columnName"),
                    dataType=fld.get("dataType"),
                    rgxExpression=fld.get("rgxExpression")
                )
            )
        return Regex.RegexProperties(
            relation_name=json.loads(parametersMap.get('relation_name').replace("'", '"')),
            parseColumns=parseColumns,
            schema=parametersMap.get('schema').lstrip("'").rstrip("'"),
            selectedColumnName=parametersMap.get('selectedColumnName').lstrip("'").rstrip("'"),
            regexExpression=parametersMap.get('regexExpression').lstrip("'").rstrip("'"),
            outputMethod=parametersMap.get('outputMethod').lstrip("'").rstrip("'"),
            caseInsensitive=parametersMap.get("caseInsensitive").lower()
                            == "true",
            allowBlankTokens=parametersMap.get("allowBlankTokens").lower()
                             == "true",
            replacementText=parametersMap.get('replacementText').lstrip("'").rstrip("'"),
            copyUnmatchedText=parametersMap.get("copyUnmatchedText").lower()
                              == "true",
            tokenizeOutputMethod=parametersMap.get('tokenizeOutputMethod').lstrip("'").rstrip("'"),
            noOfColumns=int(parametersMap.get('noOfColumns')),
            extraColumnsHandling=parametersMap.get('extraColumnsHandling').lstrip("'").rstrip("'"),
            outputRootName=parametersMap.get('outputRootName').lstrip("'").rstrip("'"),
            matchColumnName=parametersMap.get('matchColumnName').lstrip("'").rstrip("'"),
            errorIfNotMatched=parametersMap.get("errorIfNotMatched").lower()
                              == "true",
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        parseColumnsJsonList = json.dumps([{
            "columnName": fld.columnName,
            "dataType": fld.dataType,
            "rgxExpression": fld.rgxExpression
        }
            for fld in properties.parseColumns
        ])
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("parseColumns", parseColumnsJsonList),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("selectedColumnName", str(properties.selectedColumnName)),
                MacroParameter("outputMethod", str(properties.outputMethod)),
                MacroParameter("regexExpression", str(properties.regexExpression)),
                MacroParameter("caseInsensitive", str(properties.caseInsensitive).lower()),
                MacroParameter("replacementText", str(properties.replacementText)),
                MacroParameter("copyUnmatchedText", str(properties.copyUnmatchedText).lower()),
                MacroParameter("tokenizeOutputMethod", str(properties.tokenizeOutputMethod)),
                MacroParameter("allowBlankTokens", str(properties.allowBlankTokens).lower()),
                MacroParameter("noOfColumns", str(properties.noOfColumns)),
                MacroParameter("extraColumnsHandling", str(properties.extraColumnsHandling)),
                MacroParameter("outputRootName", str(properties.outputRootName)),
                MacroParameter("matchColumnName", str(properties.matchColumnName)),
                MacroParameter("errorIfNotMatched", str(properties.errorIfNotMatched).lower()),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        # Handle changes in the component's state and return the new state
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": field["name"], "dataType": field["dataType"]["type"]} for field in schema["fields"]]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name
        )
        return component.bindProperties(newProperties)

    def applyPython(self, spark: SparkSession, in0: DataFrame) -> DataFrame:
        selected_column = self.props.selectedColumnName
        regex_expression = self.props.regexExpression
        output_method = self.props.outputMethod
        case_insensitive = self.props.caseInsensitive
        replacement_text = self.props.replacementText
        copy_unmatched_text = self.props.copyUnmatchedText
        tokenize_output_method = self.props.tokenizeOutputMethod
        no_of_columns = self.props.noOfColumns
        allow_blank_tokens = self.props.allowBlankTokens
        output_root_name = self.props.outputRootName
        parse_columns = self.props.parseColumns
        match_column_name = self.props.matchColumnName
        error_if_not_matched = self.props.errorIfNotMatched
        extra_columns_handling = self.props.extraColumnsHandling

        regex_pattern = regex_expression
        if case_insensitive:
            regex_pattern = f"(?i){regex_expression}"

        result_df = in0
        val_if_not_found = None if allow_blank_tokens else lit("")

        if output_method == "replace":
            replaced_col = regexp_replace(col(selected_column), regex_pattern, replacement_text)
            if copy_unmatched_text:
                replaced_col = when(
                    col(selected_column).rlike(regex_pattern),
                    replaced_col
                ).otherwise(col(selected_column))

            result_df = result_df.withColumn(
                f"{selected_column}_replaced",
                replaced_col
            )

        elif output_method == "parse":
            if parse_columns and len(parse_columns) > 0:
                idx = 0
                for parse_col in parse_columns:
                    idx += 1
                    col_name = parse_col.columnName
                    col_type = parse_col.dataType

                    extracted = regexp_extract(col(selected_column), regex_pattern, idx)

                    if col_type.lower() == "int" or col_type.lower() == "integer":
                        extracted = when(extracted != "", extracted).otherwise(None).cast(IntegerType())
                    elif col_type.lower() == "bigint":
                        extracted = when(extracted != "", extracted).otherwise(None).cast(LongType())
                    elif col_type.lower() == "double" or col_type.lower() == "float":
                        extracted = when(extracted != "", extracted).otherwise(None).cast(DoubleType())
                    elif col_type.lower() == "bool" or col_type.lower() == "boolean":
                        extracted = when(extracted != "", extracted).otherwise(None).cast(BooleanType())
                    elif col_type.lower() == "date":
                        extracted = when(extracted != "", to_date(extracted)).otherwise(None)
                    elif col_type.lower() == "datetime" or col_type.lower() == "timestamp":
                        extracted = when(extracted != "", to_timestamp(extracted)).otherwise(None)
                    else:
                        val_if_not_found = lit("") if allow_blank_tokens else None
                        extracted = when(
                            (regexp_extract(col(selected_column), regex_pattern, 0) == "") |
                            (extracted == ""),
                            val_if_not_found
                        ).otherwise(extracted)

                    result_df = result_df.withColumn(col_name, extracted)

        elif output_method == "tokenize":
            if tokenize_output_method == "splitColumns":
                has_capture_groups = '(' in regex_expression

                if has_capture_groups:
                    for i in range(1, no_of_columns + 1):
                        extracted = regexp_extract(col(selected_column), regex_pattern, i)
                        if not allow_blank_tokens:
                            extracted = when(
                                (col(selected_column).rlike(regex_pattern)) & (extracted != ""),
                                extracted
                            ).otherwise(None)
                        else:
                            extracted = when(
                                col(selected_column).rlike(regex_pattern),
                                extracted
                            ).otherwise(lit(""))

                        result_df = result_df.withColumn(f"{output_root_name}{i}", extracted)
                else:
                    extracted_array = regexp_extract_all(col(selected_column), regex_pattern)
                    array_size = size(extracted_array)

                    extra_handling_lower = extra_columns_handling.lower() if extra_columns_handling else "dropextrawithoutwarning"

                    if extra_handling_lower == "saveallremainingtext":
                        val_for_empty = lit("") if allow_blank_tokens else None
                        for i in range(1, no_of_columns):
                            col_val = when(
                                array_size == 0,
                                None
                            ).when(
                                array_size < i,
                                val_for_empty
                            ).when(
                                extracted_array[i - 1] == "",
                                val_for_empty
                            ).otherwise(extracted_array[i - 1])

                            result_df = result_df.withColumn(f"{output_root_name}{i}", col_val)

                        last_col_val = when(
                            array_size == 0,
                            None
                        ).when(
                            array_size < no_of_columns,
                            val_for_empty
                        ).when(
                            array_size > no_of_columns,
                            concat_ws("", slice(extracted_array, no_of_columns + 1, array_size - no_of_columns))
                        ).when(
                            array_size == no_of_columns,
                            when(
                                extracted_array[no_of_columns - 1] == "",
                                val_if_not_found
                            ).otherwise(extracted_array[no_of_columns - 1])
                        ).otherwise(None)

                        result_df = result_df.withColumn(f"{output_root_name}{no_of_columns}", last_col_val)

                    elif extra_handling_lower == "dropextrawitherror":
                        val_for_empty = lit("") if allow_blank_tokens else None
                        for i in range(1, no_of_columns + 1):
                            col_val = when(
                                array_size > no_of_columns,
                                lit(f"ERROR: Found {array_size} regex matches, but only {no_of_columns} columns expected")
                            ).when(
                                array_size == 0,
                                None
                            ).when(
                                array_size < i,
                                val_for_empty
                            ).when(
                                extracted_array[i - 1] == "",
                                val_for_empty
                            ).otherwise(extracted_array[i - 1])

                            result_df = result_df.withColumn(f"{output_root_name}{i}", col_val)

                    else:
                        val_for_empty = lit("") if allow_blank_tokens else None
                        for i in range(1, no_of_columns + 1):
                            col_val = when(
                                array_size == 0,
                                None
                            ).when(
                                array_size < i,
                                val_for_empty
                            ).when(
                                extracted_array[i - 1] == "",
                                val_for_empty
                            ).otherwise(extracted_array[i - 1])

                            result_df = result_df.withColumn(f"{output_root_name}{i}", col_val)

            elif tokenize_output_method == "splitRows":
                all_columns = [col(c) for c in result_df.columns]
                extracted_array = regexp_extract_all(col(selected_column), lit(regex_pattern))
                result_df = result_df.withColumn("token_value_new", extracted_array)

                result_df = result_df.select(
                    *all_columns,
                    explode(col("token_value_new")).alias("token_value_new")
                )

                result_df = result_df.withColumnRenamed("token_value_new", output_root_name)
                if not allow_blank_tokens:
                    result_df = result_df.filter(
                        (col(output_root_name) != "") &
                        (col(output_root_name).isNotNull())
                    )

        elif output_method == "match":
            match_col = when(
                col(selected_column).isNull(),
                0
            ).when(
                col(selected_column).rlike(regex_pattern),
                1
            ).otherwise(0)

            result_df = result_df.withColumn(match_column_name, match_col)

            if error_if_not_matched:
                result_df = result_df.filter(col(selected_column).rlike(regex_pattern))

        return result_df

