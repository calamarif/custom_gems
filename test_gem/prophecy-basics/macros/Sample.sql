{% macro Sample(relation_name,
    groupCols,
    randomSeed,
    currentModeSelection,
    numberN) -%}
    {{ return(adapter.dispatch('Sample', 'prophecy_basics')(relation_name,
    groupCols,
    randomSeed,
    currentModeSelection,
    numberN)) }}
{% endmacro %}

{%- macro default__Sample(relation_name, groupCols, randomSeed, currentModeSelection, numberN) -%}

{%- set seed_value = randomSeed | default(42) -%}
{%- set sample_size = numberN | default(100) -%}

{%- if groupCols | length > 0 -%}
    {%- set innerQuery = "
        select *,
            row_number() over (partition by " ~ groupCols | join(', ') ~ " order by " ~ groupCols | join(', ') ~ ") as rn,
            row_number() over (partition by " ~ groupCols | join(', ') ~ " order by rand(" ~ seed_value ~ ")) as random_rn,
            count(*) over (partition by " ~ groupCols | join(', ') ~ ") as group_rows,
            count(*) over () as total_rows
        from " ~ relation_name
        -%}
{%- else -%}
    {%- set innerQuery = "
        select *,
            row_number() over (order by 1) as rn,
            row_number() over (order by rand(" ~ seed_value ~ ")) as random_rn,
            count(*) over () as total_rows
        from " ~ relation_name
        -%}
{%- endif -%}

{%- if currentModeSelection == 'firstN' -%}
    -- Get first N rows
    select * except (rn, random_rn, total_rows{%- if groupCols | length > 0 -%}, group_rows{%- endif -%})
    from (
        {{ innerQuery }}
    ) numbered_data
    where rn <= {{ sample_size }}

{%- elif currentModeSelection == 'lastN' -%}
    -- Get last N rows
    select * except (rn, random_rn, total_rows{%- if groupCols | length > 0 -%}, group_rows{%- endif -%})
    from (
        {{ innerQuery }}
    ) numbered_data
    where {%- if groupCols | length > 0 %} rn > greatest(0, group_rows - {{ sample_size }}) {%- else %} rn > greatest(0, total_rows - {{ sample_size }}) {%- endif %}
    order by rn

{%- elif currentModeSelection == 'skipN' -%}
    -- Skip first N rows, return the rest
    select * except (rn, random_rn, total_rows{%- if groupCols | length > 0 -%}, group_rows{%- endif -%})
    from (
        {{ innerQuery }}
    ) numbered_data
    where rn > {{ sample_size }}

{%- elif currentModeSelection == 'oneOfN' -%}
    -- Take the first row of every group of N rows (1 of every N rows)
    -- This returns rows 1, N+1, 2N+1, etc.
    select * except (rn, random_rn, total_rows{%- if groupCols | length > 0 -%}, group_rows{%- endif -%})
    from (
        {{ innerQuery }}
    ) numbered_data
    where (rn - 1) % greatest(1, {{ sample_size }}) = 0

{%- elif currentModeSelection == 'oneInN' -%}
    -- Take every Nth row (deterministic): rows N, 2N, 3N, etc.
    -- This replicates Alteryx behavior of systematic sampling
    select * except (rn, random_rn, total_rows{%- if groupCols | length > 0 -%}, group_rows{%- endif -%})
    from (
        {{ innerQuery }}
    ) numbered_data
    where rn % greatest(1, {{ sample_size }}) = 0

{%- elif currentModeSelection == 'randomN' -%}
    -- Get N random rows (seeded for reproducibility)
    {%- if groupCols | length > 0 -%}
        -- For grouped data, take N random rows from each group
        select * except (rn, random_rn, total_rows, group_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where random_rn <= least({{ sample_size }}, group_rows)
    {%- else -%}
        -- For ungrouped data, take N random rows from entire dataset
        select * except (rn, random_rn, total_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where random_rn <= least({{ sample_size }}, total_rows)
    {%- endif -%}

{%- elif currentModeSelection == 'nPercent' -%}
    -- Return exactly N% of rows (deterministic, not probabilistic)
    -- This replicates Alteryx behavior of taking exact percentage
    {% set percent_val = sample_size | default(10) %}
    {% if percent_val > 100 %}
        {% set percent_val = 100 %}
    {% endif %}

    {%- if groupCols | length > 0 -%}
        -- For grouped data, take N% from each group
        select * except (rn, random_rn, total_rows, group_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where rn <= ceiling(group_rows * {{ percent_val }} / 100.0)
    {%- else -%}
        -- For ungrouped data, take N% of total rows
        select * except (rn, random_rn, total_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where rn <= ceiling(total_rows * {{ percent_val }} / 100.0)
    {%- endif -%}

{%- elif currentModeSelection == 'randomNPercent' -%}
    -- Return exactly N% of rows randomly (seeded for reproducibility)
    {% set percent_val = sample_size | default(10) %}
    {% if percent_val > 100 %}
        {% set percent_val = 100 %}
    {% endif %}

    {%- if groupCols | length > 0 -%}
        -- For grouped data, take N% random rows from each group
        select * except (rn, random_rn, total_rows, group_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where random_rn <= ceiling(group_rows * {{ percent_val }} / 100.0)
    {%- else -%}
        -- For ungrouped data, take N% random rows from entire dataset
        select * except (rn, random_rn, total_rows)
        from (
            {{ innerQuery }}
        ) numbered_data
        where random_rn <= ceiling(total_rows * {{ percent_val }} / 100.0)
    {%- endif -%}

{%- else -%}
    -- Default to First N rows if mode not recognized
    select 'ERROR: Invalid currentModeSelection value. Valid options: firstN, lastN, skipN, oneOfN, oneInN, randomN, nPercent, randomNPercent' as error_message
{%- endif -%}

{%- endmacro -%}

{%- macro bigquery__Sample(relation_name, groupCols, randomSeed, currentModeSelection, numberN) -%}

{%- set seed_value = randomSeed | default(42) -%}
{%- set sample_size = numberN | default(100) -%}

{%- if currentModeSelection == 'firstN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn
            from {{ relation_name }}
        ) numbered_data
        where rn <= {{ sample_size }}
    {%- else -%}
        select * except (rn)
        from (
            select *,
                row_number() over (order by 1) as rn
            from {{ relation_name }}
        ) numbered_data
        where rn <= {{ sample_size }}
    {%- endif -%}

{%- elif currentModeSelection == 'lastN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn, group_rows, total_rows)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn,
                count(*) over (partition by {{ groupCols | join(', ') }}) as group_rows,
                count(*) over () as total_rows
            from {{ relation_name }}
        ) numbered_data
        where rn > greatest(0, group_rows - {{ sample_size }})
        order by rn
    {%- else -%}
        select * except (rn, total_rows)
        from (
            select *,
                row_number() over (order by 1) as rn,
                count(*) over () as total_rows
            from {{ relation_name }}
        ) numbered_data
        where rn > greatest(0, total_rows - {{ sample_size }})
        order by rn
    {%- endif -%}

{%- elif currentModeSelection == 'skipN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn
            from {{ relation_name }}
        ) numbered_data
        where rn > {{ sample_size }}
    {%- else -%}
        select * except (rn)
        from (
            select *,
                row_number() over (order by 1) as rn
            from {{ relation_name }}
        ) numbered_data
        where rn > {{ sample_size }}
    {%- endif -%}

{%- elif currentModeSelection == 'oneOfN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn
            from {{ relation_name }}
        ) numbered_data
        where MOD(rn - 1, greatest(1, {{ sample_size }})) = 0
    {%- else -%}
        select * except (rn)
        from (
            select *,
                row_number() over (order by 1) as rn
            from {{ relation_name }}
        ) numbered_data
        where MOD(rn - 1, greatest(1, {{ sample_size }})) = 0
    {%- endif -%}

{%- elif currentModeSelection == 'oneInN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn
            from {{ relation_name }}
        ) numbered_data
        where MOD(rn, greatest(1, {{ sample_size }})) = 0
    {%- else -%}
        select * except (rn)
        from (
            select *,
                row_number() over (order by 1) as rn
            from {{ relation_name }}
        ) numbered_data
        where MOD(rn, greatest(1, {{ sample_size }})) = 0
    {%- endif -%}

{%- elif currentModeSelection == 'randomN' -%}
    {%- if groupCols | length > 0 -%}
        select * except (rn, random_rn, group_rows, total_rows)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn,
                row_number() over (partition by {{ groupCols | join(', ') }} order by FARM_FINGERPRINT(CONCAT(TO_JSON_STRING(STRUCT(t)), '-', CAST({{ seed_value }} AS STRING)))) as random_rn,
                count(*) over (partition by {{ groupCols | join(', ') }}) as group_rows,
                count(*) over () as total_rows
            from {{ relation_name }} as t
        ) numbered_data
        where random_rn <= least({{ sample_size }}, group_rows)
    {%- else -%}
        select * except (rn, random_rn, total_rows)
        from (
            select *,
                row_number() over (order by 1) as rn,
                row_number() over (order by FARM_FINGERPRINT(CONCAT(TO_JSON_STRING(STRUCT(t)), '-', CAST({{ seed_value }} AS STRING)))) as random_rn,
                count(*) over () as total_rows
            from {{ relation_name }} as t
        ) numbered_data
        where random_rn <= least({{ sample_size }}, total_rows)
    {%- endif -%}

{%- elif currentModeSelection == 'nPercent' -%}
    {% set percent_val = sample_size | default(10) %}
    {% if percent_val > 100 %}
        {% set percent_val = 100 %}
    {% endif %}

    {%- if groupCols | length > 0 -%}
        select * except (rn, group_rows, total_rows)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn,
                count(*) over (partition by {{ groupCols | join(', ') }}) as group_rows,
                count(*) over () as total_rows
            from {{ relation_name }}
        ) numbered_data
        where rn <= ceiling(group_rows * {{ percent_val }} / 100.0)
    {%- else -%}
        select * except (rn, total_rows)
        from (
            select *,
                row_number() over (order by 1) as rn,
                count(*) over () as total_rows
            from {{ relation_name }}
        ) numbered_data
        where rn <= ceiling(total_rows * {{ percent_val }} / 100.0)
    {%- endif -%}

{%- elif currentModeSelection == 'randomNPercent' -%}
    {%- set percent_val = sample_size | default(10) -%}
    {%- if percent_val > 100 -%}
        {%- set percent_val = 100 -%}
    {%- endif -%}

    {%- if groupCols | length > 0 -%}
        select * except (rn, random_rn, group_rows, total_rows)
        from (
            select *,
                row_number() over (partition by {{ groupCols | join(', ') }} order by {{ groupCols | join(', ') }}) as rn,
                row_number() over (partition by {{ groupCols | join(', ') }} order by FARM_FINGERPRINT(CONCAT(TO_JSON_STRING(STRUCT(t)), '-', CAST({{ seed_value }} AS STRING)))) as random_rn,
                count(*) over (partition by {{ groupCols | join(', ') }}) as group_rows,
                count(*) over () as total_rows
            from {{ relation_name }} as t
        ) numbered_data
        where random_rn <= ceiling(group_rows * {{ percent_val }} / 100.0)
    {%- else -%}
        select * except (rn, random_rn, total_rows)
        from (
            select *,
                row_number() over (order by 1) as rn,
                row_number() over (order by FARM_FINGERPRINT(CONCAT(TO_JSON_STRING(STRUCT(t)), '-', CAST({{ seed_value }} AS STRING)))) as random_rn,
                count(*) over () as total_rows
            from {{ relation_name }} as t
        ) numbered_data
        where random_rn <= ceiling(total_rows * {{ percent_val }} / 100.0)
    {%- endif -%}

{%- else -%}
    select 'ERROR: Invalid currentModeSelection value. Valid options: firstN, lastN, skipN, oneOfN, oneInN, randomN, nPercent, randomNPercent' as error_message
{%- endif -%}

{%- endmacro -%}