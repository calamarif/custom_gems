{% macro MultiColumnEdit(relation_name,
    expressionToBeApplied,
    allColumnNames=[],
    columnNames=[],
    changeOutputFieldName=false,
    prefixSuffixOption = 'prefix / suffix',
    prefixSuffixToBeAdded='') -%}
    {{ return(adapter.dispatch('MultiColumnEdit', 'prophecy_basics')(relation_name,
    expressionToBeApplied,
    allColumnNames,
    columnNames,
    changeOutputFieldName,
    prefixSuffixOption,
    prefixSuffixToBeAdded)) }}
{% endmacro %}


{%- macro default__MultiColumnEdit(
    relation_name,
    expressionToBeApplied,
    allColumnNames=[],
    columnNames=[],
    changeOutputFieldName=false,
    prefixSuffixOption = 'prefix / suffix',
    prefixSuffixToBeAdded=''
) -%}

    {%- set select_expressions = [] -%}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}

    {%- if changeOutputFieldName -%}
        {%- for col in allColumnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- do select_expressions.append(quoted_col) -%}
        {%- endfor -%}
        {%- for col in columnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- set col_name_replacement = '"' ~ col ~ '"' -%}
            {%- if prefixSuffixOption | lower == "prefix" -%}
                {%- set alias = prefixSuffixToBeAdded ~ col -%}
            {%- else -%}
                {%- set alias = col ~ prefixSuffixToBeAdded -%}
            {%- endif -%}
            {%- set quoted_alias = prophecy_basics.quote_identifier(alias) -%}
            {%- set expr = expressionToBeApplied | replace('column_value', quoted_col) | replace('column_name', col_name_replacement) -%}
            {%- do select_expressions.append(expr ~ ' as ' ~ quoted_alias) -%}
        {%- endfor -%}
    {%- else -%}
        {%- for col in allColumnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- set col_name_replacement = '"' ~ col ~ '"' -%}
            {%- if col in columnNames -%}
                {%- set expr = expressionToBeApplied | replace('column_value', quoted_col) | replace('column_name', col_name_replacement) -%}
                {%- do select_expressions.append(expr ~ ' as ' ~ quoted_col) -%}
            {%- else -%}
                {%- do select_expressions.append(quoted_col) -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}

    select {{ select_expressions | join(',\n        ') }} from {{ relation_list | join(', ') }}

{%- endmacro -%}

{%- macro duckdb__MultiColumnEdit(
    relation_name,
    expressionToBeApplied,
    allColumnNames=[],
    columnNames=[],
    changeOutputFieldName=false,
    prefixSuffixOption = 'prefix / suffix',
    prefixSuffixToBeAdded=''
) -%}

    {%- set select_expressions = [] -%}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}

    {%- if changeOutputFieldName -%}
        {%- for col in allColumnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- do select_expressions.append(quoted_col) -%}
        {%- endfor -%}
        {%- for col in columnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- set col_name_replacement = '"' ~ col ~ '"' -%}
            {%- if prefixSuffixOption | lower == "prefix" -%}
                {%- set alias = prophecy_basics.quote_identifier(prefixSuffixToBeAdded ~ col) -%}
            {%- else -%}
                {%- set alias = prophecy_basics.quote_identifier(col ~ prefixSuffixToBeAdded) -%}
            {%- endif -%}
            {%- set expr = expressionToBeApplied | replace('column_value', quoted_col) | replace('column_name', col_name_replacement) -%}
            {%- do select_expressions.append(expr ~ ' as ' ~ alias) -%}
        {%- endfor -%}
    {%- else -%}
        {%- for col in allColumnNames -%}
            {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
            {%- set col_name_replacement = '"' ~ col ~ '"' -%}
            {%- if col in columnNames -%}
                {%- set expr = expressionToBeApplied | replace('column_value', quoted_col) | replace('column_name', col_name_replacement) -%}
                {%- do select_expressions.append(expr ~ ' as ' ~ quoted_col) -%}
            {%- else -%}
                {%- do select_expressions.append(quoted_col) -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}

    select {{ select_expressions | join(',\n        ') }} from {{ relation_list | join(', ') }}

{%- endmacro -%}
