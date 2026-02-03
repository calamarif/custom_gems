{%- macro UnionByName(
    relation_name,
    firstSchema,
    secondSchema,
    missingColumnOps
) -%}

    {# Split relation_name into two relation identifiers #}
    {%- set relations = relation_name.split(',') -%}
    {%- set first_relation = relations[0] | trim -%}
    {%- set second_relation = relations[1] | trim -%}

    {# Extract column names from each schema #}
    {%- set first_columns = [] -%}
    {%- for col in firstSchema -%}
        {%- set _ = first_columns.append('"' ~ col.name ~ '"') -%}
    {%- endfor %}

    {%- set second_columns = [] -%}
    {%- for col in secondSchema -%}
        {% set _ = second_columns.append('"' ~ col.name ~ '"') %}
    {%- endfor -%}

    {# If nameBasedUnionOperation, ensure both schemas have exactly the same set of columns #}
    {%- if missingColumnOps == 'nameBasedUnionOperation' -%}
        {%- set diff_first = [] -%}
        {%- for col in first_columns -%}
            {%- if col not in second_columns -%}
                {%- set _ = diff_first.append(col) -%}
            {%- endif -%}
        {%- endfor -%}
        {%- set diff_second = [] -%}
        {%- for col in second_columns -%}
            {%- if col not in first_columns -%}
                {%- set _ = diff_second.append(col) -%}
            {%- endif -%}
        {%- endfor -%}
        {%- if diff_first | length > 0 or diff_second | length > 0 -%}
            {{ exceptions.raise_compiler_error("Column mismatch in nameBasedUnionOperation. First schema columns: " ~ first_columns | join(', ') ~ " vs Second schema columns: " ~ second_columns | join(', ')) }}
        {%- endif -%}
    {%- endif -%}

    {# Determine final column order #}
    {%- if missingColumnOps == 'allowMissingColumns' -%}
        {# Start with firstSchema columns, then add extra columns from secondSchema #}
        {%- set final_columns = first_columns[:] -%}
        {%- for col in second_columns -%}
            {%- if col not in final_columns -%}
                {%- set _ = final_columns.append(col) -%}
            {%- endif -%}
        {%- endfor -%}
    {%- elif missingColumnOps == 'nameBasedUnionOperation' -%}
        {# Both schemas have the same set, so use firstSchema order #}
        {%- set final_columns = first_columns -%}
    {%- else -%}
        {{ exceptions.raise_compiler_error("Unsupported missingColumnOps value: " ~ missingColumnOps) }}
    {%- endif -%}

    {# Build SELECT statement for the first relation #}
    {%- set select_first = [] -%}
    {%- for col in final_columns -%}
        {%- if col in first_columns -%}
            {%- set _ = select_first.append(col) -%}
        {%- else -%}
            {%- set _ = select_first.append("null as " ~ col) -%}
        {%- endif -%}
    {%- endfor -%}

    {# Build SELECT statement for the second relation #}
    {%- set select_second = [] -%}
    {%- for col in final_columns -%}
        {%- if col in second_columns -%}
            {%- set _ = select_second.append(col) -%}
        {%- else -%}
            {%- set _ = select_second.append("null as " ~ col) -%}
        {%- endif -%}
    {%- endfor -%}

    {# Return the final union query #}
    with union_query as (
        select {{ select_first | join(', ') }} from {{ first_relation }}
        union all
        select {{ select_second | join(', ') }} from {{ second_relation }}
    )
    select * from union_query
{%- endmacro %}