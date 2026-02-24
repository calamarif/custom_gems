import dataclasses
import json
from abc import ABC
from dataclasses import dataclass, field
from typing import List

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class RuleField(ABC):
    pass


class BRE_SQL_Gem(MacroSpec):
    name: str = "BRE_SQL_Gem"
    projectName: str = "custom_gem_troubleshooting"
    category: str = "Transform"
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged,
    ]
    dependsOnUpstreamSchema: bool = True

    @dataclass(frozen=True)
    class AddRule(RuleField):
        input_column: str = ""
        output_column: str = ""
        rule_condition: str = ""
        rule_output_value: str = ""

    @dataclass(frozen=True)
    class BRE_SQL_GemProperties(MacroProperties):
        rules: List[RuleField] = field(default_factory=list)
        schema: str = ""
        relation_name: List[str] = field(default_factory=list)

    def get_relation_names(self, component: Component, context: SqlContext) -> List[str]:
        all_upstream_nodes = []
        for inputPort in component.ports.inputs:
            upstreamNode = None
            for connection in context.graph.connections:
                if connection.targetPort == inputPort.id:
                    upstreamNode = context.graph.nodes.get(connection.source)
            all_upstream_nodes.append(upstreamNode)

        relation_name = []
        for upstream_node in all_upstream_nodes:
            if upstream_node is None or upstream_node.label is None:
                relation_name.append("")
            else:
                relation_name.append(upstream_node.label)

        return relation_name

    def onButtonClick(self, state: Component):
        _rules = state.properties.rules
        _rules.append(self.AddRule())
        return state.bindProperties(
            dataclasses.replace(state.properties, rules=_rules)
        )

    def dialog(self) -> Dialog:
        rules_list = (
            StackLayout(gap="1rem", height="100%")
            .addElement(TitleElement("Business Rules"))
            .addElement(
                NativeText(
                    "Select an input column, enter the condition and output value, "
                    "then specify the output column (new or existing). "
                    "Multiple rules for the same output column are evaluated in order (CASE WHEN)."
                )
            )
            .addElement(
                OrderedList("Rules")
                .bindProperty("rules")
                .setEmptyContainerText("No rules yet — click 'Add Rule' to get started.")
                .addElement(
                    ColumnsLayout("1rem", alignY="end")
                    .addColumn(
                        SchemaColumnsDropdown("Input Column", appearance="minimal")
                        .bindSchema("component.ports.inputs[0].schema")
                        .bindProperty("record.AddRule.input_column")
                        .withSearchEnabled(),
                        "22%",
                    )
                    .addColumn(
                        TextBox("Condition (If...)", placeholder="e.g. > 100  or  LIKE 'A%'  or  IS NULL")
                        .bindProperty("record.AddRule.rule_condition"),
                        "28%",
                    )
                    .addColumn(
                        TextBox("Output Value (Then...)", placeholder="e.g. 'High'  or  999  or  'Unknown'")
                        .bindProperty("record.AddRule.rule_output_value"),
                        "28%",
                    )
                    .addColumn(
                        TextBox("Output Column", placeholder="New or existing column name")
                        .bindProperty("record.AddRule.output_column"),
                        "18%",
                    )
                    .addColumn(ListItemDelete("delete"), width="content")
                )
            )
            .addElement(SimpleButtonLayout("Add Rule", self.onButtonClick))
        )

        return Dialog("Business Rules Engine").addElement(
            ColumnsLayout(gap="1rem", height="100%")
            .addColumn(Ports(), "content")
            .addColumn(
                StackLayout(height="100%")
                .addElement(
                    StepContainer().addElement(
                        Step().addElement(rules_list)
                    )
                ),
                "5fr",
            )
        )

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(BRE_SQL_Gem, self).validate(context, component)
        props = component.properties

        if not props.rules:
            diagnostics.append(
                Diagnostic(
                    "component.properties.rules",
                    "Please add at least one business rule.",
                    SeverityLevelEnum.Error,
                )
            )
            return diagnostics

        for idx, rule in enumerate(props.rules):
            if not rule.output_column:
                diagnostics.append(
                    Diagnostic(
                        f"component.properties.rules[{idx}].output_column",
                        "Output column name is required.",
                        SeverityLevelEnum.Error,
                    )
                )
            if not rule.rule_condition:
                diagnostics.append(
                    Diagnostic(
                        f"component.properties.rules[{idx}].rule_condition",
                        "Condition is required.",
                        SeverityLevelEnum.Error,
                    )
                )
            if not rule.rule_output_value:
                diagnostics.append(
                    Diagnostic(
                        f"component.properties.rules[{idx}].rule_output_value",
                        "Output value is required.",
                        SeverityLevelEnum.Error,
                    )
                )

        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": f["name"], "dataType": f["dataType"]["type"]}
            for f in schema["fields"]
        ]
        relation_name = self.get_relation_names(newState, context)

        newProperties = dataclasses.replace(
            newState.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
        )
        return newState.bindProperties(newProperties)

    def apply(self, props: BRE_SQL_GemProperties) -> str:
        resolved_macro_name = f"{self.projectName}.{self.name}"

        rules_list = [
            {
                "input_column": r.input_column,
                "output_column": r.output_column,
                "rule_condition": r.rule_condition,
                "rule_output_value": r.rule_output_value,
            }
            for r in props.rules
        ]

        schema = props.schema if props.schema else "[]"
        arguments = [
            str(props.relation_name),
            schema,
            json.dumps(rules_list),
        ]
        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)

        rules = []
        try:
            for r in json.loads(parametersMap.get("rules", "[]")):
                rules.append(self.AddRule(
                    input_column=r.get("input_column", ""),
                    output_column=r.get("output_column", ""),
                    rule_condition=r.get("rule_condition", ""),
                    rule_output_value=r.get("rule_output_value", ""),
                ))
        except (json.JSONDecodeError, TypeError):
            rules = []

        return BRE_SQL_Gem.BRE_SQL_GemProperties(
            relation_name=json.loads(parametersMap.get("relation_name", "[]").replace("'", '"')),
            schema=parametersMap.get("schema", ""),
            rules=rules,
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                MacroParameter("rules", json.dumps([
                    {
                        "input_column": r.input_column,
                        "output_column": r.output_column,
                        "rule_condition": r.rule_condition,
                        "rule_output_value": r.rule_output_value,
                    }
                    for r in properties.rules
                ])),
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [
            {"name": f["name"], "dataType": f["dataType"]["type"]}
            for f in schema["fields"]
        ]
        relation_name = self.get_relation_names(component, context)

        newProperties = dataclasses.replace(
            component.properties,
            schema=json.dumps(fields_array),
            relation_name=relation_name,
        )
        return component.bindProperties(newProperties)
