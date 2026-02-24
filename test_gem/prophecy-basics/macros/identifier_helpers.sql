{# Helper macros for proper identifier handling across different database engines #}

{% macro quote_identifier(identifier) %}
    {{ return(adapter.dispatch('quote_identifier', 'prophecy_basics')(identifier)) }}
{% endmacro %}

{% macro default__quote_identifier(identifier) %}
    {% if identifier is string %}
        {% set clean_identifier = identifier | trim %}
        {% if ' ' in clean_identifier or clean_identifier.startswith('`') == false %}
            {% set bt = "`" %}
            {{ bt ~ clean_identifier ~ bt }}
        {% else %}
            {{ clean_identifier }}
        {% endif %}
    {% else %}
        {{ identifier }}
    {% endif %}
{% endmacro %}

{% macro duckdb__quote_identifier(identifier, quote_char='"') %}
    {%- if identifier is string -%}
        {# Single identifier - return quoted string #}
        {{ quote_char }}{{ identifier }}{{ quote_char }}
    {%- elif identifier is iterable -%}
        {# List of identifiers - return list of quoted strings #}
        {%- set quoted_identifiers = [] -%}
        {%- for id in identifier -%}
            {%- do quoted_identifiers.append(quote_char ~ id ~ quote_char) -%}
        {%- endfor -%}
        {{ quoted_identifiers }}
    {%- else -%}
        {# Fallback: treat as string #}
        {{ quote_char }}{{ identifier }}{{ quote_char }}
    {%- endif -%}
{% endmacro %}

{% macro unquote_identifier(identifier) %}
    {{ return(adapter.dispatch('unquote_identifier', 'prophecy_basics')(identifier)) }}
{% endmacro %}

{% macro default__unquote_identifier(identifier) %}
    {% if identifier is string %}
        {% set clean_identifier = identifier | trim %}
        {% if clean_identifier.startswith('`') and clean_identifier.endswith('`') %}
            {{ clean_identifier[1:-1] }}
        {% else %}
            {{ clean_identifier }}
        {% endif %}
    {% else %}
        {{ identifier }}
    {% endif %}
{% endmacro %}

{% macro duckdb__unquote_identifier(identifier) %}
    {%- if identifier is string -%}
        {# Single identifier - unquote if quoted #}
        {%- set clean_identifier = identifier | trim -%}
        {%- if clean_identifier.startswith('"') and clean_identifier.endswith('"') -%}
            {{ clean_identifier[1:-1] }}
        {%- else -%}
            {{ clean_identifier }}
        {%- endif -%}
    {%- elif identifier is iterable -%}
        {# List of identifiers - return list of unquoted strings #}
        {%- set unquoted_identifiers = [] -%}
        {%- for id in identifier -%}
            {%- set clean_id = id | trim -%}
            {%- if clean_id.startswith('"') and clean_id.endswith('"') -%}
                {%- do unquoted_identifiers.append(clean_id[1:-1]) -%}
            {%- else -%}
                {%- do unquoted_identifiers.append(clean_id) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ unquoted_identifiers }}
    {%- else -%}
        {# Fallback: treat as string #}
        {{ identifier }}
    {%- endif -%}
{% endmacro %}

{% macro safe_identifier(identifier) %}
    {{ return(adapter.dispatch('safe_identifier', 'prophecy_basics')(identifier)) }}
{% endmacro %}

{% macro default__safe_identifier(identifier) %}
    {# Returns a safe identifier that can be used in SQL queries #}
    {% if identifier is string %}
        {% set clean_identifier = identifier | trim %}
        {% if ' ' in clean_identifier or clean_identifier.startswith('`') == false %}
            {% set bt = "`" %}
            {{ bt ~ clean_identifier ~ bt }}
        {% else %}
            {{ clean_identifier }}
        {% endif %}
    {% else %}
        {{ identifier }}
    {% endif %}
{% endmacro %}

{% macro duckdb__safe_identifier(identifier, quote_char='"') %}
    {# Returns a safe identifier that can be used in SQL queries #}
    {%- if identifier is string -%}
        {# Single identifier - return quoted string #}
        {{ quote_char }}{{ identifier }}{{ quote_char }}
    {%- elif identifier is iterable -%}
        {# List of identifiers - return list of quoted strings #}
        {%- set quoted_identifiers = [] -%}
        {%- for id in identifier -%}
            {%- do quoted_identifiers.append(quote_char ~ id ~ quote_char) -%}
        {%- endfor -%}
        {{ quoted_identifiers }}
    {%- else -%}
        {# Fallback: treat as string #}
        {{ quote_char }}{{ identifier }}{{ quote_char }}
    {%- endif -%}
{% endmacro %}

{% macro quote_column_list(column_list) %}
    {# Takes a comma-separated string of column names and returns a quoted, comma-separated string #}
    {{ return(adapter.dispatch('quote_column_list', 'prophecy_basics')(column_list)) }}
{% endmacro %}

{% macro default__quote_column_list(column_list) %}
    {%- if column_list == "" or column_list is none -%}
        {{ return("") }}
    {%- else -%}
        {%- set quoted_columns = [] -%}
        {%- set column_list_split = column_list.split(',') | map('trim') | list -%}
        {%- for col in column_list_split -%}
            {%- if col != "" -%}
                {%- do quoted_columns.append(prophecy_basics.quote_identifier(col)) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ return(quoted_columns | join(', ')) }}
    {%- endif -%}
{% endmacro %}

{% macro duckdb__quote_column_list(column_list) %}
    {%- if column_list == "" or column_list is none -%}
        {{ return("") }}
    {%- else -%}
        {%- set quoted_columns = [] -%}
        {%- set column_list_split = column_list.split(',') | map('trim') | list -%}
        {%- for col in column_list_split -%}
            {%- if col != "" -%}
                {%- do quoted_columns.append(prophecy_basics.quote_identifier(col)) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ return(quoted_columns | join(', ')) }}
    {%- endif -%}
{% endmacro %}

{% macro bigquery__quote_column_list(column_list) %}
    {# BigQuery uses backticks for identifiers, same as default #}
    {%- if column_list == "" or column_list is none -%}
        {{ return("") }}
    {%- else -%}
        {%- set quoted_columns = [] -%}
        {%- set column_list_split = column_list.split(',') | map('trim') | list -%}
        {%- for col in column_list_split -%}
            {%- if col != "" -%}
                {%- do quoted_columns.append(prophecy_basics.quote_identifier(col)) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ return(quoted_columns | join(', ')) }}
    {%- endif -%}
{% endmacro %}

{% macro replace_column_safe(text, plain_col, replacement) %}
    {% if text is none or text == '' %}
        {{ return(text) }}
    {% endif %}
    {% if plain_col is none or plain_col == '' %}
        {{ return(text) }}
    {% endif %}
    {% set word_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' %}
    {% set suffixes = [' ', '(', '.', ')', ',', '+', '-', '*', '/', '%', '=', '<', '>', '|', '&'] %}
    {% set col_len = plain_col | length %}
    {% set text_len = text | length %}

    {# Step 1: Find all positions where column name appears in original text #}
    {# Use namespace to maintain state across loop iterations (Jinja2 limitation) #}
    {% set ns = namespace(positions=[], search_pos=0) %}
    {% for _ in range(0, text_len) %}
        {% if ns.search_pos >= text_len %}
            {% break %}
        {% endif %}
        {% set remaining = text[ns.search_pos:] %}
        {% set found_pos = remaining.find(plain_col) %}
        {% if found_pos >= 0 %}
            {% set actual_pos = ns.search_pos + found_pos %}
            {% do ns.positions.append(actual_pos) %}
            {# Advance past the match to avoid finding it again #}
            {% set ns.search_pos = actual_pos + col_len %}
        {% else %}
            {% break %}
        {% endif %}
    {% endfor %}
    {% set positions = ns.positions %}

    {# Step 2: Process each position and build result #}
    {% set result_parts = [] %}
    {% set ns2 = namespace(last_pos=0) %}
    {% for match_pos in positions %}
        {% set before_pos = match_pos - 1 %}
        {% set after_pos = match_pos + col_len %}
        {% set before_char = '' if before_pos < 0 else text[before_pos] %}
        {% set after_char = '' if after_pos >= text_len else text[after_pos] %}
        {# If before_char is '.', it's a qualified column (e.g., payload.YMD) - don't replace #}
        {% set valid_before = match_pos == 0 or (before_char != '.' and before_char not in word_chars) %}
        {% set valid_after = after_pos >= text_len or after_char in suffixes or after_char not in word_chars %}

        {# Add text before this match #}
        {% do result_parts.append(text[ns2.last_pos:match_pos]) %}

        {# Replace if valid, otherwise keep original #}
        {% if valid_before and valid_after %}
            {% do result_parts.append(replacement) %}
        {% else %}
            {% do result_parts.append(plain_col) %}
        {% endif %}

        {% set ns2.last_pos = after_pos %}
    {% endfor %}

    {# Add remaining text after last match #}
    {% do result_parts.append(text[ns2.last_pos:]) %}

    {% set result = result_parts | join('') %}
    {% if result == '' %}
        {% set result = text %}
    {% endif %}
    {{ return(result) }}
{% endmacro %}

{# Helper: Replace all variants of a column name (quoted and unquoted) with replacement, preserving payload references #}
{% macro replace_column_in_expression(text, unquoted_col, replacement, preserve_payload=true) %}
    {% set q_by_adapter = prophecy_basics.quote_identifier(unquoted_col) %}
    {% set backtick_col = "`" ~ unquoted_col ~ "`" %}
    {% set doubleq_col = '"' ~ unquoted_col ~ '"' %}
    {% set singleq_col = "'" ~ unquoted_col ~ "'" %}
    {% set plain_col = unquoted_col %}

    {# Replace quoted variants first (before plain replacement to avoid conflicts) #}
    {% set result = text | replace(backtick_col, replacement) %}
    {% set result = result | replace(q_by_adapter, replacement) %}
    {% set result = result | replace(doubleq_col, replacement) %}
    {% set result = result | replace(singleq_col, replacement) %}
    {# Then replace plain column name (on already-processed text) to catch any remaining instances #}
    {% set result = prophecy_basics.replace_column_safe(result, plain_col, replacement) %}
    {# Restore payload references if requested #}
    {% if preserve_payload %}
        {% set result = result | replace('payload.' ~ replacement, 'payload.' ~ plain_col) %}
    {% endif %}
    {{ return(result) }}
{% endmacro %}

{# Helper: Detect if expression is a simple date string literal and cast it to DATE if needed #}
{% macro column_names_match(name1, name2) %}
    {# Compare two column names with case-insensitive matching for Databricks/DuckDB #}
    {{ return(adapter.dispatch('column_names_match', 'prophecy_basics')(name1, name2)) }}
{% endmacro %}

{% macro default__column_names_match(name1, name2) %}
    {# Default: case-insensitive comparison (for Databricks) #}
    {% set col1 = prophecy_basics.unquote_identifier(name1) | trim | lower %}
    {% set col2 = prophecy_basics.unquote_identifier(name2) | trim | lower %}
    {{ return(col1 == col2) }}
{% endmacro %}

{% macro duckdb__column_names_match(name1, name2) %}
    {# DuckDB: case-insensitive comparison #}
    {% set col1 = prophecy_basics.unquote_identifier(name1) | trim | lower %}
    {% set col2 = prophecy_basics.unquote_identifier(name2) | trim | lower %}
    {{ return(col1 == col2) }}
{% endmacro %}

{% macro databricks__column_names_match(name1, name2) %}
    {# Databricks: case-insensitive comparison #}
    {% set col1 = prophecy_basics.unquote_identifier(name1) | trim | lower %}
    {% set col2 = prophecy_basics.unquote_identifier(name2) | trim | lower %}
    {{ return(col1 == col2) }}
{% endmacro %}

{% macro spark__column_names_match(name1, name2) %}
    {# Spark: case-insensitive comparison #}
    {% set col1 = prophecy_basics.unquote_identifier(name1) | trim | lower %}
    {% set col2 = prophecy_basics.unquote_identifier(name2) | trim | lower %}
    {{ return(col1 == col2) }}
{% endmacro %}

{% macro cast_date_if_needed(expr) %}
    {% if expr is none or expr == '' %}
        {{ return(expr) }}
    {% endif %}

    {% set expr_trimmed = expr | trim %}
    {% set is_date_string = false %}
    {% set date_str_to_cast = expr %}

    {# Check if it matches date pattern (YYYY-MM-DD) #}
    {% set looks_like_date = false %}
    {% if expr_trimmed.startswith("'") and expr_trimmed.endswith("'") %}
        {% set date_str = expr_trimmed[1:-1] %}
        {% if date_str | length == 10 and date_str[4] == '-' and date_str[7] == '-' %}
            {% set looks_like_date = true %}
        {% endif %}
    {% elif expr_trimmed.startswith('"') and expr_trimmed.endswith('"') %}
        {% set date_str = expr_trimmed[1:-1] %}
        {% if date_str | length == 10 and date_str[4] == '-' and date_str[7] == '-' %}
            {% set looks_like_date = true %}
        {% endif %}
    {% elif expr_trimmed | length == 10 and expr_trimmed[4] == '-' and expr_trimmed[7] == '-' %}
        {% set looks_like_date = true %}
    {% endif %}

    {% if looks_like_date %}
        {% set has_operators = '(' in expr_trimmed or ')' in expr_trimmed or '+' in expr_trimmed or '*' in expr_trimmed or '/' in expr_trimmed or 'payload.' in expr_trimmed %}
        {% if not expr_trimmed.startswith("'") and not expr_trimmed.startswith('"') %}
            {% if ' ' in expr_trimmed or expr_trimmed.count('-') > 2 %}
                {% set has_operators = true %}
            {% endif %}
        {% endif %}

        {% if not has_operators %}
            {% set is_date_string = true %}
            {% if expr_trimmed.startswith("'") or expr_trimmed.startswith('"') %}
                {% set date_str_to_cast = expr %}
            {% else %}
                {% set date_str_to_cast = "'" ~ expr_trimmed ~ "'" %}
            {% endif %}
        {% endif %}
    {% endif %}

    {% if is_date_string %}
        {{ return('CAST(' ~ date_str_to_cast ~ ' AS DATE)') }}
    {% else %}
        {{ return(expr) }}
    {% endif %}
{% endmacro %}

{% macro cast_timestamp_if_needed(expr) %}
    {% if expr is none or expr == '' %}
        {{ return(expr) }}
    {% endif %}

    {% set expr_trimmed = expr | trim %}
    {% set is_timestamp_string = false %}
    {% set timestamp_str_to_cast = expr %}

    {# First check if it matches timestamp pattern (YYYY-MM-DD HH:MM:SS) #}
    {% set looks_like_timestamp = false %}
    {% set inner_timestamp_str = expr_trimmed %}
    {% set is_quoted = false %}

    {# Extract inner string if quoted #}
    {% if expr_trimmed.startswith("'") and expr_trimmed.endswith("'") %}
        {% set inner_timestamp_str = expr_trimmed[1:-1] | trim %}
        {% set is_quoted = true %}
    {% elif expr_trimmed.startswith('"') and expr_trimmed.endswith('"') %}
        {% set inner_timestamp_str = expr_trimmed[1:-1] | trim %}
        {% set is_quoted = true %}
    {% else %}
        {% set inner_timestamp_str = expr_trimmed | trim %}
    {% endif %}

    {# Check if inner string matches timestamp pattern (19 chars: YYYY-MM-DD HH:MM:SS) #}
    {% if inner_timestamp_str | length == 19 %}
        {% if inner_timestamp_str[4] == '-' and inner_timestamp_str[7] == '-' and inner_timestamp_str[10] == ' ' and inner_timestamp_str[13] == ':' and inner_timestamp_str[16] == ':' %}
            {% set is_valid = true %}
            {% for i in [0,1,2,3,5,6,8,9,11,12,14,15,17,18] %}
                {% if inner_timestamp_str[i] not in '0123456789' %}
                    {% set is_valid = false %}
                    {% break %}
                {% endif %}
            {% endfor %}
            {% if is_valid %}
                {% set looks_like_timestamp = true %}
            {% endif %}
        {% endif %}
    {% endif %}

    {% if looks_like_timestamp %}
        {% set has_operators = '(' in expr_trimmed or ')' in expr_trimmed or '+' in expr_trimmed or '*' in expr_trimmed or '/' in expr_trimmed or 'payload.' in expr_trimmed %}
        {% if not expr_trimmed.startswith("'") and not expr_trimmed.startswith('"') %}
            {# For unquoted strings, check if there are extra spaces (other than the one at position 10) or extra operators #}
            {% if expr_trimmed.count(' ') > 1 or expr_trimmed.count('-') > 2 or expr_trimmed.count(':') > 2 %}
                {% set has_operators = true %}
            {% endif %}
        {% endif %}

        {% if not has_operators %}
            {% set is_timestamp_string = true %}
            {% if is_quoted %}
                {# Already quoted, use as-is #}
                {% set timestamp_str_to_cast = expr %}
            {% else %}
                {# Not quoted, add quotes #}
                {% set timestamp_str_to_cast = "'" ~ inner_timestamp_str ~ "'" %}
            {% endif %}
        {% endif %}
    {% endif %}

    {% if is_timestamp_string %}
        {{ return('CAST(' ~ timestamp_str_to_cast ~ ' AS TIMESTAMP)') }}
    {% else %}
        {% set date_result = prophecy_basics.cast_date_if_needed(expr) %}
        {{ return(date_result) }}
    {% endif %}
{% endmacro %}
