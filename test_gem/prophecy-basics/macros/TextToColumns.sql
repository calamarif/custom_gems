{% macro TextToColumns(relation_name,
    columnNames,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName   ) -%}
    {{ return(adapter.dispatch('TextToColumns', 'prophecy_basics')(relation_name,
    columnNames,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName   )) }}
{% endmacro %}

{% macro default__TextToColumns(
    relation_name,
    columnNames,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName
    ) %}

{#
  Build the regex pattern for matching the delimiter.
#}
{%- set pattern = delimiter -%}
{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}

{# Helper to quote column names inline #}
{%- set quote_char = '`' -%}

{# Quote the column name properly #}
{%- set quoted_column_name = prophecy_basics.quote_identifier(columnNames) -%}

{%- if split_strategy == 'splitColumns' -%}
    WITH source AS (
        SELECT *,
            split(
                regexp_replace({{ quoted_column_name }}, {{ "'" ~ pattern ~ "'" }}, '%%DELIM%%'),
                '%%DELIM%%'
            ) AS tokens
        FROM {{ relation_list | join(', ') }}
    ),
    all_data AS (
    SELECT *,
        {# Extract tokens positionally (Spark arrays are 0-indexed) #}
        {%- for i in range(1, noOfColumns) %}
            regexp_replace(trim(tokens[{{ i - 1 }}]), '^"|"$', '')
            AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ i ~ '_' ~ splitColumnSuffix ~ quote_char }}{% if not loop.last or leaveExtraCharLastCol %}, {% endif %}
        {%- endfor %}
        {%- if leaveExtraCharLastCol %}
            CASE
                WHEN size(tokens) >= {{ noOfColumns }}
                    THEN array_join(slice(tokens, {{ noOfColumns }}, greatest(size(tokens) - {{ noOfColumns }} + 1, 0)), '{{ delimiter }}')
                ELSE null
            END AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix ~ quote_char }}
        {%- else %}
            tokens[{{ noOfColumns - 1 }}] AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix ~ quote_char }}
        {%- endif %}
    FROM source
    )
    SELECT * EXCEPT(tokens) FROM all_data

{%- elif split_strategy == 'splitRows' -%}
    SELECT r.*,
        trim(regexp_replace(s.col, '[{}_]', ' ')) AS {{ quote_char ~ splitRowsColumnName ~ quote_char }}
    FROM {{ relation_list | join(', ') }} r
    LATERAL VIEW explode(
        split(
            if({{ quoted_column_name }} IS NULL, '', {{ quoted_column_name }}),
            '{{ pattern }}'
        )
    ) s AS col

{%- else -%}
SELECT * FROM {{ relation_list | join(', ') }}
{%- endif -%}

{% endmacro %}

{% macro bigquery__TextToColumns(
    relation_name,
    columnNames,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName
    ) %}

{#
  Build the regex pattern for matching the delimiter.
#}
{%- set pattern = delimiter -%}
{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}

{# Helper to quote column names inline #}
{%- set quote_char = '`' -%}

{# Quote the column name properly #}
{%- set quoted_column_name = prophecy_basics.quote_identifier(columnNames) -%}

{%- if split_strategy == 'splitColumns' -%}
    WITH source AS (
        SELECT *,
            SPLIT(
                REGEXP_REPLACE({{ quoted_column_name }}, {{ "'" ~ pattern ~ "'" }}, '%%DELIM%%'),
                '%%DELIM%%'
            ) AS tokens
        FROM {{ relation_list | join(', ') }}
    ),
    all_data AS (
    SELECT *,
        {# Extract tokens positionally (BigQuery arrays are 0-indexed) #}
        {%- for i in range(1, noOfColumns) %}
            CASE
                WHEN ARRAY_LENGTH(tokens) > {{ i - 1 }}
                    THEN REGEXP_REPLACE(TRIM(tokens[OFFSET({{ i - 1 }})]), r'^"|"$', '')
                ELSE null
            END AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ i ~ '_' ~ splitColumnSuffix ~ quote_char }}{% if not loop.last or leaveExtraCharLastCol %}, {% endif %}
        {%- endfor %}
        {%- if leaveExtraCharLastCol %}
            CASE
                WHEN ARRAY_LENGTH(tokens) >= {{ noOfColumns }}
                    THEN ARRAY_TO_STRING(ARRAY(SELECT tokens[OFFSET(i)] FROM UNNEST(GENERATE_ARRAY({{ noOfColumns - 1 }}, ARRAY_LENGTH(tokens) - 1)) AS i), '{{ delimiter }}')
                ELSE null
            END AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix ~ quote_char }}
        {%- else %}
            CASE
                WHEN ARRAY_LENGTH(tokens) > {{ noOfColumns - 1 }}
                    THEN REGEXP_REPLACE(TRIM(tokens[OFFSET({{ noOfColumns - 1 }})]), r'^"|"$', '')
                ELSE null
            END AS {{ quote_char ~ splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix ~ quote_char }}
        {%- endif %}
    FROM source
    )
    SELECT * EXCEPT(tokens) FROM all_data

{%- elif split_strategy == 'splitRows' -%}
    SELECT r.*,
        REGEXP_REPLACE(TRIM(split_value), r'[{}_]', ' ') AS {{ quote_char ~ splitRowsColumnName ~ quote_char }}
    FROM {{ relation_list | join(', ') }} r,
    UNNEST(SPLIT(COALESCE(r.{{ quoted_column_name }}, ''), '{{ pattern }}')) AS split_value

{%- else -%}
SELECT * FROM {{ relation_list | join(', ') }}
{%- endif -%}

{% endmacro %}


{%- macro duckdb__TextToColumns(
    relation_name,
    columnNames,
    delimiter,
    split_strategy,
    noOfColumns,
    leaveExtraCharLastCol,
    splitColumnPrefix,
    splitColumnSuffix,
    splitRowsColumnName
) -%}

{# Handle escaped delimiters from Python - remove backslashes entirely #}
{%- set pattern = delimiter.replace('\\', '') -%}
{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
{# Handle string boolean parameter from Python - check string directly #}
{%- set quoted_column = prophecy_basics.quote_identifier(columnNames) -%}

{%- if split_strategy == 'splitColumns' -%}
    WITH source AS (
        SELECT *,
            string_split({{ quoted_column }}, '{{ pattern }}') AS tokens
        FROM {{ relation_list | join(', ') }}
    ),
    all_data AS (
    SELECT *,
        {# Extract tokens positionally (DuckDB arrays are 1-indexed) #}
        {%- for i in range(1, noOfColumns) %}
            regexp_replace(trim(tokens[{{ i }}]), '^"|"$', '')
            AS {{ prophecy_basics.quote_identifier(splitColumnPrefix ~ '_' ~ i ~ '_' ~ splitColumnSuffix) }}{% if not loop.last or leaveExtraCharLastCol == 'Leave extra in last column' %},{% endif %}
        {%- endfor %}
        {%- if leaveExtraCharLastCol == 'Leave extra in last column' %}
            CASE
                WHEN array_length(tokens) >= {{ noOfColumns }}
                    THEN array_to_string(tokens[{{ noOfColumns }}:], '{{ pattern }}')
                ELSE null
            END AS {{ prophecy_basics.quote_identifier(splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix) }}
        {%- else %}{% if noOfColumns > 1 %},{% endif %}
            tokens[{{ noOfColumns }}] AS {{ prophecy_basics.quote_identifier(splitColumnPrefix ~ '_' ~ noOfColumns ~ '_' ~ splitColumnSuffix) }}
        {%- endif %}
    FROM source
    )
    SELECT * EXCLUDE(tokens) FROM all_data

{%- elif split_strategy == 'splitRows' -%}
  SELECT
    r.*,
    -- replace { } _ globally with spaces, collapse repeats, then trim
    trim(
      regexp_replace(
        regexp_replace(s.col, '[{}_]', ' ', 'g'),
        '\s+',
        ' ',
        'g'
      )
    ) AS {{ prophecy_basics.quote_identifier(splitRowsColumnName) }}
  FROM {{ relation_list | join(', ') }} r
  CROSS JOIN UNNEST(
    string_split(coalesce(r.{{ quoted_column }}, ''), '{{ pattern }}')
  ) AS s(col)

{%- else -%}
  SELECT * FROM {{ relation_list | join(', ') }}
{%- endif -%}

{%- endmacro -%}