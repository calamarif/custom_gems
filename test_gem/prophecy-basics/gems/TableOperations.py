from dataclasses import dataclass
from collections import defaultdict
from prophecy.cb.sql.Component import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import SparkSession, DataFrame

@dataclass(frozen=True)
class StringColName:
    colName: str

class TableOperations(MacroSpec):
    name: str = "TableOperations"
    projectName: str = "prophecy_basics"
    category: str = "Custom"
    minNumOfInputPorts: int = 0
    maxNumOfInputPorts: int = 0
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        # ProviderTypeEnum.BigQuery,
        # ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class TableOperationsProperties(MacroProperties):
        # Common properties
        relation_name: List[str] = field(default_factory=list)
        database: Optional[str] = ""
        tableName: Optional[str] = ""
        catalog: Optional[str] = ""
        isCatalogEnabled: Optional[bool] = True
        useExternalFilePath: Optional[bool] = False
        path: str = ""
        action: Optional[str] = "optimiseTable"

        # Vacuum properties
        vaccumRetainNumHours: str = "168"  # 7 days default

        # Optimize properties
        useOptimiseWhere: Optional[bool] = False
        optimiseWhere: Optional[str] = None
        useOptimiseZOrder: Optional[bool] = False
        optimiseZOrderColumns: List[StringColName] = field(default_factory=list)
        optimize_zorder_columns: List[str] = field(default_factory=list)

        # Restore properties
        restoreVia: Optional[str] = ""
        restoreValue: Optional[str] = ""

        # Update properties
        updateSetClause: str = ""
        updateCondition: str = ""

        # Delete Properties
        deleteCondition: str = ""

        # Run DDL properties
        runDDL: str = ""

    def dialog(self) -> Dialog:
        # Operation selector
        operation_selector = (
            ColumnsLayout(gap=("1rem"))
            .addColumn(
                SelectBox("Action")
                .addOption("Register table in catalog", "registerTableInCatalog")
                .addOption("Vacuum table", "vacuumTable")
                .addOption("Optimise table", "optimiseTable")
                .addOption("Restore table", "restoreTable")
                .addOption("Update table", "updateTable")
                .addOption("Delete from table", "deleteFromTable")
                .addOption("Drop table", "dropTable")
                .addOption("FSCK Repair table", "fsckRepairTable")
                .addOption("Run DDL", "runDDL")
                .bindProperty("action")
            )
        )

        # FSCK repair UI
        fsck_repair_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "Removes the file entries from the transaction log of a Delta table that can no longer be found in the underlying file system. This can happen when these files have been manually deleted."
                )
            )
        )

        # Vacuum table UI
        vacuum_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "Recursively vacuum directories associated with the Delta table. VACUUM removes all files from the"
                    + " table directory that are not managed by Delta, as well as data files that are no longer in the"
                    + " latest state of the transaction log for the table and are older than a retention threshold. The"
                    + " default threshold is 7 days."
                )
            )
            .addElement(
                TextBox("Retention Hours (Optional)")
                .bindPlaceholder("168")
                .bindProperty("vaccumRetainNumHours")
            )
        )

        # Optimize table UI
        optimize_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "Optimizes the layout of Delta Lake data. Optionally optimize a subset of data or colocate"
                    + " data by column. If colocation is not specified, bin-packing optimization is performed by default. "
                )
            )
            .addElement(                
                StackLayout()
                    .addElement(
                        Checkbox("Use where clause").bindProperty("useOptimiseWhere")
                    )
                    .addElement(
                        Checkbox("Use ZOrder").bindProperty("useOptimiseZOrder")
                    )
            )
            .addElement(
                Condition()
                    .ifEqual(
                    PropExpr("component.properties.useOptimiseWhere"),
                    BooleanExpr(True),
                ).then(
                    StackLayout()
                    .addElement(
                        AlertBox(
                            variant="success",
                            _children=[
                                Markdown(
                                    "**In Select Expression, you can choose value, custom code etc. to create the expression** \n\n"
                                    "* **Example**: date >= \"2025-06-25\" (Put it as value) \n\n"
                                    "* **Example**: date >= \"2025-06-25\" (Put it as custom code)"
                                )
                            ],
                        )
                    )
                    .addElement(
                        ExpressionBox(language="sql")
                        .bindProperty("optimiseWhere")
                        .bindPlaceholder(
                            "Write sql expression eg: date >= '2024-01-01'"
                        )
                        .withGroupBuilder(GroupBuilderType.EXPRESSION)
                        .withUnsupportedExpressionBuilderTypes(
                            [ExpressionBuilderType.INCREMENTAL_EXPRESSION]
                        )
                    )                        
                )
            )
            .addElement(
                Condition()
                    .ifEqual(
                    PropExpr("component.properties.useOptimiseZOrder"),
                    BooleanExpr(True),
                ).then(
                        BasicTable(
                            "ZOrder Columns",
                            height=("200px"),
                            columns=[
                                Column(
                                    "ZOrder Columns",
                                    "colName",
                                    (TextBox("").bindPlaceholder("col_name")),
                                )
                            ],
                            targetColumnKey="colName",
                        ).bindProperty("optimiseZOrderColumns")                   
                )                
            )
        )

        # Delete table UI
        delete_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "Delete removes the data from the latest version of the Delta table as per the condition"
                    + " specified below. Please note that delete does not remove it from the physical storage"
                    + " until the older versions are explicitly vacuumed."
                    + " Please specify the where clause"
                )
            )
            .addElement(
                AlertBox(
                    variant="success",
                    _children=[
                        Markdown(
                            "**In Select Expression, you can choose value, custom code etc. to create the expression** \n\n"
                            "* **Example**: date >= \"2025-06-25\" (Put it as value) \n\n"
                            "* **Example**: date >= \"2025-06-25\" (Put it as custom code)"
                        )
                    ],
                )
            )
            .addElement(
                ExpressionBox(language="sql")
                .bindProperty("deleteCondition")
                .bindPlaceholder(
                    "Write sql expression eg: date >= '2024-01-01'"
                )
                .withGroupBuilder(GroupBuilderType.EXPRESSION)
                .withUnsupportedExpressionBuilderTypes(
                    [ExpressionBuilderType.INCREMENTAL_EXPRESSION]
                )
            )
        )

        # Drop table UI
        drop_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "This will drop the table from catalog and remove the files."
                )
            )
        )

        # Restore table UI
        restore_table_ui = (
            StackItem(grow=(1))
            .addElement(
                NativeText(
                    "Restores a Delta table to an earlier state. Restoring to an earlier version number or a"
                    + " timestamp is supported."
                )
            )
            .addElement(
                SelectBox("Restore via")
                .addOption("Timestamp", "restoreViaTimestamp")
                .addOption("Version", "restoreViaVersion")
                .bindProperty("restoreVia")
            )
            .addElement(
                TextBox("Value").bindPlaceholder("Timestamp format YYYY-MM-DD HH:MM:SS (e.g., 2025-11-23 00:00:00) or Version number").bindProperty("restoreValue")
            )
        )

        # Update table UI
        update_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(TitleElement("Update Configuration"))
            .addElement(
                TextArea("SET Clause", rows=3)
                .bindPlaceholder("column1 = value1, column2 = value2")
                .bindProperty("updateSetClause")
            )
            .addElement(
                NativeText("WHERE Clause")
            )
            .addElement(
                AlertBox(
                    variant="success",
                    _children=[
                        Markdown(
                            "**In Select Expression, you can choose value, custom code etc. to create the expression** \n\n"
                            "* **Example**: date >= \"2025-06-25\" (Put it as value) \n\n"
                            "* **Example**: date >= \"2025-06-25\" (Put it as custom code)"
                        )
                    ],
                )
            )
            .addElement(
                ExpressionBox(language="sql")
                .bindProperty("updateCondition")
                .bindPlaceholder(
                    "Write sql expression eg: date >= '2024-01-01'"
                )
                .withGroupBuilder(GroupBuilderType.EXPRESSION)
                .withUnsupportedExpressionBuilderTypes(
                    [ExpressionBuilderType.INCREMENTAL_EXPRESSION]
                )
            )
        )

        # Register table UI
        register_table_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                NativeText(
                    "This will register the data at mentioned file path as a table in catalog."
                )
            )
        )

        # Run DDL UI
        run_ddl_ui = (
            StackLayout(gap="1rem", height="100%", direction="vertical")
            .addElement(
                TextArea(
                    "",
                    6,
                    placeholder="use {table_name} as a placeholder for the name of the table or mention the complete table name."
                    + "\n\n"
                    + "Example 1: alter table {table_name} ADD COLUMNS (col1 STRING COMMENT 'New column for notes',col2 TIMESTAMP)"
                    + "\n"
                    + "Example 2: alter table test_catalog.test_schema.test_table ADD COLUMNS (col1 STRING COMMENT 'New column for notes',col2 TIMESTAMP)"
                ).bindProperty("runDDL")
            )
        )

        # Build the dialog
        dialog = Dialog("delta_operations_dialog").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                Ports(allowInputAddOrDelete=True),
                "content"
            )
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(
                        Step()
                        .addElement(
                            Condition()
                            .ifEqual(
                                PropExpr("component.properties.useExternalFilePath"),
                                BooleanExpr(True),
                            )
                            .then(
                                TextBox(
                                    "File location", placeholder="dbfs:/FileStore/delta/tableName"
                                ).bindProperty("path")
                            )
                        )
                        .addElement(Checkbox("Use File Path").bindProperty("useExternalFilePath"))
                        .addElement(
                            CatalogTableDB("").bindProperty("database").bindTableProperty("tableName").bindCatalogProperty(
                                "catalog").bindIsCatalogEnabledProperty("isCatalogEnabled")
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(operation_selector)
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            Condition()
                            .ifEqual(PropExpr("component.properties.action"), StringExpr("registerTableInCatalog"))
                            .then(register_table_ui)
                            .otherwise(
                                Condition()
                                .ifEqual(PropExpr("component.properties.action"), StringExpr("vacuumTable"))
                                .then(vacuum_table_ui)
                                .otherwise(
                                    Condition()
                                    .ifEqual(PropExpr("component.properties.action"), StringExpr("optimiseTable"))
                                    .then(optimize_table_ui)
                                    .otherwise(
                                        Condition()
                                        .ifEqual(PropExpr("component.properties.action"), StringExpr("restoreTable"))
                                        .then(restore_table_ui)
                                        .otherwise(
                                            Condition()
                                            .ifEqual(PropExpr("component.properties.action"), StringExpr("updateTable"))
                                            .then(update_table_ui)
                                            .otherwise(
                                                Condition()
                                                .ifEqual(PropExpr("component.properties.action"), StringExpr("deleteFromTable"))
                                                .then(delete_table_ui)
                                                .otherwise(
                                                    Condition()
                                                    .ifEqual(PropExpr("component.properties.action"), StringExpr("dropTable"))
                                                    .then(drop_table_ui)
                                                    .otherwise(
                                                        Condition()
                                                        .ifEqual(PropExpr("component.properties.action"), StringExpr("fsckRepairTable"))
                                                        .then(fsck_repair_ui)
                                                        .otherwise(run_ddl_ui)
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
        return dialog

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:

        diagnostics = []

        if isBlank(component.properties.database) and isBlank(component.properties.path):
            diagnostics.append(
                Diagnostic("properties.database", "Both file path and database & table cannot be empty ",
                           SeverityLevelEnum.Error))

        if component.properties.action in ["registerTableInCatalog", "optimiseTable", "fsckRepairTable"]:
            if component.properties.isCatalogEnabled and (len(component.properties.catalog) == 0):
                diagnostics.append(
                    Diagnostic("properties.catalog", "Catalog Name cannot be empty", SeverityLevelEnum.Error))

            if len(component.properties.database) == 0:
                diagnostics.append(
                    Diagnostic("properties.database", "Database Name cannot be empty", SeverityLevelEnum.Error))

            if len(component.properties.tableName) == 0:
                diagnostics.append(
                    Diagnostic("properties.tableName", "Table Name cannot be empty", SeverityLevelEnum.Error))

        if component.properties.useExternalFilePath and isBlank(component.properties.path):
            if component.properties.action == "registerTableInCatalog":
                diagnostics.append(
                    Diagnostic(f"properties.useExternalFilePath", "File path cannot be empty", SeverityLevelEnum.Error))

        if component.properties.action == "deleteFromTable":
            if isBlank(component.properties.deleteCondition):
                diagnostics.append(
                    Diagnostic(f"properties.deleteCondition", "Delete condition cannot be empty", SeverityLevelEnum.Error))

        if component.properties.useOptimiseWhere:
            if isBlank(component.properties.optimiseWhere):
                diagnostics.append(
                    Diagnostic(f"properties.optimiseWhere", "Where condition cannot be blank", SeverityLevelEnum.Error))

        if component.properties.action == "vacuumTable":
            if isBlank(component.properties.vaccumRetainNumHours):
                diagnostics.append(
                    Diagnostic(f"properties.vaccumRetainNumHours", "Retention hours cannot be blank", SeverityLevelEnum.Error))

            if int(component.properties.vaccumRetainNumHours) < 168 :
                diagnostics.append(
                    Diagnostic(f"properties.vaccumRetainNumHours", "Retention hours should be equal to or greater than 168", SeverityLevelEnum.Error))

        if component.properties.useOptimiseZOrder:
            if len(component.properties.optimiseZOrderColumns) == 0:
                diagnostics.append(
                    Diagnostic(f"properties.optimiseZOrderColumns", "Please provide at least one column to ZOrder by",
                               SeverityLevelEnum.Error))

        if component.properties.action == "updateTable":
            if len(component.properties.updateCondition) == 0:
                diagnostics.append(
                    Diagnostic(f"properties.updateCondition", "Update without where clause will update all rows",
                               SeverityLevelEnum.Warning))

        if component.properties.action == "restoreTable":
            if component.properties.restoreVia == "restoreViaTimestamp" and isBlank(component.properties.restoreValue):
                diagnostics.append(
                    Diagnostic(f"properties.restoreValue", "Restore value cannot be blank", SeverityLevelEnum.Error))
            if component.properties.restoreVia == "restoreViaTimestamp" and not isBlank(component.properties.restoreValue):
                # Validate timestamp format YYYY-MM-DD HH:MM:SS
                from datetime import datetime
                try:
                    datetime.strptime(component.properties.restoreValue.strip(), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    diagnostics.append(
                        Diagnostic(f"properties.restoreValue", "Restore value must be in format YYYY-MM-DD HH:MM:SS (e.g., 2025-11-23 00:00:00)", SeverityLevelEnum.Error))
            if component.properties.restoreVia == "restoreViaVersion" and isBlank(component.properties.restoreValue):
                diagnostics.append(
                    Diagnostic(f"properties.restoreValue", "Restore value cannot be blank", SeverityLevelEnum.Error))
            if component.properties.restoreVia == "restoreViaVersion" and not isBlank(component.properties.restoreValue):
                # Validate version is a positive integer
                try:
                    version = int(component.properties.restoreValue.strip())
                    if version <= 0:
                        diagnostics.append(
                            Diagnostic(f"properties.restoreValue", "Restore version must be greater than 0", SeverityLevelEnum.Error))
                except ValueError:
                    diagnostics.append(
                        Diagnostic(f"properties.restoreValue", "Restore version must be a valid integer", SeverityLevelEnum.Error))


        if component.properties.action == "runDDL":
            if isBlank(component.properties.runDDL):
                diagnostics.append(
                    Diagnostic(f"component.properties.runDDL", "Please provide a ddl query to run",
                               SeverityLevelEnum.Error))
        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        # Handle changes in the component's state and return the new state
        return newState

    def apply(self, props: TableOperationsProperties) -> str:
        # generate the actual macro call given the component's state
        resolved_macro_name = f"{self.projectName}.{self.name}"

        # Helper function to safely convert values to strings and escape quotes
        def safe_str_escape(value):
            if value is None:
                return ""
            return str(value).replace("'", "\\'")

        # Extract column names from optimiseZOrderColumns
        zorder_columns = ",".join([col.colName for col in props.optimiseZOrderColumns]) if props.optimiseZOrderColumns else ""
        
        arguments = [
            f"'{safe_str_escape(props.catalog)}'",            
            f"'{safe_str_escape(props.database)}'",
            f"'{safe_str_escape(props.tableName)}'",
            f"'{safe_str_escape(props.action)}'",
            f"'{safe_str_escape(props.path)}'",
            f"{str(props.useExternalFilePath).lower()}",
            f"'{safe_str_escape(props.vaccumRetainNumHours)}'",
            f"{str(props.useOptimiseWhere).lower()}",
            f"'{safe_str_escape(props.optimiseWhere)}'",
            f"{str(props.useOptimiseZOrder).lower()}",
            f"'{zorder_columns}'",
            f"'{safe_str_escape(props.restoreVia)}'",
            f"'{safe_str_escape(props.restoreValue)}'",
            f"'{safe_str_escape(props.deleteCondition)}'",
            f"'{safe_str_escape(props.updateSetClause)}'",
            f"'{safe_str_escape(props.updateCondition)}'",
            f"'{safe_str_escape(props.runDDL)}'"
        ]

        params = ", ".join(arguments)
        return f'{{{{ {resolved_macro_name}({params}) }}}}'

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        
        # Convert optimiseZOrderColumns from comma-separated string to List[StringColName]
        zorder_cols_str = parametersMap.get("optimiseZOrderColumns", "").lstrip("'").rstrip("'").strip()
        optimiseZOrderColumns = []
        if zorder_cols_str:
            optimiseZOrderColumns = [
                StringColName(colName=col.strip()) 
                for col in zorder_cols_str.split(",") if col.strip()
            ]
        
        return TableOperations.TableOperationsProperties(
            catalog=parametersMap.get("catalog", "").lstrip("'").rstrip("'"),
            database=parametersMap.get("database", "").lstrip("'").rstrip("'"),
            tableName=parametersMap.get("tableName", "").lstrip("'").rstrip("'"),
            action=parametersMap.get("action", "").lstrip("'").rstrip("'"),
            path=parametersMap.get("path", "").lstrip("'").rstrip("'"),
            useExternalFilePath=parametersMap.get("useExternalFilePath", "false").lower() == "true",
            vaccumRetainNumHours=parametersMap.get("vaccumRetainNumHours", "").lstrip("'").rstrip("'"),
            useOptimiseWhere=parametersMap.get("useOptimiseWhere", "false").lower() == "true",
            optimiseWhere=parametersMap.get("optimiseWhere", "").lstrip("'").rstrip("'"),
            useOptimiseZOrder=parametersMap.get("useOptimiseZOrder", "false").lower() == "true",
            optimiseZOrderColumns=optimiseZOrderColumns,
            restoreVia=parametersMap.get("restoreVia", "").lstrip("'").rstrip("'"),
            restoreValue=parametersMap.get("restoreValue", "").lstrip("'").rstrip("'"),
            deleteCondition=parametersMap.get("deleteCondition", "").lstrip("'").rstrip("'"),
            updateSetClause=parametersMap.get("updateSetClause", "").lstrip("'").rstrip("'"),
            updateCondition=parametersMap.get("updateCondition", "").lstrip("'").rstrip("'"),
            runDDL=parametersMap.get("runDDL", "").lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # convert component's state to default macro property representation
        # Convert optimiseZOrderColumns from List[StringColName] to comma-separated string
        zorder_columns = ",".join([col.colName for col in properties.optimiseZOrderColumns]) if properties.optimiseZOrderColumns else ""
        
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("catalog", str(properties.catalog)),
                MacroParameter("database", str(properties.database)),
                MacroParameter("tableName", str(properties.tableName)),
                MacroParameter("action", str(properties.action)),
                MacroParameter("path", str(properties.path)),
                MacroParameter("useExternalFilePath", str(properties.useExternalFilePath).lower()),
                MacroParameter("vaccumRetainNumHours", str(properties.vaccumRetainNumHours)),
                MacroParameter("useOptimiseWhere", str(properties.useOptimiseWhere).lower()),
                MacroParameter("optimiseWhere", str(properties.optimiseWhere)),
                MacroParameter("useOptimiseZOrder", str(properties.useOptimiseZOrder).lower()),
                MacroParameter("optimiseZOrderColumns", zorder_columns),
                MacroParameter("restoreVia", str(properties.restoreVia)),
                MacroParameter("restoreValue", str(properties.restoreValue)),
                MacroParameter("deleteCondition", str(properties.deleteCondition)),
                MacroParameter("updateSetClause", str(properties.updateSetClause)),
                MacroParameter("updateCondition", str(properties.updateCondition)),
                MacroParameter("runDDL", str(properties.runDDL)),
            ],
        )
    def applyPython(self, spark: SparkSession) -> DataFrame:
        return_str: str = ""
        if not ("SColumnExpression" in locals()):
            try:
                from delta.tables import DeltaTable
                table_name = f"`{self.props.catalog}`.`{self.props.database}`.`{self.props.tableName}`" if self.props.isCatalogEnabled else f"`{self.props.database}`.`{self.props.tableName}`"

                if self.props.useExternalFilePath:
                    deltaTable = DeltaTable.forPath(
                        spark, self.props.path
                    )  # path-based tables
                else:
                    deltaTable = DeltaTable.forName(
                        spark, table_name
                    )  # Catalog based tables

                # Register Table In Catalog
                if self.props.action == "registerTableInCatalog":
                    spark.sql(
                        "CREATE TABLE "
                        + table_name
                        + " USING DELTA LOCATION '"
                        + self.props.path
                        + "'"
                    )

                elif self.props.action == "vacuumTable":
                    if isBlank(self.props.vaccumRetainNumHours):
                        deltaTable.vacuum()
                    else:
                        deltaTable.vacuum(
                            retentionHours=float(self.props.vaccumRetainNumHours)
                        )

                elif self.props.action == "optimiseTable":
                    zorderstr = ",".join(
                        [x.colName for x in self.props.optimiseZOrderColumns]
                    )
                    if (
                            not self.props.useOptimiseWhere
                            and not self.props.useOptimiseZOrder
                    ):
                        spark.sql(f"OPTIMIZE " + table_name)
                    elif not self.props.useOptimiseZOrder:
                        spark.sql(f"OPTIMIZE " + table_name + f" WHERE {self.props.optimiseWhere}")
                    elif not self.props.useOptimiseWhere:
                        spark.sql(f"OPTIMIZE " + table_name + f" ZORDER BY {zorderstr}")
                    else:
                        spark.sql(f"OPTIMIZE " + table_name + f" WHERE {self.props.optimiseWhere} ZORDER BY {zorderstr}")
                elif self.props.action == "restoreTable":
                    if self.props.restoreVia == "restoreViaVersion":
                        deltaTable.restoreToVersion(int(self.props.restoreValue))
                    elif self.props.restoreVia == "restoreViaTimestamp":
                        deltaTable.restoreToTimestamp(self.props.restoreValue)

                elif self.props.action == "deleteFromTable":
                    spark.sql(
                        "DELETE FROM " + table_name + " WHERE " + self.props.deleteCondition
                    )

                elif self.props.action == "dropTable":
                    spark.sql(
                        "DROP TABLE " + table_name
                    )
                elif self.props.action == "fsckRepairTable":
                    if not isBlank(self.props.database) and not isBlank(
                            self.props.tableName
                    ):
                        spark.sql(
                            "FSCK REPAIR TABLE " + table_name
                        )                          

                elif self.props.action == 'updateTable':
                    update_cmd = f"UPDATE {table_name} SET {self.props.updateSetClause}"
                    
                    if self.props.updateCondition.strip() != '':
                        update_cmd += f" WHERE {self.props.updateCondition}"
                    
                    spark.sql(update_cmd)
                    
                elif self.props.action == "runDDL":
                    spark.sql(self.props.runDDL.replace('{table_name}',table_name).strip())
                
                return_str:str = f"select '{self.props.action}' as action, '{table_name}' as table_name, 'Success' as status, current_timestamp() as executed_at"
            except Exception as ex:
                raise ex
        
        if return_str != "":
            return spark.sql(return_str)
        else:
            return spark.sql(f"select '{self.props.action}' as action, '`{self.props.catalog}`.`{self.props.database}`.`{self.props.tableName}`' as table_name, 'Schema Analysis Failed' as status, current_timestamp() as executed_at")