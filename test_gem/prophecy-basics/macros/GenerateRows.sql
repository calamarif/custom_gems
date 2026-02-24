{% macro GenerateRows(relation_name,
    schema,
    init_expr,
    condition_expr,
    loop_expr,
    column_name,
    max_rows,
    force_mode) -%}
    {{ return(adapter.dispatch('GenerateRows', 'prophecy_basics')(relation_name,
    schema,
    init_expr,
    condition_expr,
    loop_expr,
    column_name,
    max_rows,
    force_mode)) }}
{% endmacro %}

{% macro default__GenerateRows(
    relation_name=None,
    schema='[]',
    init_expr='1',
    condition_expr='value <= 10',
    loop_expr='value + 1',
    column_name='value',
    max_rows=100000,
    force_mode='recursive'
) %}
    {% if init_expr is none or init_expr == '' %}
        {% do exceptions.raise_compiler_error("init_expr is required") %}
    {% endif %}

    {% if condition_expr is none or condition_expr == '' %}
        {% do exceptions.raise_compiler_error("condition_expr is required") %}
    {% endif %}

    {% if loop_expr is none or loop_expr == '' %}
        {% do exceptions.raise_compiler_error("loop_expr is required") %}
    {% endif %}

    {# max_rows defaults to 100 if not provided (set by apply function) #}
    {% if max_rows is none or max_rows == '' %}
        {% set max_rows = 100 %}
    {% endif %}

    {% set alias = "src" %}
    {% set relation_tables = (relation_name if relation_name is iterable and relation_name is not string else [relation_name]) | join(', ')  %}

    {# Use provided helper to unquote the provided column name #}
    {% set unquoted_col = prophecy_basics.unquote_identifier(column_name) | trim %}
    {% set internal_col = "__gen_" ~ unquoted_col | replace(' ', '_') %}

    {# Check if column exists in source schema #}
    {% set column_exists_in_schema = prophecy_basics.column_exists_in_schema(schema, column_name) %}

    {# Detect if init_expr is a simple date or timestamp string literal and cast it if needed #}
    {% set init_select = prophecy_basics.cast_timestamp_if_needed(init_expr) %}

    {# Normalize user-supplied condition expression quotes if they used double quotes only #}
    {% if '"' in condition_expr and "'" not in condition_expr %}
        {% set condition_expr_sql = condition_expr.replace('"', "'") %}
    {% else %}
        {% set condition_expr_sql = condition_expr %}
    {% endif %}

    {# --- Replace the target column in condition expression to reference the internal column --- #}
    {% set condition_expr_sql = prophecy_basics.replace_column_in_expression(condition_expr_sql, unquoted_col, internal_col, preserve_payload=true) %}

    {# --- Replace the target column in loop expression to reference gen.<internal_col> in recursive step --- #}
    {# Properly quote internal_col when creating gen. reference (e.g., gen.`__gen_date_val` not gen.__gen_date_val) #}
    {# Use backticks for internal columns to ensure proper SQL syntax #}
    {% set quoted_internal_col = "`" ~ internal_col ~ "`" %}
    {% set loop_expr_replaced = prophecy_basics.replace_column_in_expression(loop_expr, unquoted_col, 'gen.' ~ quoted_internal_col, preserve_payload=false) %}

    {# Use adapter-safe quoting for EXCEPT column #}
    {% set except_col = prophecy_basics.safe_identifier(unquoted_col) %}

    {# --- Build recursion_condition: same condition but referencing the previous iteration (gen.__gen_col) --- #}
    {% set _rec_tmp = condition_expr_sql %}
    {% set _rec_tmp = _rec_tmp | replace(internal_col, 'gen.' ~ quoted_internal_col) %}
    {# Note: condition_expr_sql already has internal_col substituted; above we switch to gen.internal_col for recursive WHERE #}
    {% set recursion_condition = _rec_tmp %}

    {# --- Determine output alias: quote it if it contains non [A-Za-z0-9_] characters (no regex used) --- #}
    {% set allowed = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' %}
    {% set specials = [] %}
    {% for ch in unquoted_col %}
        {% if ch not in allowed %}
            {% do specials.append(ch) %}
        {% endif %}
    {% endfor %}
    {% if specials | length > 0 %}
        {% set output_col_alias = prophecy_basics.quote_identifier(unquoted_col) %}
    {% else %}
        {% set output_col_alias = unquoted_col %}
    {% endif %}

    {% if relation_tables %}
        with recursive gen as (
            -- base case: one row per input record
            select
                struct({{ alias }}.*) as payload,
                {{ init_select }} as {{ internal_col }},
                1 as _iter
            from {{ relation_tables }} {{ alias }}

            union all

            -- recursive step
            select
                gen.payload as payload,
                {{ loop_expr_replaced }} as {{ internal_col }},
                _iter + 1
            from gen
            where _iter < {{ max_rows | int }}
              and ({{ recursion_condition }})
        )
        select
            -- Exclude the original column from payload only if it exists in the source schema
            {% if column_exists_in_schema %}
            payload.* EXCEPT ({{ except_col }}),
            {% else %}
            payload.*,
            {% endif %}
            {{ internal_col }} as {{ output_col_alias }}
        from gen
        where {{ condition_expr_sql }}
    {% else %}
        with recursive gen as (
            select {{ init_select }} as {{ internal_col }}, 1 as _iter
            union all
            select
                {{ loop_expr_replaced }} as {{ internal_col }},
                _iter + 1
            from gen
            where _iter < {{ max_rows | int }}
              and ({{ recursion_condition }})
        )
        select {{ internal_col }} as {{ output_col_alias }}
        from gen
        where {{ condition_expr_sql }}
    {% endif %}
{% endmacro %}

{% macro bigquery__GenerateRows(
    relation_name=None,
    schema='[]',
    init_expr='1',
    condition_expr='value <= 10',
    loop_expr='value + 1',
    column_name='value',
    max_rows=100000,
    force_mode='recursive'
) %}
    {# Validate required parameters #}
    {% if init_expr is none or init_expr == '' or condition_expr is none or condition_expr == '' or loop_expr is none or loop_expr == '' or column_name is none or column_name == '' %}
        select 'ERROR: init_expr, condition_expr, loop_expr, and column_name are required and cannot be empty' as error_message
    {% else %}
    {# max_rows defaults to 100 if not provided (set by apply function) #}
    {% if max_rows is none or max_rows == '' %}
        {% set max_rows = 100 %}
    {% endif %}

    {% set alias = "src" %}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {% set relation_tables = relation_list | join(', ') if relation_list and relation_list|length > 0 and relation_list[0] else '' %}
    {% set unquoted_col = prophecy_basics.unquote_identifier(column_name) | trim %}
    {% set output_col_alias = prophecy_basics.quote_identifier(unquoted_col) %}
    {% set internal_col = "__gen_" ~ unquoted_col | replace(' ', '_') %}
    {% set array_elem_alias = internal_col %}

    {# Extract init value - evaluate init_expr by replacing column_name with 1 #}
    {% set init_expr_eval = init_expr | replace(column_name, '1') | trim %}
    {% set init_value = init_expr_eval | int %}

    {# Extract step value - evaluate loop_expr by replacing column_name with 0 #}
    {% set step_expr = loop_expr | replace(column_name, '0') | trim %}
    {% set step_value = step_expr | int %}

    {# Use GENERATE_ARRAY with step - always use array element alias #}
    {% set computed_expr = array_elem_alias %}
    {% set condition_expr_sql = condition_expr | replace(column_name, array_elem_alias) %}
    {% set use_step = true %}
    {% set array_step = step_value %}

    {% if relation_tables %}
        {# With source table: generate sequence for each input row #}
        with source_data as (
            select {{ alias }}.*
            from {{ relation_tables }} {{ alias }}
        ),
        gen as (
            select
                source_data.*,
                {{ computed_expr }} as {{ output_col_alias }}
            from source_data
            cross join unnest(
                generate_array({{ init_value }}, {{ init_value + max_rows | int * array_step }}, {{ array_step }})
            ) as {{ array_elem_alias }}
            where {{ condition_expr_sql }}
            limit {{ max_rows | int }}
        )
        select gen.*
        from gen
    {% else %}
        {# Without source table: simple sequence generation #}
        with gen as (
            select {{ computed_expr }} as {{ output_col_alias }}
            from unnest(
                {% if use_step %}
                    generate_array({{ init_value }}, {{ init_value + max_rows | int * array_step }}, {{ array_step }})
                {% else %}
                    generate_array(0, {{ max_rows | int }} - 1)
                {% endif %}
            ) as {% if use_step %}{{ array_elem_alias }}{% else %} _iter {% endif %}
            where {{ condition_expr_sql }}
            limit {{ max_rows | int }}
        )
        select {{ output_col_alias }}
        from gen
    {% endif %}
    {% endif %}
{% endmacro %}

{% macro duckdb__GenerateRows(
    relation_name=None,
    schema='[]',
    init_expr='1',
    condition_expr='value <= 10',
    loop_expr='value + 1',
    column_name='value',
    max_rows=100000,
    force_mode='recursive'
) %}
    {% if init_expr is none or init_expr == '' %}
        {% do exceptions.raise_compiler_error("init_expr is required") %}
    {% endif %}

    {% if condition_expr is none or condition_expr == '' %}
        {% do exceptions.raise_compiler_error("condition_expr is required") %}
    {% endif %}

    {% if loop_expr is none or loop_expr == '' %}
        {% do exceptions.raise_compiler_error("loop_expr is required") %}
    {% endif %}

    {# max_rows defaults to 100 if not provided (set by apply function) #}
    {% if max_rows is none or max_rows == '' %}
        {% set max_rows = 100 %}
    {% endif %}

    {% set alias = "src" %}
    {% set relation_tables = (relation_name if relation_name is iterable and relation_name is not string else [relation_name]) | join(', ')  %}

    {# Use provided helper to unquote the provided column name #}
    {% set unquoted_col = prophecy_basics.unquote_identifier(column_name) | trim %}
    {% set internal_col = "__gen_" ~ unquoted_col | replace(' ', '_') %}

    {# Check if column exists in source schema #}
    {% set column_exists_in_schema = prophecy_basics.column_exists_in_schema(schema, column_name) %}

    {# Detect if init_expr is a simple date or timestamp string literal and cast it if needed #}
    {% set init_select = prophecy_basics.cast_timestamp_if_needed(init_expr) %}

    {# Normalize user-supplied condition expression quotes if they used double quotes only #}
    {% if '"' in condition_expr and "'" not in condition_expr %}
        {% set condition_expr_sql = condition_expr.replace('"', "'") %}
    {% else %}
        {% set condition_expr_sql = condition_expr %}
    {% endif %}

    {# --- Replace the target column in condition expression to reference the internal column --- #}
    {% set condition_expr_sql = prophecy_basics.replace_column_in_expression(condition_expr_sql, unquoted_col, internal_col, preserve_payload=true) %}

    {# --- Replace the target column in loop expression to reference gen.<internal_col> in recursive step --- #}
    {# Properly quote internal_col when creating gen. reference (e.g., gen.`__gen_date_val` not gen.__gen_date_val) #}
    {# Use backticks for internal columns to ensure proper SQL syntax #}
    {% set quoted_internal_col = "`" ~ internal_col ~ "`" %}
    {% set loop_expr_replaced = prophecy_basics.replace_column_in_expression(loop_expr, unquoted_col, 'gen.' ~ quoted_internal_col, preserve_payload=false) %}

    {# Use adapter-safe quoting for EXCLUDE column #}
    {% set except_col = prophecy_basics.safe_identifier(unquoted_col) %}

    {# --- Build recursion_condition: same condition but referencing the previous iteration (gen.__gen_col) --- #}
    {% set _rec_tmp = condition_expr_sql %}
    {% set _rec_tmp = _rec_tmp | replace(internal_col, 'gen.' ~ quoted_internal_col) %}
    {# Note: condition_expr_sql already has internal_col substituted; above we switch to gen.internal_col for recursive WHERE #}
    {% set recursion_condition = _rec_tmp %}

    {# --- Determine output alias: quote it if it contains non [A-Za-z0-9_] characters (no regex used) --- #}
    {% set allowed = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' %}
    {% set specials = [] %}
    {% for ch in unquoted_col %}
        {% if ch not in allowed %}
            {% do specials.append(ch) %}
        {% endif %}
    {% endfor %}
    {% if specials | length > 0 %}
        {% set output_col_alias = prophecy_basics.quote_identifier(unquoted_col) %}
    {% else %}
        {% set output_col_alias = unquoted_col %}
    {% endif %}

    {% if relation_tables %}
        with recursive payload as (
            -- Select all columns from source table
            select *
            from {{ relation_tables }} {{ alias }}
        ),
        gen as (
            -- base case: one row per input record
            -- Don't exclude the column here - it needs to be available in the recursive loop
            select
                payload.*,
                {{ init_select }} as {{ internal_col }},
                1 as _iter
            from payload

            union all

            -- recursive step
            select
                gen.* EXCLUDE (_iter),
                {{ loop_expr_replaced }} as {{ internal_col }},
                _iter + 1
            from gen
            where _iter < {{ max_rows | int }}
              and ({{ recursion_condition }})
        )
        select
            -- Exclude internal column, iteration counter, and original column from payload (only if it exists in schema)
            {% if column_exists_in_schema %}
            gen.* EXCLUDE ({{ internal_col }}, _iter, {{ unquoted_col }}),
            {% else %}
            gen.* EXCLUDE ({{ internal_col }}, _iter),
            {% endif %}
            {{ internal_col }} as {{ output_col_alias }}
        from gen
        where {{ condition_expr_sql }}
    {% else %}
        with recursive gen as (
            select {{ init_select }} as {{ internal_col }}, 1 as _iter
            union all
            select
                {{ loop_expr_replaced }} as {{ internal_col }},
                _iter + 1
            from gen
            where _iter < {{ max_rows | int }}
              and ({{ recursion_condition }})
        )
        select {{ internal_col }} as {{ output_col_alias }}
        from gen
        where {{ condition_expr_sql }}
    {% endif %}
{% endmacro %}