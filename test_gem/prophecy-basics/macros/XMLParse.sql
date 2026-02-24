{% macro XMLParse(relation_name,
    columnName,
    parsingMethod,
    sampleRecord,
    sampleSchema) -%}
    {{ return(adapter.dispatch('XMLParse', 'prophecy_basics')(relation_name,
    columnName,
    parsingMethod,
    sampleRecord,
    sampleSchema)) }}
{% endmacro %}


{% macro default__XMLParse(
    relation_name,
    columnName,
    parsingMethod,
    sampleRecord,
    sampleSchema
) %}

    {{ log("Parsing XML using method: " ~ parsingMethod, info=True) }}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}

    {%- if not columnName or columnName | trim == '' -%}
        select * from {{ relation_list | join(', ') }}

    {%- elif parsingMethod == 'parseFromSchema' and (not sampleSchema or sampleSchema | trim == '') -%}
        select * from {{ relation_list | join(', ') }}

    {%- elif parsingMethod == 'parseFromSampleRecord' and (not sampleRecord or sampleRecord | trim == '') -%}
        select * from {{ relation_list | join(', ') }}

    {%- else -%}
        {%- set quoted_col = "`" ~ columnName ~ "`" -%}
        {%- set alias_col = "`" ~ columnName ~ "_parsed`" -%}

        {%- if parsingMethod == 'parseFromSchema' -%}
            select
                *,
                from_xml({{ quoted_col }}, '{{ sampleSchema | replace("\n", " ") }}') as {{ alias_col }}
            from {{ relation_list | join(', ') }}

        {%- elif parsingMethod == 'parseFromSampleRecord' -%}
            select
                *,
                from_xml({{ quoted_col }}, schema_of_xml('{{ sampleRecord | replace("\n", " ") }}')) as {{ alias_col }}
            from {{ relation_list | join(', ') }}

        {%- elif parsingMethod == 'none' or not parsingMethod -%}
            select * from {{ relation_list | join(', ') }}

        {%- else -%}
            {{ exceptions.raise_compiler_error(
                "Invalid parsingMethod: '" ~ parsingMethod ~ "'. Expected 'parseFromSchema', 'parseFromSampleRecord', or 'none'."
            ) }}
        {%- endif -%}
    {%- endif -%}

{% endmacro %}

{%- macro duckdb__XMLParse(relation_name,
    columnName,
    parsingMethod,
    sampleRecord,
    sampleSchema) -%}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {# Simple XML parsing implementation for DuckDB - returns original data #}
    SELECT * FROM {{ relation_list | join(', ') }}
{%- endmacro -%}