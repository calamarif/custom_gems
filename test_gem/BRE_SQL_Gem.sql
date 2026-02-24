{% macro BRE_SQL_Gem(relation_name, schema, rules) %}

    {# ── 1. Normalise relation_name to a list ─────────────────────────────── #}
    {% set rel_list = relation_name
        if (relation_name is iterable and relation_name is not string)
        else [relation_name] %}

    {# ── 2. Collect existing column names from input schema ───────────────── #}
    {% set input_col_names = [] %}
    {% for col in schema %}
        {% do input_col_names.append(col.name) %}
    {% endfor %}

    {# ── 3. Group rules by output_column ─────────────────────────────────── #}
    {% set grouped = {} %}
    {% for rule in rules %}
        {% set out_col = rule.output_column %}
        {% if out_col not in grouped %}
            {% do grouped.update({out_col: []}) %}
        {% endif %}
        {% do grouped[out_col].append(rule) %}
    {% endfor %}

    {# ── 4. Identify truly new output columns (not in input schema) ───────── #}
    {% set new_output_cols = [] %}
    {% for out_col in grouped.keys() %}
        {% if out_col not in input_col_names %}
            {% do new_output_cols.append(out_col) %}
        {% endif %}
    {% endfor %}

    {# ── 5. Build the SELECT column list ─────────────────────────────────── #}
    {% set select_cols = [] %}

    {# Existing columns — wrap in CASE WHEN if they appear as an output column #}
    {% for col in schema %}
        {% set col_name = col.name %}
        {% if col_name in grouped %}
            {%- set when_clauses = [] -%}
            {%- for rule in grouped[col_name] -%}
                {%- set in_col  = rule.input_column | default('') -%}
                {%- set cond    = rule.rule_condition | trim -%}
                {%- set cond_lc = cond | lower -%}
                {%- if cond[:1] in ['>', '<', '=', '!']
                    or cond_lc.startswith('like ')
                    or cond_lc.startswith('in (')
                    or cond_lc.startswith('between ')
                    or cond_lc.startswith('is ')
                -%}
                    {%- set full_cond = in_col ~ ' ' ~ cond -%}
                {%- else -%}
                    {%- set full_cond = cond -%}
                {%- endif -%}
                {%- do when_clauses.append('WHEN ' ~ full_cond ~ ' THEN ' ~ rule.rule_output_value) -%}
            {%- endfor -%}
            {% do select_cols.append('CASE ' ~ (when_clauses | join(' ')) ~ ' ELSE ' ~ col_name ~ ' END AS ' ~ col_name) %}
        {% else %}
            {% do select_cols.append(col_name) %}
        {% endif %}
    {% endfor %}

    {# New (appended) output columns #}
    {% for col_name in new_output_cols %}
        {%- set when_clauses = [] -%}
        {%- for rule in grouped[col_name] -%}
            {%- set in_col  = rule.input_column | default('') -%}
            {%- set cond    = rule.rule_condition | trim -%}
            {%- set cond_lc = cond | lower -%}
            {%- if cond[:1] in ['>', '<', '=', '!']
                or cond_lc.startswith('like ')
                or cond_lc.startswith('in (')
                or cond_lc.startswith('between ')
                or cond_lc.startswith('is ')
            -%}
                {%- set full_cond = in_col ~ ' ' ~ cond -%}
            {%- else -%}
                {%- set full_cond = cond -%}
            {%- endif -%}
            {%- do when_clauses.append('WHEN ' ~ full_cond ~ ' THEN ' ~ rule.rule_output_value) -%}
        {%- endfor -%}
        {% do select_cols.append('CASE ' ~ (when_clauses | join(' ')) ~ ' ELSE NULL END AS ' ~ col_name) %}
    {% endfor %}

    {# ── 6. Emit the query ────────────────────────────────────────────────── #}
    {% if select_cols | length > 0 %}
    SELECT
        {{ select_cols | join(',\n        ') }}
    FROM {{ rel_list | join(', ') }}
    {% else %}
    SELECT *
    FROM {{ rel_list | join(', ') }}
    {% endif %}

{% endmacro %}
