{# ============================================ #}
{# SQL String Escaping Helper Macros           #}
{# ============================================ #}

{# Main dispatch macro for escaping SQL strings #}
{% macro escape_sql_string(text, escape_backslashes=true) %}
    {{ return(adapter.dispatch('escape_sql_string', 'prophecy_basics')(text, escape_backslashes)) }}
{% endmacro %}

{# Main dispatch macro for escaping regex patterns #}
{% macro escape_regex_pattern(pattern, escape_backslashes=true) %}
    {{ return(adapter.dispatch('escape_regex_pattern', 'prophecy_basics')(pattern, escape_backslashes)) }}
{% endmacro %}

{# ============================================ #}
{# DEFAULT (Databricks/Spark) Implementation   #}
{# ============================================ #}
{% macro default__escape_sql_string(text, escape_backslashes=true) %}
    {# 
    Escapes special characters in SQL string literals for Databricks/Spark.
    Handles backslashes and single quotes in the correct order to avoid double-escaping issues.
    
    Args:
        text: The string to escape
        escape_backslashes: Whether to escape backslashes (default: true for Databricks/Spark)
    
    Returns:
        Properly escaped string safe for use in SQL string literals
    #}
    {%- if text is not string -%}
        {{ return(text) }}
    {%- endif -%}
    
    {%- if escape_backslashes -%}
        {# Escape backslashes first (so theyre protected before we escape quotes) #}
        {%- set escaped = text | replace("\\", "\\\\") -%}
    {%- else -%}
        {%- set escaped = text -%}
    {%- endif -%}
    
    {# Then escape single quotes (SQL standard: '' represents a single quote in a string literal) #}
    {%- set escaped = escaped | replace("'", "''") -%}
    
    {{ return(escaped) }}
{% endmacro %}

{% macro default__escape_regex_pattern(pattern, escape_backslashes=true) %}
    {# Regex patterns use the same escaping as SQL strings #}
    {{ return(prophecy_basics.escape_sql_string(pattern, escape_backslashes)) }}
{% endmacro %}

{# ============================================ #}
{# BIGQUERY Implementation                     #}
{# ============================================ #}
{# BigQuery uses the same escaping logic as default (Databricks/Spark) #}
{% macro bigquery__escape_sql_string(text, escape_backslashes=true) %}
    {{ return(prophecy_basics.default__escape_sql_string(text, escape_backslashes)) }}
{% endmacro %}

{% macro bigquery__escape_regex_pattern(pattern, escape_backslashes=true) %}
    {{ return(prophecy_basics.escape_sql_string(pattern, escape_backslashes)) }}
{% endmacro %}

{# ============================================ #}
{# SNOWFLAKE Implementation                    #}
{# ============================================ #}
{# Snowflake uses the same escaping logic as default (Databricks/Spark) #}
{% macro snowflake__escape_sql_string(text, escape_backslashes=true) %}
    {{ return(prophecy_basics.default__escape_sql_string(text, escape_backslashes)) }}
{% endmacro %}

{% macro snowflake__escape_regex_pattern(pattern, escape_backslashes=true) %}
    {{ return(prophecy_basics.escape_sql_string(pattern, escape_backslashes)) }}
{% endmacro %}

{# ============================================ #}
{# DUCKDB Implementation                       #}
{# ============================================ #}
{% macro duckdb__escape_sql_string(text, escape_backslashes=false) %}
    {# 
    Escapes special characters in SQL string literals for DuckDB.
    DuckDB doesn't require backslash escaping in regex patterns.
    
    Args:
        text: The string to escape
        escape_backslashes: Whether to escape backslashes (default: false for DuckDB regex)
    
    Returns:
        Properly escaped string safe for use in DuckDB SQL string literals
    #}
    {%- if text is not string -%}
        {{ return(text) }}
    {%- endif -%}
    
    {%- if escape_backslashes -%}
        {# Escape backslashes first (so they're protected before we escape quotes) #}
        {%- set escaped = text | replace("\\", "\\\\") -%}
    {%- else -%}
        {%- set escaped = text -%}
    {%- endif -%}
    
    {# Then escape single quotes (SQL standard: '' represents a single quote in a string literal) #}
    {%- set escaped = escaped | replace("'", "''") -%}
    
    {{ return(escaped) }}
{% endmacro %}

{% macro duckdb__escape_regex_pattern(pattern, escape_backslashes=false) %}
    {# Regex patterns use the same escaping as SQL strings #}
    {{ return(prophecy_basics.escape_sql_string(pattern, escape_backslashes)) }}
{% endmacro %}

