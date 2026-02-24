{% macro FuzzyMatch(relation_name,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage=0,
    includeSimilarityScore=False) -%}
    {{ return(adapter.dispatch('FuzzyMatch', 'prophecy_basics')(relation_name,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage,
    includeSimilarityScore)) }}
{% endmacro %}


{% macro default__FuzzyMatch(
    relation_name,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage=0,
    includeSimilarityScore=False
    ) %}

{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
{%- if mode == 'PURGE' or mode == 'MERGE' -%}
    {# Build individual SELECT statements for each match field #}
    {%- set selects = [] -%}
    {%- for field in matchFields -%}
        {%- set key = field.matchFunction -%}
        {%- set col = field.columnName -%}

        {# Decide on the function name based on the key #}
        {%- if key == 'custom' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'name' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'phone' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- elif key == 'address' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'exact' -%}
            {%- set func_name = 'EXACT' -%}
        {%- elif key == 'equals' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- else -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- endif -%}

        {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
        {%- if key == 'custom' -%}
            {# For custom matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), '[[:punct:]]', ''))" -%}
        {%- elif key == 'name' -%}
            {# For name matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), '[[:punct:]]', ''))" -%}
        {%- elif key == 'address' -%}
            {# For address matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), '[[:punct:]]', ''))" -%}
        {%- else -%}
            {%- set column_value_expr = "CAST(" ~ quoted_col ~ " AS STRING)" -%}
        {%- endif -%}
        {%- if mode == 'PURGE' -%}
            {%- set select_stmt = "select CAST(" ~ recordIdCol ~ " AS STRING) as record_id, upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- elif mode == 'MERGE' -%}
            {%- set select_stmt = "select CAST(" ~ recordIdCol ~ " AS STRING) as record_id, CAST(" ~ sourceIdCol ~ " AS STRING) as source_id , upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- endif -%}

        {%- do selects.append(select_stmt) -%}

    {%- endfor -%}

    {%- set match_function_cte = selects | join(" union all ") -%}

with match_function as (
    {{ match_function_cte }}
),
cross_join_data as (
    select
        df0.record_id as record_id1,
        df1.record_id as record_id2,
        {%- if mode == 'MERGE' -%}
            df0.source_id as source_id1,
            df1.source_id as source_id2,
        {%- endif -%}
        df0.column_value as column_value_1,
        df1.column_value as column_value_2,
        df0.column_name as column_name,
        df0.function_name as function_name
    from match_function as df0
    cross join match_function as df1
    where df0.record_id <> df1.record_id
      and df0.function_name = df1.function_name
      and df0.column_name = df1.column_name
    {% if mode == 'MERGE' %}
       and df0.source_id <> df1.source_id
    {% endif %}
),
impose_function_match as (
    select
        record_id1,
        record_id2,
        {%- if mode == 'MERGE' -%}
            source_id1,
            source_id2,
        {%- endif -%}
        column_name,
        function_name,
        case
            when function_name = 'LEVENSHTEIN' then
                (1 - ( LEVENSHTEIN(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
            when function_name = 'EXACT' AND (column_value_1 = REVERSE(column_value_2) AND column_value_2 = REVERSE(column_value_1)) then
                100.0
            when function_name = 'EXACT' AND (column_value_1 <> REVERSE(column_value_2) OR column_value_2 = REVERSE(column_value_1)) then
                0.0
            when function_name = 'EQUALS' AND column_value_1 = column_value_2 then
                100.0
            when function_name = 'EQUALS' AND column_value_1 <> column_value_2 then
                0.0
            else
                {# Fallback to Levenshtein distance #}
                (1 - ( LEVENSHTEIN(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
        end as similarity_score
    from cross_join_data
),
replace_record_ids as (
    select
        GREATEST(record_id1, record_id2) as record_id1,
        LEAST(record_id1, record_id2) as record_id2,
        column_name,
        function_name,
        similarity_score
    from impose_function_match
),
final_output as (
    select
        record_id1,
        record_id2,
        round(avg(similarity_score),2) as similarity_score
    from replace_record_ids
    group by
    record_id1,
    record_id2
)
    {# Include similarity score if True #}
    {%- if includeSimilarityScore -%}
        select
            record_id1,
            record_id2,
            similarity_score from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- else -%}
        select
            record_id1,
            record_id2
            from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- endif -%}

{%- else -%}
    select * from {{ relation_list | join(', ') }}
{%- endif -%}

{% endmacro %}

{% macro bigquery__FuzzyMatch(
    relation_name,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage=0,
    includeSimilarityScore=False
    ) %}

{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
{%- if mode == 'PURGE' or mode == 'MERGE' -%}
    {# Build individual SELECT statements for each match field #}
    {%- set selects = [] -%}
    {%- for field in matchFields -%}
        {%- set key = field.matchFunction -%}
        {%- set col = field.columnName -%}

        {# Decide on the function name based on the key #}
        {%- if key == 'custom' -%}
            {%- set func_name = 'EDIT_DISTANCE' -%}
        {%- elif key == 'name' -%}
            {%- set func_name = 'EDIT_DISTANCE' -%}
        {%- elif key == 'phone' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- elif key == 'address' -%}
            {%- set func_name = 'EDIT_DISTANCE' -%}
        {%- elif key == 'exact' -%}
            {%- set func_name = 'EXACT' -%}
        {%- elif key == 'equals' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- else -%}
            {%- set func_name = 'EDIT_DISTANCE' -%}
        {%- endif -%}

        {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
        {%- if key == 'custom' -%}
            {# For custom matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), r'[^a-zA-Z0-9\\s]', ''))" -%}
        {%- elif key == 'name' -%}
            {# For name matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), r'[^a-zA-Z0-9\\s]', ''))" -%}
        {%- elif key == 'address' -%}
            {# For address matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS STRING), r'[^a-zA-Z0-9\\s]', ''))" -%}
        {%- else -%}
            {%- set column_value_expr = "CAST(" ~ quoted_col ~ " AS STRING)" -%}
        {%- endif -%}

        {# Properly quote recordIdCol and sourceIdCol with backticks #}
        {%- set quoted_record_id_col = prophecy_basics.quote_identifier(recordIdCol) -%}
        {%- set quoted_source_id_col = prophecy_basics.quote_identifier(sourceIdCol) -%}

        {%- if mode == 'PURGE' -%}
            {%- set select_stmt = "select CAST(" ~ quoted_record_id_col ~ " AS STRING) as record_id, upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- elif mode == 'MERGE' -%}
            {%- set select_stmt = "select CAST(" ~ quoted_record_id_col ~ " AS STRING) as record_id, CAST(" ~ quoted_source_id_col ~ " AS STRING) as source_id , upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- endif -%}

        {%- do selects.append(select_stmt) -%}

    {%- endfor -%}

    {%- set match_function_cte = selects | join(" union all ") -%}

with match_function as (
    {{ match_function_cte }}
),
cross_join_data as (
    select
        df0.record_id as record_id1,
        df1.record_id as record_id2,
        {%- if mode == 'MERGE' -%}
            df0.source_id as source_id1,
            df1.source_id as source_id2,
        {%- endif -%}
        df0.column_value as column_value_1,
        df1.column_value as column_value_2,
        df0.column_name as column_name,
        df0.function_name as function_name
    from match_function as df0
    cross join match_function as df1
    where df0.record_id <> df1.record_id
      and df0.function_name = df1.function_name
      and df0.column_name = df1.column_name
    {% if mode == 'MERGE' %}
       and df0.source_id <> df1.source_id
    {% endif %}
),
impose_function_match as (
    select
        record_id1,
        record_id2,
        {%- if mode == 'MERGE' -%}
            source_id1,
            source_id2,
        {%- endif -%}
        column_name,
        function_name,
        case
            when function_name = 'EDIT_DISTANCE' then
                (1 - ( EDIT_DISTANCE(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
            when function_name = 'EXACT' AND (column_value_1 = REVERSE(column_value_2) AND column_value_2 = REVERSE(column_value_1)) then
                100.0
            when function_name = 'EXACT' AND (column_value_1 <> REVERSE(column_value_2) OR column_value_2 = REVERSE(column_value_1)) then
                0.0
            when function_name = 'EQUALS' AND column_value_1 = column_value_2 then
                100.0
            when function_name = 'EQUALS' AND column_value_1 <> column_value_2 then
                0.0
            else
                {# Fallback to Edit Distance #}
                (1 - ( EDIT_DISTANCE(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
        end as similarity_score
    from cross_join_data
),
replace_record_ids as (
    select
        GREATEST(record_id1, record_id2) as record_id1,
        LEAST(record_id1, record_id2) as record_id2,
        column_name,
        function_name,
        similarity_score
    from impose_function_match
),
final_output as (
    select
        record_id1,
        record_id2,
        round(avg(similarity_score),2) as similarity_score
    from replace_record_ids
    group by
    record_id1,
    record_id2
)
    {# Include similarity score if True #}
    {%- if includeSimilarityScore -%}
        select
            record_id1,
            record_id2,
            similarity_score from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- else -%}
        select
            record_id1,
            record_id2
            from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- endif -%}

{%- else -%}
    select * from {{ relation_list | join(', ') }}
{%- endif -%}

{% endmacro %}

{% macro duckdb__FuzzyMatch(
    relation_name,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage=0,
    includeSimilarityScore=False
    ) %}

{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
{%- if mode == 'PURGE' or mode == 'MERGE' -%}
    {# Build individual SELECT statements for each match field #}
    {%- set selects = [] -%}
    {%- for field in matchFields -%}
        {%- set key = field.matchFunction -%}
        {%- set col = field.columnName -%}

        {# Decide on the function name based on the key #}
        {%- if key == 'custom' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'name' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'phone' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- elif key == 'address' -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- elif key == 'exact' -%}
            {%- set func_name = 'EXACT' -%}
        {%- elif key == 'equals' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- else -%}
            {%- set func_name = 'LEVENSHTEIN' -%}
        {%- endif -%}

        {%- set quoted_col = prophecy_basics.quote_identifier(col) -%}
        {%- if key == 'custom' -%}
            {# For custom matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS VARCHAR), '[[:punct:]]', ''))" -%}
        {%- elif key == 'name' -%}
            {# For name matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS VARCHAR), '[[:punct:]]', ''))" -%}
        {%- elif key == 'address' -%}
            {# For address matching, strip punctuation from the column value #}
            {%- set column_value_expr = "UPPER(REGEXP_REPLACE(CAST(" ~ quoted_col ~ " AS VARCHAR), '[[:punct:]]', ''))" -%}
        {%- else -%}
            {%- set column_value_expr = "CAST(" ~ quoted_col ~ " AS VARCHAR)" -%}
        {%- endif -%}

        {%- if mode == 'PURGE' -%}
            {%- set select_stmt = "select CAST(" ~ recordIdCol ~ " AS VARCHAR) as record_id, upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- elif mode == 'MERGE' -%}
            {%- set select_stmt = "select CAST(" ~ recordIdCol ~ " AS VARCHAR) as record_id, CAST(" ~ sourceIdCol ~ " AS VARCHAR) as source_id , upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ (relation_list | join(', ')) -%}
        {%- endif -%}

        {%- do selects.append(select_stmt) -%}

    {%- endfor -%}

    {%- set match_function_cte = selects | join(" union all ") -%}

with match_function as (
    {{ match_function_cte }}
),
cross_join_data as (
    select
        df0.record_id as record_id1,
        df1.record_id as record_id2,
        {%- if mode == 'MERGE' -%}
            df0.source_id as source_id1,
            df1.source_id as source_id2,
        {%- endif -%}
        df0.column_value as column_value_1,
        df1.column_value as column_value_2,
        df0.column_name as column_name,
        df0.function_name as function_name
    from match_function as df0
    cross join match_function as df1
    where df0.record_id <> df1.record_id
      and df0.function_name = df1.function_name
      and df0.column_name = df1.column_name
    {% if mode == 'MERGE' %}
       and df0.source_id <> df1.source_id
    {% endif %}
),
impose_function_match as (
    select
        record_id1,
        record_id2,
        {%- if mode == 'MERGE' -%}
            source_id1,
            source_id2,
        {%- endif -%}
        column_name,
        function_name,
        case
            when function_name = 'LEVENSHTEIN' then
                (1 - ( LEVENSHTEIN(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
            when function_name = 'EXACT' AND (column_value_1 = REVERSE(column_value_2) AND column_value_2 = REVERSE(column_value_1)) then
                100.0
            when function_name = 'EXACT' AND (column_value_1 <> REVERSE(column_value_2) OR column_value_2 = REVERSE(column_value_1)) then
                0.0
            when function_name = 'EQUALS' AND column_value_1 = column_value_2 then
                100.0
            when function_name = 'EQUALS' AND column_value_1 <> column_value_2 then
                0.0
            else
                {# Fallback to Levenshtein distance #}
                (1 - ( LEVENSHTEIN(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
        end as similarity_score
    from cross_join_data
),
replace_record_ids as (
    select
        GREATEST(record_id1, record_id2) as record_id1,
        LEAST(record_id1, record_id2) as record_id2,
        column_name,
        function_name,
        similarity_score
    from impose_function_match
),
final_output as (
    select
        record_id1,
        record_id2,
        round(avg(similarity_score),2) as similarity_score
    from replace_record_ids
    group by
    record_id1,
    record_id2
)
    {# Include similarity score if True #}
    {%- if includeSimilarityScore -%}
        select
            record_id1,
            record_id2,
            similarity_score from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- else -%}
        select
            record_id1,
            record_id2
            from final_output
        where similarity_score >= {{ matchThresholdPercentage }}
    {%- endif -%}

{%- else -%}
    select * from {{ relation_list | join(', ') }}
{%- endif -%}

{% endmacro %}
