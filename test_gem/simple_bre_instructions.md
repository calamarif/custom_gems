# GEMINI.md

This file provides guidance to Gemini Code (gemini.ai/code) when working with code in this repository.

## Prompt Instruction:

I want you to create a custom Prophecy SQL gem called `BRE_SQL_Gem_basic` - a Transform gem that allows creation of business rules. 

The business user will:
1) Input column - select an existing input column, this will need to be dynamically generated based on the input port that is selected, which the gem logic will need to incorporate to detect the name of the table (dynamically generated from the input table that is wired into the gem as input). and then allow the specification of the column names from that table. There should not be a place for the user to manually enter an input_table as this will be dictated by the input that has been wired up to the gem. Also the input_column should be clickable/selectable from the input ports, not "typed" 
2) Output column - Once the input either select and existing OUTPUT column or specify an new OUTPUT column that doesn't exist.
3) Define the logic for the business rule in plain text, this should be done in two separate inputs. The "If clause", which will contain the logic, and then the value that should be output into the output column (that was specified in point 2 above)

For example
1) 'Input_Column' (selected from the existing input ports)
2) 'New_Output_Column'
3) Rule consists of input and output
    input = 'If Input_Column > 100' 
    output = New_Output_Column = 'this row is greater than 100'

This gem (as with all gems) will consist of two files. 

## Key Files to create:

- **BRE_SQL_Gem_basic.py**: The Prophecy gem definition with ComponentProperties, dialog UI, validation, and code generation
- **BRE_SQL_Gem_basic.sql**: This file will define the logic of the case statement that will be built by the previous interface.

The inputs will be selectable by whichever input ports are available, the outputs will be free text, or selectable from the input ports

This is the UI that will take user input that will eventually build the SQL (which will be a large case statement with jinja templating and be dbt-core compliant). 

## Reference Resources (Symlinked)
- **uispec.py**: UI specification reference (copied from @./.venv/lib/python3.11/site-packages/prophecy/cb/ui/uispec.pyfor convenience)

- **ComponentBuilderPython/**: Prophecy component builder framework
  - `prophecy/cb/ui/uispec.py` - UI element classes (Dialog, TextBox, Checkbox, etc.)
  - `prophecy/cb/server/base/ComponentBuilderBase.py` - Base classes (ComponentSpec, ComponentProperties, etc.)
  - `prophecy/cb/server/base/datatypes.py` - SInt, SString, SColumn types

SQL Gems need two files to be created. (1) DBT sql gem (examples in the "macros" folder) and (2) their corresponding "interface" files in the "gems" folder, see locations below:
- **snowflake-sql-basics-main/gems/**: Example gems (the interface)
- **snowflake-sql-basics-main/macros/**: Example gems (the sql)
    - Examples include: DataCleansing, DynamicSelect, FuzzyMatch, JSONParse, MultiColumnEdit,MultiColumnRename, TextToColumns, Transpose, UnionByName, XMLParse (they should be treated as pairs of files as they relate to each other based on name)

## Reference Documentation

- https://docs.prophecy.io/engineers/gem-builder
- https://docs.prophecy.io/engineers/gem-builder-reference
- https://docs.prophecy.io/engineers/optimization-functions

## Useful Example Gems for UI Patterns (in the directory )

- user interface files = @./sql_examples/gems/*
- sql dbt code files = @./sql_examples/macros/*
## Known Issues / Future Work

- **Output schema**: should be the input schema plus the output columns that are defined in the Gems UI. This might be additional columns, it might not, it might just be the same schema. 