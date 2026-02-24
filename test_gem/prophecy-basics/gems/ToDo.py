import dataclasses

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *
from pyspark.sql import *
from pyspark.sql.functions import *


class ToDo(MacroSpec):
    name: str = "ToDo"
    projectName: str = "prophecy_basics"
    category: str = "Custom"
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        # ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged
    ]
    dependsOnUpstreamSchema: bool = False

    @dataclass(frozen=True)
    class ToDoProperties(MacroProperties):
        relation_name: List[str] = field(default_factory=list)
        error_string: Optional[str] = None
        code_string: Optional[str] = None
        diag_message: Optional[str] = None

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
        return Dialog("ToDo").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(
                Ports(allowInputAddOrDelete=True, allowCustomOutputSchema=True),
                "content",
            )
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout(height="100%")
                            .addElement(TitleElement("Highlight message"))
                            .addElement(
                                TextBox("")
                                .bindPlaceholder(
                                    "To-Do logic not implemented yet. Please complete this feature."
                                )
                                .bindProperty("diag_message")
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout()
                            .addElement(TitleElement("Error message (Optional)"))
                            .addElement(
                                TextBox("")
                                .bindPlaceholder(
                                    "Please enter error message here for reference."
                                )
                                .bindProperty("error_string")
                            )
                        )
                    )
                )
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(
                            StackLayout()
                            .addElement(TitleElement("Helper code/text (Optional)"))
                            .addElement(
                                TextArea("", 12)
                                .bindPlaceholder(
                                    "Paste sample code or helpful notes here for reference."
                                )
                                .bindProperty("code_string")
                            )
                        )
                    )
                )
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super().validate(context, component)
        if (
            component.properties.diag_message is not None
            and component.properties.diag_message != ""
        ):
            diagnostics.append(
                Diagnostic(
                    "component.properties.diag_message",
                    component.properties.diag_message,
                    SeverityLevelEnum.Error,
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "component.properties.diag_message",
                    "Highlight message field cannot be empty.",
                    SeverityLevelEnum.Error,
                )
            )
        return diagnostics

    def onChange(
        self, context: SqlContext, oldState: Component, newState: Component
    ) -> Component:
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties, relation_name=relation_name
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: ToDoProperties) -> str:
        resolved_macro_name = f"{self.projectName}.{self.name}"
        diagMessage: str = (
            props.diag_message
            if props.diag_message is not None
            else "No diaganostic provided."
        )
        arguments = ["'" + diagMessage + "'"]

        params = ",".join([param for param in arguments])
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        # Load the component's state given default macro property representation
        parametersMap = self.convertToParameterMap(properties.parameters)
        return ToDo.ToDoProperties(diag_message=parametersMap.get("diag_message"))

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        # Convert component's state to default macro property representation
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[MacroParameter("diag_message", properties.diag_message)],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties, relation_name=relation_name
        )
        return component.bindProperties(newProperties)

    def applyPython(self, spark: SparkSession, *inDFs: DataFrame) -> DataFrame:
        message = self.props.diag_message
        if message is not None:
            raise Exception(f"ToDo: {message}")
        return spark.sql("select 1")
