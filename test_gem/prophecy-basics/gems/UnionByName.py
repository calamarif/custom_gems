import dataclasses
import json

from prophecy.cb.server.base.ComponentBuilderBase import *
from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import *
from pyspark.sql.functions import *


class UnionByName(MacroSpec):
    name: str = "UnionByName"
    projectName: str = "prophecy_basics"
    category: str = "Join/Split"
    minNumOfInputPorts: int = 2
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class UnionByNameProperties(MacroProperties):
        relation_name: List[str] = field(
            default_factory=list
        )  # labels of upstream nodes
        schemas: List[str] = field(default_factory=list)  # JSON strings, one per port
        missingColumnOps: str = "allowMissingColumns"

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
            .addColumn(Ports(allowInputAddOrDelete=True), "content")
            .addColumn(
                StackLayout().addElement(
                    RadioGroup("")
                    .addOption(
                        "Union By Name (No Missing Column)",
                        "nameBasedUnionOperation",
                        ("UnionAll"),
                        ("Union of DataFrames with identical column sets"),
                    )
                    .addOption(
                        "Union By Name (Allow Missing Columns)",
                        "allowMissingColumns",
                        ("UnionAll"),
                        ("Aligns by name; fills missing columns with NULLs"),
                    )
                    .setOptionType("button")
                    .setVariant("large")
                    .setButtonStyle("solid")
                    .bindProperty("missingColumnOps")
                )
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(UnionByName, self).validate(context, component)
        return diagnostics

    def _extract_schemas(self, component: Component):
        """Return list[str] – one compact JSON blob per input port."""
        schema_blobs = []
        for in_port in component.ports.inputs:
            raw_schema = json.loads(str(in_port.schema).replace("'", '"'))
            fields_arr = [
                {"name": f["name"], "dataType": f["dataType"]["type"]}
                for f in raw_schema["fields"]
            ]
            schema_blobs.append(json.dumps(fields_arr))
        return schema_blobs

    def onChange(self, context: SqlContext, oldState: Component, newState: Component):
        new_props = dataclasses.replace(
            newState.properties,
            relation_name=self.get_relation_names(newState, context),
            schemas=self._extract_schemas(newState),
        )
        return newState.bindProperties(new_props)

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(UnionByName, self).validate(context, component)
        return diagnostics

    def apply(self, props: UnionByNameProperties) -> str:
        resolved_macro_name = f"{self.projectName}.{self.name}"

        #   argument #1 – ALL table names in one comma-sep string  (macro can handle str or list)
        relation_arg = str(props.relation_name)

        #   argument #2 – JSON list of all schema blobs
        schemas_arg = str(props.schemas)

        call = f"{{{{ {resolved_macro_name}({relation_arg}, {schemas_arg}, '{props.missingColumnOps}') }}}}"
        return call

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        pm = self.convertToParameterMap(properties.parameters)
        return UnionByName.UnionByNameProperties(
            relation_name=json.loads(pm.get("relation_name", "[]").replace("'", '"')),
            schemas=[str(x) for x in json.loads(pm.get("schemas", "[]").replace("'", ''))],
            missingColumnOps=pm.get("missingColumnOps", "nameBasedUnionOperation").lstrip("'").rstrip("'"),
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schemas", json.dumps(properties.schemas)),
                MacroParameter("missingColumnOps", properties.missingColumnOps),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        new_props = dataclasses.replace(
            component.properties,
            relation_name=self.get_relation_names(component, context),
            schemas=self._extract_schemas(component),
        )
        return component.bindProperties(new_props)

    def applyPython(self, spark: SparkSession, in0: DataFrame, in1: DataFrame, *inDFs: DataFrame) -> DataFrame:
        _inputs = [in0, in1]
        _inputs.extend(inDFs)

        nonEmptyDf: SubstituteDisabled = [x for x in _inputs if x is not None]
        res: SubstituteDisabled = nonEmptyDf[0]
        rest: SubstituteDisabled = nonEmptyDf[1:]

        if self.props.missingColumnOps == "allowMissingColumns":
            for inDF in rest:
                res = res.unionByName(inDF, allowMissingColumns=True)
        else:
            for inDF in rest:
                res = res.unionByName(inDF)
        return res
