{% macro UnionByName(relation_names,
                     schemas,
                     missingColumnOps='allowMissingColumns') -%}
    {{ return(adapter.dispatch('UnionByName', 'prophecy_basics')(relation_names, schemas, missingColumnOps)) }}
{% endmacro %}

{% macro default__UnionByName(relation_names,
                     schemas,
                     missingColumnOps='allowMissingColumns') -%}

    {# Step 1: Normalize relation list #}
    {%- if relation_names is string -%}
        {%- set relations = relation_names.split(',') | map('trim') | list -%}
    {%- else -%}
        {%- set relations = relation_names | list -%}
    {%- endif -%}

    {# Step 2: Capture column names per schema #}
    {%- set columns_per_relation = [] -%}
    {%- for schema_blob in schemas -%}
        {%- if schema_blob is string -%}
            {%- set parsed = fromjson(schema_blob) -%}
        {%- else -%}
            {%- set parsed = schema_blob -%}
        {%- endif -%}

        {%- set col_list = [] -%}
        {%- for f in parsed -%}
            {%- do col_list.append(f.name) -%}
        {%- endfor -%}
        {%- do columns_per_relation.append(col_list) -%}
    {%- endfor -%}

    {# Step 3: Normalize column names and preserve original for final SELECT #}
    {%- set norm_to_original = {} -%}
    {%- set final_columns = [] -%}
    {%- for col in columns_per_relation[0] -%}
        {%- set norm = col | lower -%}
        {%- if norm not in norm_to_original -%}
            {%- do norm_to_original.update({norm: col}) -%}
            {%- do final_columns.append(norm) -%}
        {%- endif -%}
    {%- endfor -%}

    {# Step 4: Merge schema column names #}
    {%- if missingColumnOps == 'allowMissingColumns' -%}
        {%- for other_cols in columns_per_relation[1:] -%}
            {%- for c in other_cols -%}
                {%- set norm = c | lower -%}
                {%- if norm not in norm_to_original -%}
                    {%- do norm_to_original.update({norm: c}) -%}
                    {%- do final_columns.append(norm) -%}
                {%- endif -%}
            {%- endfor -%}
        {%- endfor -%}

    {%- elif missingColumnOps == 'nameBasedUnionOperation' -%}
        {%- for idx in range(1, columns_per_relation | length) -%}
            {%- set current_norm = columns_per_relation[idx] | map('lower') | list -%}
            {%- set extra = [] -%}
            {%- set missing = [] -%}
            {%- for c in current_norm if c not in final_columns -%}
                {%- do extra.append(c) -%}
            {%- endfor -%}
            {%- for c in final_columns if c not in current_norm -%}
                {%- do missing.append(c) -%}
            {%- endfor -%}
            {%- if extra or missing -%}
                {{ exceptions.raise_compiler_error(
                    "Column mismatch between first relation and relation "
                    ~ (idx + 1) ~ ". Extra: " ~ extra | join(', ')
                    ~ " | Missing: " ~ missing | join(', ')
                ) }}
            {%- endif -%}
        {%- endfor -%}

    {%- else -%}
        {{ exceptions.raise_compiler_error("Unsupported missingColumnOps value: " ~ missingColumnOps) }}
    {%- endif -%}

    {# Step 5: Build SELECTs with proper quoting #}
    {%- set selects = [] -%}
    {%- for idx in range(relations | length) -%}
        {%- set cur_cols = columns_per_relation[idx] -%}
        {%- set cur_norms = cur_cols | map('lower') | list -%}
        {%- set parts = [] -%}

        {%- for norm in final_columns -%}
            {%- set quoted_alias = prophecy_basics.quote_identifier(norm_to_original[norm]) -%}
            {%- if norm in cur_norms -%}
                {%- set actual_idx = cur_norms.index(norm) -%}
                {%- set quoted_actual = prophecy_basics.quote_identifier(cur_cols[actual_idx]) -%}
                {%- do parts.append(quoted_actual ~ " as " ~ quoted_alias) -%}
            {%- else -%}
                {%- do parts.append("null as " ~ quoted_alias) -%}
            {%- endif -%}
        {%- endfor -%}

        {%- do selects.append("select " ~ parts | join(', ') ~ " from " ~ relations[idx]) -%}
    {%- endfor -%}

    {# Step 6: Union all together #}
    with union_query as (
        {{ selects | join('\nunion all\n') }}
    )
    select * from union_query

{%- endmacro %}

{% macro duckdb__UnionByName(relation_names,
                     schemas,
                     missingColumnOps='allowMissingColumns') -%}

    {# Step 1: Normalize relation list #}
    {%- if relation_names is string -%}
        {%- set relations = relation_names.split(',') | map('trim') | list -%}
    {%- else -%}
        {%- set relations = relation_names | list -%}
    {%- endif -%}

    {# Step 2: Capture column names per schema #}
    {%- set columns_per_relation = [] -%}
    {%- for schema_blob in schemas -%}
        {%- if schema_blob is string -%}
            {%- set parsed = fromjson(schema_blob) -%}
        {%- else -%}
            {%- set parsed = schema_blob -%}
        {%- endif -%}

        {%- set col_list = [] -%}
        {%- for f in parsed -%}
            {%- do col_list.append(f.name) -%}
        {%- endfor -%}
        {%- do columns_per_relation.append(col_list) -%}
    {%- endfor -%}

    {# Step 3: Normalize names #}
    {%- set norm_to_original = {} -%}
    {%- set final_columns = [] -%}
    {%- for col in columns_per_relation[0] -%}
        {%- set norm = col | lower -%}
        {%- if norm not in norm_to_original -%}
            {%- do norm_to_original.update({norm: col}) -%}
            {%- do final_columns.append(norm) -%}
        {%- endif -%}
    {%- endfor -%}

    {# Step 4: Handle missing column ops #}
    {%- if missingColumnOps == 'allowMissingColumns' -%}
        {%- for other_cols in columns_per_relation[1:] -%}
            {%- for c in other_cols -%}
                {%- set norm = c | lower -%}
                {%- if norm not in norm_to_original -%}
                    {%- do norm_to_original.update({norm: c}) -%}
                    {%- do final_columns.append(norm) -%}
                {%- endif -%}
            {%- endfor -%}
        {%- endfor -%}

    {%- elif missingColumnOps == 'nameBasedUnionOperation' -%}
        {%- for idx in range(1, columns_per_relation | length) -%}
            {%- set current_norm = columns_per_relation[idx] | map('lower') | list -%}
            {%- set extra = [] -%}
            {%- set missing = [] -%}
            {%- for c in current_norm if c not in final_columns -%}
                {%- do extra.append(c) -%}
            {%- endfor -%}
            {%- for c in final_columns if c not in current_norm -%}
                {%- do missing.append(c) -%}
            {%- endfor -%}
            {%- if extra or missing -%}
                {{ exceptions.raise_compiler_error(
                    "Column mismatch between first relation and relation "
                    ~ (idx + 1) ~ ". Extra: " ~ extra | join(', ')
                    ~ " | Missing: " ~ missing | join(', ')
                ) }}
            {%- endif -%}
        {%- endfor -%}

    {%- else -%}
        {{ exceptions.raise_compiler_error("Unsupported missingColumnOps value: " ~ missingColumnOps) }}
    {%- endif -%}

    {# Step 5: Build SELECTs #}
    {%- set selects = [] -%}
    {%- for idx in range(relations | length) -%}
        {%- set cur_cols = columns_per_relation[idx] -%}
        {%- set cur_norms = cur_cols | map('lower') | list -%}
        {%- set parts = [] -%}

        {%- for norm in final_columns -%}
            {%- set alias_col = norm_to_original[norm] -%}
            {%- if norm in cur_norms -%}
                {%- set actual_idx = cur_norms.index(norm) -%}
                {%- set actual_col = cur_cols[actual_idx] -%}
                {%- do parts.append(actual_col ~ " as " ~ alias_col) -%}
            {%- else -%}
                {%- do parts.append("null as " ~ alias_col) -%}
            {%- endif -%}
        {%- endfor -%}

        {%- do selects.append("select " ~ parts | join(', ') ~ " from " ~ relations[idx]) -%}
    {%- endfor -%}

    {# Step 6: Union all together #}
    with union_query as (
        {{ selects | join('\nunion all\n') }}
    )
    select * from union_query

{%- endmacro %}
