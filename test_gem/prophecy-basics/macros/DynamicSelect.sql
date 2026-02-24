{% macro DynamicSelect(relation_name, schema, targetTypes, selectUsing, customExpression='') -%}
    {{ return(adapter.dispatch('DynamicSelect', 'prophecy_basics')(relation_name, schema, targetTypes, selectUsing, customExpression)) }}
{% endmacro %}


{%- macro default__DynamicSelect(relation_name, schema, targetTypes, selectUsing, customExpression='') -%}

    {%- set enriched_schema = [] -%}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- for column in schema -%}
        {# Create a copy of the column dictionary #}
        {%- set new_column = {} -%}
        {%- for key, value in column.items() -%}
            {%- do new_column.update({key: value}) -%}
        {%- endfor -%}
        {# Add the column_index key using loop.index0 #}
        {%- do new_column.update({"column_index": loop.index0}) -%}
        {%- do enriched_schema.append(new_column) -%}
    {%- endfor -%}

    {%- set selected_columns = [] -%}
    {%- for column in enriched_schema -%}
        {%- if selectUsing == 'SELECT_EXPR' -%}
                {%- set expression_to_evaluate = customExpression -%}

                {%- if "column_name" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "column_name", "'" ~ column["name"] ~ "'") -%}
                {%- endif -%}

                {%- if "column_type" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "column_type", "'" ~ column["dataType"] ~ "'") -%}
                {%- endif -%}

                {%- if "field_number" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "field_number", "'" ~ column["column_index"] ~ "'") -%}
                {%- endif -%}

                {%- set evaluation_result = prophecy_basics.evaluate_expression(expression_to_evaluate) | trim -%}

                {# Only add column if the evaluation result is true #}
                {%- if evaluation_result == "True" -%}
                    {%- do selected_columns.append("`" ~ column["name"] ~ "`") -%}
                {%- endif -%}
        {%- else -%}
            {# If no custom expression, select columns based on target types #}
            {%- if column["dataType"] in targetTypes -%}
                {%- do selected_columns.append("`" ~ column["name"] ~ "`") -%}
            {%- endif -%}
        {%- endif -%}
    {%- endfor -%}

    {# Build and return the SELECT statement #}
    {%- if selected_columns -%}
        SELECT {{ selected_columns | join(', ') }} FROM {{ relation_list | join(', ') }}
    {%- else -%}
        SELECT NULL AS no_columns_matched FROM {{ relation_list | join(', ') }}
    {%- endif -%}
{%- endmacro -%}

{%- macro duckdb__DynamicSelect(relation_name, schema, targetTypes=[], selectUsing='SELECT_TYPES', customExpression='') -%}
{#
  Dynamic column selection macro for DuckDB - handles both expression-based and type-based selection.
  
  Args:
    relation_name: The table/relation to select from
    schema: List of column dictionaries with 'name' and 'dataType' keys
    targetTypes: List of data types to select (for SELECT_TYPES mode) - case-insensitive
    selectUsing: Selection mode - 'SELECT_EXPR' or 'SELECT_TYPES'
    customExpression: Custom SQL expression for SELECT_EXPR mode
  
  Returns:
    SELECT statement with dynamically selected columns
  
  Examples:
    SELECT_TYPES mode: {{ DynamicSelect(ref('my_table'), schema, ['STRING', 'INTEGER']) }}
    SELECT_EXPR mode: {{ DynamicSelect(ref('my_table'), schema, [], 'SELECT_EXPR', "column_name like '%user%'") }}
#}

    {%- set enriched_schema = [] -%}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- for column in schema -%}
        {# Create a copy of the column dictionary #}
        {%- set new_column = {} -%}
        {%- for key, value in column.items() -%}
            {%- do new_column.update({key: value}) -%}
        {%- endfor -%}
        {# Add the column_index key using loop.index0 #}
        {%- do new_column.update({"column_index": loop.index0}) -%}
        {%- do enriched_schema.append(new_column) -%}
    {%- endfor -%}

    {%- set selected_columns = [] -%}
    {%- for column in enriched_schema -%}
        {%- if selectUsing == 'SELECT_EXPR' -%}
                {%- set expression_to_evaluate = customExpression -%}

                {%- if "column_name" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "column_name", "'" ~ column["name"] ~ "'") -%}
                {%- endif -%}

                {%- if "column_type" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "column_type", "'" ~ column["dataType"] ~ "'") -%}
                {%- endif -%}

                {%- if "field_number" in expression_to_evaluate -%}
                    {%- set expression_to_evaluate = expression_to_evaluate.replace(
                        "field_number", column["column_index"] | string) -%}
                {%- endif -%}

                {%- set evaluation_result = prophecy_basics.evaluate_expression(expression_to_evaluate) | trim -%}

                {# Only add column if the evaluation result is true #}
                {%- if evaluation_result | lower == "true" -%}
                    {%- do selected_columns.append(prophecy_basics.quote_identifier(column["name"])) -%}
                {%- endif -%}
        {%- else -%}
            {# If no custom expression, select columns based on target types (case-insensitive) #}
            {%- set column_type_upper = column["dataType"] | upper -%}
            {%- set target_types_upper = targetTypes | map('upper') | list -%}
            {%- if column_type_upper in target_types_upper -%}
                {%- do selected_columns.append(prophecy_basics.quote_identifier(column["name"])) -%}
            {%- endif -%}
        {%- endif -%}
    {%- endfor -%}

    {# Build and return the SELECT statement #}
    {%- if selected_columns -%}
        SELECT {{ selected_columns | join(', ') }} FROM {{ relation_list | join(', ') }}
    {%- else -%}
        SELECT NULL AS no_columns_matched FROM {{ relation_list | join(', ') }}
    {%- endif -%}
{%- endmacro -%}
