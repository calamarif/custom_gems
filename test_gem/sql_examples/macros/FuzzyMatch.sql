{% macro FuzzyMatch(
    relation,
    mode,
    sourceIdCol,
    recordIdCol,
    matchFields,
    matchThresholdPercentage=0,
    includeSimilarityScore=False
    ) %}

{%- if mode == 'PURGE' or mode == 'MERGE' -%}
    {# Build individual SELECT statements for each match field #}
    {%- set selects = [] -%}
    {%- for key, columns in matchFields.items() -%}
        {# Decide on the function name based on the key #}
        {%- if key == 'custom' -%}
            {%- set func_name = 'EDITDISTANCE' -%}
        {%- elif key == 'name' -%}
            {%- set func_name = 'JAROWINKLER_SIMILARITY' -%}
        {%- elif key == 'phone' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- elif key == 'address' -%}
            {%- set func_name = 'JAROWINKLER_SIMILARITY' -%}
        {%- elif key == 'exact' -%}
            {%- set func_name = 'EXACT' -%}
        {%- elif key == 'equals' -%}
            {%- set func_name = 'EQUALS' -%}
        {%- else -%}
            {%- set func_name = 'JAROWINKLER_SIMILARITY' -%}
        {%- endif -%}

        {%- for col in columns -%}
            {%- if key == 'custom' -%}
                {# For custom matching, strip punctuation from the column value #}
                {%- set column_value_expr = "UPPER(REGEXP_REPLACE(" ~ col ~ "::string, '[[:punct:]]', ''))" -%}
            {%- elif key == 'name' -%}
                {# For name matching, strip punctuation from the column value #}
                {%- set column_value_expr = "UPPER(REGEXP_REPLACE(" ~ col ~ "::string, '[[:punct:]]', ''))" -%}
            {%- elif key == 'address' -%}
                {# For address matching, strip punctuation from the column value #}
                {%- set column_value_expr = "UPPER(REGEXP_REPLACE(" ~ col ~ "::string, '[[:punct:]]', ''))" -%}
            {%- else -%}
                {%- set column_value_expr = col ~ "::string" -%}
            {%- endif -%}

            {%- if mode == 'PURGE' -%}
                {%- set select_stmt = "select " ~ recordIdCol ~ "::string as record_id, upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ relation -%}
            {%- elif mode == 'MERGE' -%}
                {%- set select_stmt = "select " ~ recordIdCol ~ "::string as record_id, " ~ sourceIdCol ~ "::string as source_id, upper('" ~ col ~ "') as column_name, " ~ column_value_expr ~ " as column_value, '" ~ func_name ~ "' as function_name from " ~ relation -%}
            {%- endif -%}

            {%- do selects.append(select_stmt) -%}
        {%- endfor -%}

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
            when function_name = 'EDITDISTANCE' then
                (1 - ( EDITDISTANCE(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
            when function_name = 'JAROWINKLER_SIMILARITY' then
                JAROWINKLER_SIMILARITY(column_value_1, column_value_2)
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
                (1 - ( EDITDISTANCE(column_value_1, column_value_2) / GREATEST(length(column_value_1), length(column_value_2)))) * 100
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
    select * from {{ relation }}
{%- endif -%}

{% endmacro %}