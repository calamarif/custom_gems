{%- macro MultiColumnEdit(
    relation,
    expressionToBeApplied,
    allColumnNames=[],
    columnNames=[],
    changeOutputFieldName=false,
    prefixSuffixOption = 'prefix / suffix',
    prefixSuffixToBeAdded=''
) -%}

    {%- set select_expressions = [] -%}

    {%- if changeOutputFieldName -%}
        {%- for col in allColumnNames -%}
            {%- do select_expressions.append('"' ~ col ~ '"') -%}
        {%- endfor -%}
        {%- for col in columnNames -%}
            {%- if prefixSuffixOption | lower == "prefix" -%}
                {%- set alias = prefixSuffixToBeAdded ~ col -%}
            {%- else -%}
                {%- set alias = col ~ prefixSuffixToBeAdded -%}
            {%- endif -%}
            {%- set expr = expressionToBeApplied | replace('column_value', '"' ~ col ~ '"') | replace('column_name', '"' ~ col ~ '"') -%}
            {%- do select_expressions.append(expr ~ ' as "' ~ alias ~ '"') -%}
        {%- endfor -%}
    {%- else -%}
        {%- for col in allColumnNames -%}
            {%- if col in columnNames -%}
                {%- set expr = expressionToBeApplied | replace('column_value', '"' ~ col ~ '"') | replace('column_name', '"' ~ col ~ '"') -%}
                {%- do select_expressions.append(expr ~ ' as "' ~ col ~ '"') -%}
            {%- else -%}
                {%- do select_expressions.append('"' ~ col ~ '"') -%}
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}

    select
        {{ select_expressions | join(',\n        ') }}
    from {{ relation }}
{%- endmacro -%}
