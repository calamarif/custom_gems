# Prophecy SQL Gem Builder

Help the user create a new Custom Prophecy SQL gem. Follow these steps in order.

---

## Step 1 – Gather requirements

Ask the user:
1. What SQL transformation should the gem perform? (brief description)
2. What is the gem name? (PascalCase, e.g. `MyTransform`)
3. What Prophecy project will it live in? (the `projectName` value, e.g. `prophecy_basics`)
4. How many input ports? (usually 1)
5. What user inputs does the gem need? (e.g. columns to select, free-text fields, checkboxes, rule tables)

Do not proceed to generation until you have all five answers.

---

## Step 2 – Study the official examples BEFORE writing any code

Fetch these raw files from the official Prophecy examples repo and read them carefully:

**Python interface examples:**
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/gems/DataCleansing.py`
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/gems/MultiColumnEdit.py`

**SQL macro examples:**
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/macros/DataCleansing.sql`
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/macros/MultiColumnEdit.sql`

If the user's gem needs a UI pattern not covered by the above two, also fetch the relevant gem from this list:
- CountRecords, DataEncoderDecoder, DataMasking, DynamicSelect, FindDuplicates, FuzzyMatch,
  GenerateRows, JSONParse, MultiColumnRename, RecordID, Regex, Sample, TableOperations,
  TextToColumns, ToDo, Transpose, UnionByName, XMLParse

Use the URL pattern:
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/gems/<Name>.py`
- `https://raw.githubusercontent.com/prophecy-io/prophecy-basics/main/macros/<Name>.sql`

Do not write any code until you have read and understood the relevant examples.

---

## Step 3 – Generate the Python interface file (`<GemName>.py`)

Base the code on what you read in Step 2. The canonical structure is:

```python
import dataclasses
import json
from dataclasses import dataclass, field
from typing import List

from prophecy.cb.sql.MacroBuilderBase import *
from prophecy.cb.ui.uispec import *


class MyGem(MacroSpec):
    name: str = "MyGem"
    projectName: str = "prophecy_basics"   # confirm with user
    category: str = "Transform"            # or "Prepare", "Join", etc.
    minNumOfInputPorts: int = 1
    supportedProviderTypes: list[ProviderTypeEnum] = [
        ProviderTypeEnum.Databricks,
        ProviderTypeEnum.Snowflake,
        ProviderTypeEnum.BigQuery,
        ProviderTypeEnum.ProphecyManaged,
    ]
    dependsOnUpstreamSchema: bool = True   # required when gem reads input columns

    @dataclass(frozen=True)
    class MyGemProperties(MacroProperties):
        schema: str = ""
        relation_name: List[str] = field(default_factory=list)
        # Add your gem-specific properties here
        # Use List[dict] for table rows — NEVER a nested custom dataclass
        # Use List[str] for multi-column selectors
        # Use bool for checkboxes, str for text/select inputs

    def get_relation_names(self, component: Component, context: SqlContext):
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

    def dialog(self) -> Dialog:
        # See UI component cheat-sheet below
        ...

    def validate(self, context: SqlContext, component: Component) -> List[Diagnostic]:
        diagnostics = super(MyGem, self).validate(context, component)
        # Append Diagnostic(..., SeverityLevelEnum.Error) for each invalid state
        return diagnostics

    def onChange(self, context: SqlContext, oldState: Component, newState: Component) -> Component:
        schema = json.loads(str(newState.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": f["name"], "dataType": f["dataType"]["type"]} for f in schema["fields"]]
        relation_name = self.get_relation_names(newState, context)
        newProperties = dataclasses.replace(newState.properties, schema=json.dumps(fields_array), relation_name=relation_name)
        return newState.bindProperties(newProperties)

    def apply(self, props: MyGemProperties) -> str:
        resolved_macro_name = f"{self.projectName}.{self.name}"
        # Encode each argument as passed in the official examples
        # - relation_name: str(props.relation_name)
        # - schema: props.schema  (raw JSON string)
        # - str values: "'" + props.myStr + "'"
        # - bool values: str(props.myBool).lower()
        # - List[str] values: str(props.myList)
        # - List[dict] values: json.dumps(props.myList)
        arguments = [str(props.relation_name), props.schema]
        params = ",".join(arguments)
        return f"{{{{ {resolved_macro_name}({params}) }}}}"

    def loadProperties(self, properties: MacroProperties) -> PropertiesType:
        parametersMap = self.convertToParameterMap(properties.parameters)
        return MyGem.MyGemProperties(
            relation_name=json.loads(parametersMap.get("relation_name", "[]").replace("'", '"')),
            schema=parametersMap.get("schema", ""),
            # Decode each parameter using the same type it was encoded as in apply()
        )

    def unloadProperties(self, properties: PropertiesType) -> MacroProperties:
        return BasicMacroProperties(
            macroName=self.name,
            projectName=self.projectName,
            parameters=[
                MacroParameter("relation_name", json.dumps(properties.relation_name)),
                MacroParameter("schema", str(properties.schema)),
                # One MacroParameter per property
            ],
        )

    def updateInputPortSlug(self, component: Component, context: SqlContext):
        schema = json.loads(str(component.ports.inputs[0].schema).replace("'", '"'))
        fields_array = [{"name": f["name"], "dataType": f["dataType"]["type"]} for f in schema["fields"]]
        relation_name = self.get_relation_names(component, context)
        newProperties = dataclasses.replace(component.properties, schema=json.dumps(fields_array), relation_name=relation_name)
        return component.bindProperties(newProperties)
```

### UI component cheat-sheet

| Need | Component |
|------|-----------|
| Select one column from input | `SchemaColumnsDropdown("").bindSchema("component.ports.inputs[0].schema").bindProperty("col")` |
| Select multiple columns | `SchemaColumnsDropdown("", appearance="minimal").withMultipleSelection().bindSchema("component.ports.inputs[0].schema").bindProperty("cols")` |
| Free-text entry | `TextBox("Label", placeholder="hint").bindProperty("myStr")` |
| Number entry | `NumberBox("Label", placeholder="0").withMin(0).bindProperty("myNum")` |
| True/false toggle | `Checkbox("Label").bindProperty("myBool")` |
| Pick one from a list | `SelectBox("").addOption("Label", "value").bindProperty("mySelect")` |
| Show element only when condition met | `Condition().ifEqual(PropExpr("component.properties.myBool"), BooleanExpr(True)).then(<element>)` |
| Table of rows (add/remove) | `BasicTable("Title", columns=[Column("Header", "key", <widget>)]).bindProperty("myList")` |
| Column in a BasicTable | `Column("Header", "dict_key", SchemaColumnsDropdown("").bindSchema(...))` |
| Horizontal split | `ColumnsLayout(gap="1rem", height="100%").addColumn(..., "5fr")` |
| Vertical stack | `StackLayout(height="100%").addElement(...)` |
| Ports panel (always leftmost column) | `Ports()` — place via `.addColumn(Ports(), "content")` |
| Visual grouping | `StepContainer().addElement(Step().addElement(...))` |
| Section title | `TitleElement("Title")` |
| Static descriptive text | `NativeText("...")` |

**Layout rules:**
- Top-level layout is always `ColumnsLayout` with `Ports()` in the leftmost column
- Group related controls in `StepContainer > Step > StackLayout`
- Use `SchemaColumnsDropdown` (never `TextBox`) wherever the user selects column names
- Use `Condition()` to hide/show fields that only apply when a checkbox is ticked
- Use `BasicTable` for any repeating row structure; bind it to a `List[dict]` property

---

## Step 4 – Generate the SQL macro file (`<GemName>.sql`)

SQL macros in this project use **dbt adapter dispatch** for multi-dialect support. The structure is always:

```sql
{% macro MyGem(relation_name, schema, my_param='default') -%}
    {{ return(adapter.dispatch('MyGem', 'prophecy_basics')(relation_name, schema, my_param)) }}
{% endmacro %}

{%- macro default__MyGem(relation_name, schema, my_param='default') -%}
    {# Normalise relation_name to a list #}
    {% set rel_list = relation_name
        if (relation_name is iterable and relation_name is not string)
        else [relation_name] %}

    {# Build your SELECT here #}
    select
        ...
    from {{ rel_list | join(', ') }}
{%- endmacro -%}

{%- macro snowflake__MyGem(relation_name, schema, my_param='default') -%}
    {# Snowflake-specific version — use double-quote identifiers, :: casting #}
    ...
{%- endmacro -%}

{%- macro duckdb__MyGem(relation_name, schema, my_param='default') -%}
    {# DuckDB-specific version — use prophecy_basics.quote_identifier() #}
    ...
{%- endmacro -%}
```

**Rules for the SQL macro:**
- Always include all three dialect variants (`default__`, `snowflake__`, `duckdb__`)
- Must be dbt-core compliant Jinja2 — no non-standard filters
- `relation_name` arrives as a Python list-string; always normalise to a proper list first
- `schema` arrives as a JSON array of `{name, dataType}` dicts
- Build the SELECT column list as a Jinja2 list, then `{{ cols | join(',\n    ') }}`
- Use `{% do list.append(...) %}` to accumulate expressions
- Study the fetched examples carefully for the exact quoting/casting style per dialect

---

## Step 5 – Output

1. Confirm the final gem name and `projectName` with the user before writing files
2. Write `<GemName>.py` using the Write tool
3. Write `<GemName>.sql` using the Write tool
4. After writing, remind the user of the testing workflow: copy each file's content into the Prophecy gem builder UI to test, then iterate
