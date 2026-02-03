# GEMINI.md

This file provides guidance to Gemini Code (gemini.ai/code) when working with code in this repository.

## Prompt Instruction:

I want you to create a custom Prophecy SQL gem called `BRE_SQL_Gem` - a Transform gem that allows creation of business rules. 

The business user will:
1) select an existing input column, 
2) either select and existing OUTPUT column or specify an new OUTPUT column that doesn't exist.
3) Define the logic for the business rule 

For example
1) 'Input_Column'
2) 'New_Output_Column'
3) Rule consists of input and output
    input = 'If Input_Column > 100' 
    output = New_Output_Column = 'this row is greater than 100'

This gem will consist of two files. 

## Key Files to create:

- **BRE_SQL_Gem.py**: The Prophecy gem definition with ComponentProperties, dialog UI, validation, and code generation
- **BRE_SQL_Gem.sql**: This file will define the logic of the case statement that will be built by the previous interface.

When creating the user interface it should be based on these two images, showing the same interface:
- test_gem/bre_screenshot_1.png
- test_gem/bre_screenshot_2.png

The inputs will be selectable by whichever input ports are available, the outputs will be completely free text.

This is the UI that will take user input that will eventually build the SQL (which will be a large case statement with jinja templating and be dbt-core compliant). Focus on the interface first, don't worry about getting the SQL perfect, as we will be iterating on the interface and I will be giving more specific instructions on this.  


## Reference Resources (Symlinked)
- **uispec.py**: UI specification reference (copied from ComponentBuilderPython/prophecy/cb/ui/uispec.py for convenience)

- **ComponentBuilderPython/**: Prophecy component builder framework
  - `prophecy/cb/ui/uispec.py` - UI element classes (Dialog, TextBox, Checkbox, etc.)
  - `prophecy/cb/server/base/ComponentBuilderBase.py` - Base classes (ComponentSpec, ComponentProperties, etc.)
  - `prophecy/cb/server/base/datatypes.py` - SInt, SString, SColumn types

SQL Gems need two files to be created. (1) DBT sql gem (examples in the "macros" folder) and (2) their corresponding "interface" files in the "gems" folder, see locations below:
- **snowflake-sql-basics-main/gems/**: Example gems (the interface)
- **snowflake-sql-basics-main/macros/**: Example gems (the sql)
    - Examples include: DataCleansing, DynamicSelect, FuzzyMatch, JSONParse, MultiColumnEdit,MultiColumnRename, TextToColumns, Transpose, UnionByName, XMLParse

## Gem Development Pattern

Prophecy gems (the interface python file) follows this structure:
```python
class MyGem(ComponentSpec):
    name: str = "MyGem"
    category: str = "Transform"  # or "Dataset", etc.

    @dataclass(frozen=True)
    class MyGemProperties(ComponentProperties):
        # Design-time configuration (use str for UI binding, convert in apply())
        my_setting: str = "default"
        my_flag: bool = True

    def dialog(self) -> Dialog:
        # UI layout using ColumnsLayout, StackLayout, TextBox, Checkbox, etc.

    def validate(self, context, component) -> List[Diagnostic]:
        # Return validation errors

    def onChange(self, context, oldState, newState) -> Component:
        # Handle state changes

    class MyGemCode(ComponentCode):
        def apply(self, spark, in0) -> DataFrame:
            # Generate Spark code using self.props.*
```

## Property Types

- Use `str` for numeric/text inputs (parse to int/float in apply())
- Use `bool` for checkboxes
- Use `SInt`/`SString`/`SColumn` only when Spark expression support is needed

## Current screenshots of the gem that we are trying to recreate:
- 'test_gem/bre_screenshot_1.png'
- 'test_gem/bre_screenshot_2.png'



## Reference Documentation

- https://docs.prophecy.io/engineers/gem-builder
- https://docs.prophecy.io/engineers/gem-builder-reference
- https://docs.prophecy.io/engineers/optimization-functions

## Useful Example Gems for UI Patterns (in the directory )

| Pattern | Example Gem |
|---------|-------------|
| Simple TextBox/NumberBox | `transform/Limit.py` |
| Checkbox + Conditional visibility | `transform/Repartition.py`, `transform/SampleRows.py` |
| RadioGroup with descriptions | `transform/Repartition.py` |
| FieldPicker with multiple options | `dataset/csv.py` |
| Validation with diagnostics | `transform/Limit.py` |

## Known Issues / Future Work

- **Output schema**: should be the input schema plus the output columns that are defined in the Gems UI. 

## Testing Workflow

Development uses copy-paste testing: copy gem code into Prophecy UI, test, collect feedback, iterate.
