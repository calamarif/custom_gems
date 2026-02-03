{% macro JSONParse(
    relation_name,
    columnName
    ) %}

    {%- if columnName -%}
        select
            *,
            {%- for col in columnName %}
                PARSE_JSON({{ '"' ~ col ~ '"' }}) as {{ '"' ~ col ~ '_parsed"' }}{% if not loop.last %},{% endif %}
            {%- endfor %}
        from {{ relation_name }}
    {%- else -%}
        select * from {{ relation_name }}
    {%- endif -%}
    
{% endmacro %}