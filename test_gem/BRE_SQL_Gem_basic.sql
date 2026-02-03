{% macro BRE_SQL_Gem_basic(input_table, input_column, output_column, rule_condition, rule_output_value) %}
    -- SQL logic for BRE_SQL_Gem_basic
    -- input_table: {{ input_table }}
    -- input_column: {{ input_column }}
    -- output_column: {{ output_column }}
    -- rule_condition: {{ rule_condition }}
    -- rule_output_value: {{ rule_output_value }}

    {# Replace Input_Column placeholder in the condition with the actual input_column name #}
    {%- set final_condition = rule_condition.replace("Input_Column", input_column) -%}

    SELECT
        *,
        CASE
            WHEN {{ final_condition }} THEN {{ rule_output_value }}
            ELSE NULL -- Default value if the condition is not met
        END AS {{ output_column }}
    FROM {{ input_table }}
{% endmacro %}