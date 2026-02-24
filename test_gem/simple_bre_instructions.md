# GEMINI.md

This file provides guidance to Gemini Code (gemini.ai/code) when working with code in this repository.

## Prompt Instruction:

I want you to create a custom Prophecy SQL gem called `BRE_SQL_Gem_basic` - a Transform gem that allows creation of business rules. The project I am building this under is 'SQL_BRE_Gem_dev' which you will need to reference.

The business user will:
1) Input column - select an existing input column, this will need to be dynamically generated based on the input port that is selected, which the gem logic will need to incorporate to detect the name of the table (dynamically generated from the input table that is wired into the gem as input). and then allow the specification of the column names from that table. There should not be a place for the user to manually enter an input_table as this will be dictated by the input that has been wired up to the gem. Also the input_column should be clickable/selectable from the input ports, not "typed" 
2) Output column - Once the input either select and existing OUTPUT column or specify an new OUTPUT column that doesn't exist.
3) Define the logic for the business rule in plain text, this should be done in two separate inputs. 
    - rule_condition - The "If clause", which will contain the logic, (applied to the input column (that was specified in point 1 above) and then 
    - rule_output_value - the value that should be output into the output column (that was specified in point 2 above)
LASTLY) You should be able to add multiple rules within this single gem such that you will need to save each rule into a graphical table within the gem, similarly to these screenshots here:
- @test_gem/bre_screenshot_1.png
- @test_gem/bre_screenshot_2.png

You need to make this UI simple to use and not require the user to understand how to structure json or anything technical. It would be good to make sure if the

For example
1) 'Input_Column' - selected from the list of columns (from the ports that have been connected to the gem)
2) 'Output_Column' - optionally selected from the list of columns (from the ports that have been connected to the gem) - or alternatively accepts free text to specify a new column to be created for the output
3) Rule consists of rule_condition (that looks at the input_column) and the rule_output_value which is the value to output into the 'Output_Column'
    rule_condition = '> 18' 
    rule_output_value = 'Is an Adult'

This gem (as with all gems) will consist of two files. 

## Key Files to create:

- **BRE_SQL_Gem_basic.py**: The Prophecy gem definition with ComponentProperties, dialog UI, validation, and code generation
- **BRE_SQL_Gem_basic.sql**: This file will define the logic of the case statement that will be built by the previous interface.

The inputs will be selectable by whichever input ports are available, the outputs will be free text, or selectable from the input ports

This is the UI that will take user input that will eventually build the SQL (which will be a large case statement with jinja templating and be dbt-core compliant). 

## Reference Resources
- **uispec.py**: UI specification reference (copied from @./.venv/lib/python3.11/site-packages/prophecy/cb/ui/uispec.py for convenience)

- **ComponentBuilderPython/**: Prophecy component builder framework
  - `prophecy/cb/ui/uispec.py` - UI element classes (Dialog, TextBox, Checkbox, etc.)
  - `prophecy/cb/server/base/ComponentBuilderBase.py` - Base classes (ComponentSpec, ComponentProperties, etc.)
  - `prophecy/cb/server/base/datatypes.py` - SInt, SString, SColumn types

SQL Gems need two files to be created. (1) DBT sql gem (examples in the "macros" folder) and (2) their corresponding "interface" files in the "gems" folder, see locations below:
- **prophecy-basics/gems/**: Example gems (the interface)
- **prophecy-basics/macros/**: Example gems (the sql)
    - Examples include: DataCleansing, DynamicSelect, FuzzyMatch, JSONParse, MultiColumnEdit,MultiColumnRename, TextToColumns, Transpose, UnionByName, XMLParse (they should be treated as pairs of files as they relate to each other based on name). These files will need to be analysed carefully to base your UI decisions on (as they all have different options)

## Reference Documentation
- https://docs.prophecy.io/engineers/gem-builder
- https://docs.prophecy.io/engineers/gem-builder-reference
- https://docs.prophecy.io/engineers/optimization-functions

## Useful Example Gems for UI Patterns (in the directory )
- user interface files = @./test_gem/prophecy-basics/gems/*
- sql dbt code files = @./test_gem/prophecy-basics/macros/*

## Design Suggestions
- @test_gem/Gem Design Principles.txt

- **Output schema**: should be the input schema plus the output columns that are defined in the Gems UI. This might be additional columns, it might not, it might just be the same schema. 