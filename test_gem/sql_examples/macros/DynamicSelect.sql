{%- macro DynamicSelect(relation, schema, targetTypes, selectUsing, customExpression='') -%}

    {%- set enriched_schema = [] -%}
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

                {%- set evaluation_result = SnowflakeSqlBasics.evaluate_expression(expression_to_evaluate) | trim -%}

                {# Only add column if the evaluation result is true #}
                {%- if evaluation_result == "True" -%}
                    {%- do selected_columns.append("\"" ~ column["name"] ~ "\"") -%}
                {%- endif -%}
        {%- else -%}
            {# If no custom expression, select columns based on target types #}
            {%- if column["dataType"] in targetTypes -%}
                {%- do selected_columns.append("\"" ~ column["name"] ~ "\"") -%}
            {%- endif -%}
        {%- endif -%}
    {%- endfor -%}

    {# Build and return the SELECT statement #}
    {%- if selected_columns -%}
        SELECT {{ selected_columns | join(', ') }} FROM {{ relation }}
    {%- else -%}
        SELECT NULL AS no_columns_matched FROM {{ relation }}
    {%- endif -%}
{%- endmacro -%}
