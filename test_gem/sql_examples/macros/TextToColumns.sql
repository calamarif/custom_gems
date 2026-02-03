{% macro TextToColumns(
    relation_name,
    columnName,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName
    ) %}

{# 
  Build the regex pattern for matching the delimiter only when it is not inside 
  double quotes, single quotes, parentheses, or brackets.
  Start with the literal delimiter and append lookahead assertions as needed.
#}
{%- set pattern = delimiter -%}
{%- if split_strategy == 'splitColumns' -%}
    with source as (
        select *,
            SPLIT(
              REGEXP_REPLACE({{ columnName }}, {{ "'" ~ pattern ~ "'" }}, '%%DELIM%%'),
              '%%DELIM%%'
            ) as tokens
        from {{ relation_name }}
    ),
    all_data as (
    select
        s.*,
        {# Extract tokens positionally (Snowflake arrays are 0-indexed) #}
        {%- for i in range(1, noOfColumns) %}
            TRIM(s.tokens[{{ i - 1 }}],'"') as {{ splitColumnPrefix }}_{{ i }}_{{ splitColumnSuffix }}{% if not loop.last or leaveExtraCharLastCol %}, {% endif %}
        {%- endfor %}
        {%- if leaveExtraCharLastCol %}
                CASE 
                  WHEN ARRAY_SIZE(s.tokens) >= {{ noOfColumns }} 
                  THEN ARRAY_TO_STRING(ARRAY_SLICE(s.tokens, {{ noOfColumns - 1 }}, ARRAY_SIZE(s.tokens)), '{{ delimiter }}')
                  ELSE NULL
                END AS {{ splitColumnPrefix }}_{{ noOfColumns }}_{{ splitColumnSuffix }}
        {%- else %}
            s.tokens[{{ noOfColumns - 1 }}] as {{ splitColumnPrefix }}_{{ noOfColumns }}_{{ splitColumnSuffix }}
        {%- endif %}
    from source as s
    )
    select * EXCLUDE(tokens) from all_data

{%- elif split_strategy == 'splitRows' -%}
    SELECT {{ relation_name }}.*,TRIM(REGEXP_REPLACE(s.value, '[{}_]', ' ')) AS {{ splitRowsColumnName }}
    FROM {{ relation_name }}, LATERAL SPLIT_TO_TABLE(iff({{ columnName }} is null, '', {{ columnName }}), '{{pattern}}') s
{%- else -%}
    select * from {{ relation_name }}
{%- endif -%}

{% endmacro %}
