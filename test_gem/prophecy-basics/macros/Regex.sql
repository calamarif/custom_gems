{% macro Regex(relation_name,
    parseColumns,
    schema='',
    selectedColumnName='',
    regexExpression='',
    outputMethod='replace',
    caseInsensitive=true,
    allowBlankTokens=false,
    replacementText='',
    copyUnmatchedText=false,
    tokenizeOutputMethod='splitColumns',
    noOfColumns=3,
    extraColumnsHandling='dropExtraWithoutWarning',
    outputRootName='regex_col',
    matchColumnName='regex_match',
    errorIfNotMatched=false) -%}
    {{ return(adapter.dispatch('Regex', 'prophecy_basics')(relation_name,
    parseColumns,
    schema,
    selectedColumnName,
    regexExpression,
    outputMethod,
    caseInsensitive,
    allowBlankTokens,
    replacementText,
    copyUnmatchedText,
    tokenizeOutputMethod,
    noOfColumns,
    extraColumnsHandling,
    outputRootName,
    matchColumnName,
    errorIfNotMatched)) }}
{% endmacro %}

{# ============================================ #}
{# DEFAULT (Spark/Databricks) Implementation   #}
{# ============================================ #}
{% macro default__Regex(
    relation_name,
    parseColumns,
    schema='',
    selectedColumnName='',
    regexExpression='',
    outputMethod='replace',
    caseInsensitive=true,
    allowBlankTokens=false,
    replacementText='',
    copyUnmatchedText=false,
    tokenizeOutputMethod='splitColumns',
    noOfColumns=3,
    extraColumnsHandling='dropExtraWithoutWarning',
    outputRootName='regex_col',
    matchColumnName='regex_match',
    errorIfNotMatched=false
) %}

{# Input validation #}
{% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
{%- if not selectedColumnName or selectedColumnName == '' -%}
    {{ log("ERROR: selectedColumnName parameter is required and cannot be empty", info=True) }}
    select 'ERROR: selectedColumnName parameter is required' as error_message
{%- elif not regexExpression or regexExpression == '' -%}
    {{ log("ERROR: regexExpression parameter is required and cannot be empty", info=True) }}
    select 'ERROR: regexExpression parameter is required' as error_message
{%- elif not relation_list or relation_list == '' -%}
    {{ log("ERROR: relation_name parameter is required and cannot be empty", info=True) }}
    select 'ERROR: relation_name parameter is required' as error_message
{%- else -%}

{# Parse parseColumns if its a string #}
{%- if parseColumns is string -%}
    {%- set parsed_columns = fromjson(parseColumns) -%}
{%- else -%}
    {%- set parsed_columns = parseColumns -%}
{%- endif -%}

{%- set output_method_lower = outputMethod | lower -%}
{# Use helper macro for proper SQL string escaping #}
{%- set escaped_regex = prophecy_basics.escape_regex_pattern(regexExpression, escape_backslashes=true) -%}
{%- set regex_pattern = ('(?i)' if caseInsensitive else '') ~ escaped_regex -%}
{# For replacement text, escape SQL string literals #}
{%- set escaped_replacement = prophecy_basics.escape_sql_string(replacementText, escape_backslashes=true) -%}
{%- set source_table = relation_list | join(', ') -%}
{%- set extra_handling_lower = extraColumnsHandling | lower -%}
{%- set quoted_selected = prophecy_basics.quote_identifier(selectedColumnName) -%}

{%- if output_method_lower == 'replace' -%}
    select
        *,
        {% if copyUnmatchedText %}
        case
            when {{ quoted_selected }} rlike '{{ regex_pattern }}' then
                regexp_replace({{ quoted_selected }}, '{{ regex_pattern }}', '{{ escaped_replacement }}')
            else {{ quoted_selected }}
        end as {{ prophecy_basics.quote_identifier(selectedColumnName ~ '_replaced') }}
        {% else %}
        regexp_replace({{ quoted_selected }}, '{{ regex_pattern }}', '{{ escaped_replacement }}') as {{ prophecy_basics.quote_identifier(selectedColumnName ~ '_replaced') }}
        {% endif %}
    from {{ source_table }}

{%- elif output_method_lower == 'parse' -%}
    {%- if parsed_columns and parsed_columns|length > 0 -%}
        select
            *
            {%- for config in parsed_columns -%}
                {%- if config and config.columnName -%}
                    {%- set col_name = config.columnName -%}
                    {%- set col_type = config.dataType | default('string') -%}
                    {%- set group_index = loop.index -%}
            ,
            {%- if col_type|lower == 'string' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }})
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'int' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as int)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'bigint' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as bigint)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'double' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as double)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'bool' or col_type|lower == 'boolean' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as boolean)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'date' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as date)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- elif col_type|lower == 'datetime' or col_type|lower == 'timestamp' %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else cast(regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) as timestamp)
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- else %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }}) = '' then null
                else regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ group_index }})
            end as {{ prophecy_basics.quote_identifier(col_name) }}
            {%- endif %}
                {%- endif -%}
            {%- endfor %}
        from {{ source_table }}
    {%- else -%}
        select 'ERROR: parseColumns array is empty after parsing' as error_message
    {%- endif -%}

{%- elif output_method_lower == 'tokenize' -%}
    {%- set tokenize_method_lower = tokenizeOutputMethod | lower -%}
    {%- if tokenize_method_lower == 'splitcolumns' -%}
        {# For tokenize/splitColumns, always use regexp_extract_all to get all matches #}
        {# This works regardless of whether the pattern has capturing groups #}
        {# For example, ([^,]+) will match all comma-separated values #}
        with extracted_array as (
            select
                *,
                regexp_extract_all({{ quoted_selected }}, '{{ regex_pattern }}') as regex_matches
            from {{ source_table }}
        )
        {%- if extra_handling_lower == 'dropextrawitherror' -%}
            {# Check for extra matches and raise error if found #}
            select
                * except (regex_matches)
                {%- for i in range(1, noOfColumns + 1) %},
                case
                    when size(regex_matches) > {{ noOfColumns }} then
                        cast(concat('ERROR: Found ', cast(size(regex_matches) as string), ' regex matches, but only ', cast({{ noOfColumns }} as string), ' columns expected') as string)
                    when size(regex_matches) = 0 then cast(null as string)
                    when size(regex_matches) < {{ i }} then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    when regex_matches[{{ i - 1 }}] = '' then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    else regex_matches[{{ i - 1 }}]
                end as {{ prophecy_basics.quote_identifier(outputRootName ~ i) }}
                {%- endfor %}
            from extracted_array
        {%- elif extra_handling_lower == 'saveallremainingtext' -%}
            {# Save all remaining text into last generated column #}
            select
                * except (regex_matches)
                {%- for i in range(1, noOfColumns) %},
                case
                    when size(regex_matches) = 0 then cast(null as string)
                    when size(regex_matches) < {{ i }} then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    when regex_matches[{{ i - 1 }}] = '' then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    else regex_matches[{{ i - 1 }}]
                end as {{ prophecy_basics.quote_identifier(outputRootName ~ i) }}
                {%- endfor %},
                {# Last column: concatenate all matches from noOfColumns onwards #}
                case
                    when size(regex_matches) = 0 then cast(null as string)
                    when size(regex_matches) < {{ noOfColumns }} then
                        case
                            when regex_matches[{{ noOfColumns - 1 }}] = '' then
                                case when {{ allowBlankTokens }} then '' else cast(null as string) end
                            else regex_matches[{{ noOfColumns - 1 }}]
                        end
                    else
                        {# Concatenate remaining matches using array_join and slice #}
                        array_join(
                            slice(regex_matches, {{ noOfColumns }}, greatest(size(regex_matches) - {{ noOfColumns }} + 1, 0)),
                            ''
                        )
                end as {{ prophecy_basics.quote_identifier(outputRootName ~ noOfColumns) }}
            from extracted_array
        {%- else -%}
            {# dropExtraWithoutWarning: drop extra columns silently #}
            select
                * except (regex_matches)
                {%- for i in range(1, noOfColumns + 1) %},
                case
                    when size(regex_matches) = 0 then cast(null as string)
                    when size(regex_matches) < {{ i }} then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    when regex_matches[{{ i - 1 }}] = '' then
                        case when {{ allowBlankTokens }} then '' else cast(null as string) end
                    else regex_matches[{{ i - 1 }}]
                end as {{ prophecy_basics.quote_identifier(outputRootName ~ i) }}
                {%- endfor %}
            from extracted_array
        {%- endif -%}

    {%- elif tokenize_method_lower == 'splitrows' -%}
        with regex_matches as (
            select
                *,
                regexp_extract_all({{ quoted_selected }}, '{{ regex_pattern }}') as split_tokens
            from {{ source_table }}
        ),
        exploded_tokens as (
            select
                * except (split_tokens),
                explode(split_tokens) as token_value_new
            from regex_matches
        ),
        numbered_tokens as (
            select
                *,
                token_value_new,
                row_number() over (partition by {{ quoted_selected }} order by monotonically_increasing_id()) as token_position
            from exploded_tokens
        )
        select
            * except (token_value_new),
            token_value_new as {{ prophecy_basics.quote_identifier(outputRootName) }},
            token_position as token_sequence
        from numbered_tokens
        {% if not allowBlankTokens %}
        where token_value_new != '' and token_value_new is not null
        {% endif %}

    {%- else -%}
        select
            *,
            {% for i in range(1, noOfColumns + 1) %}
            case
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', 0) = '' then null
                when regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ i }}) = '' then null
                else regexp_extract({{ quoted_selected }}, '{{ regex_pattern }}', {{ i }})
            end as {{ prophecy_basics.quote_identifier(outputRootName ~ i) }}
            {%- if not loop.last -%},{%- endif -%}
            {% endfor %}
        from {{ source_table }}
    {%- endif -%}

{%- elif output_method_lower == 'match' -%}
    select
        *,
        case
            when {{ quoted_selected }} is null then 0
            when {{ quoted_selected }} rlike '{{ regex_pattern }}' then 1
            else 0
        end as {{ prophecy_basics.quote_identifier(matchColumnName) }}
    from {{ source_table }}
    {% if errorIfNotMatched %}
    where {{ quoted_selected }} rlike '{{ regex_pattern }}'
    {% endif %}

{%- else -%}
    select 'ERROR: Unknown outputMethod "{{ outputMethod }}"' as error_message

{%- endif -%}

{%- endif -%}

{% endmacro %}
