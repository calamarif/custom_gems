{% macro DataMasking(relation_name,
    column_names,
    remaining_columns,
    masking_method,
    upper_char_substitute,
    lower_char_substitute,
    digit_char_substitute,
    other_char_substitute,
    sha2_bit_length,
    masked_column_add_method,
    prefix_suffix_opt,
    prefix_suffix_val,
    combined_hash_column_name) -%}
    {{ return(adapter.dispatch('DataMasking', 'prophecy_basics')(relation_name,
    column_names,
    remaining_columns,
    masking_method,
    upper_char_substitute,
    lower_char_substitute,
    digit_char_substitute,
    other_char_substitute,
    sha2_bit_length,
    masked_column_add_method,
    prefix_suffix_opt,
    prefix_suffix_val,
    combined_hash_column_name)) }}
{% endmacro %}


{%- macro default__DataMasking(
    relation_name,
    column_names,
    remaining_columns,
    masking_method,
    upper_char_substitute,
    lower_char_substitute,
    digit_char_substitute,
    other_char_substitute,
    sha2_bit_length,
    masked_column_add_method,
    prefix_suffix_opt,
    prefix_suffix_val,
    combined_hash_column_name
) %}

    {{ log("Applying Masking-specific column operations", info=True) }}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- set withColumn_clause = [] -%}
    {%- if masking_method == "mask" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- set args = [quoted_column] -%}

            {%- if upper_char_substitute == "NULL" -%}
                {%- do args.append("upperChar => NULL") -%}
            {%- elif upper_char_substitute != "" -%}
                {%- do args.append("upperChar => '" ~ upper_char_substitute ~ "'") -%}
            {%- endif -%}

            {%- if lower_char_substitute == "NULL" -%}
                {%- do args.append("lowerChar => NULL") -%}
            {%- elif lower_char_substitute != "" -%}
                {%- do args.append("lowerChar => '" ~ lower_char_substitute ~ "'") -%}
            {%- endif -%}

            {%- if digit_char_substitute == "NULL" -%}
                {%- do args.append("digitChar => NULL") -%}
            {%- elif digit_char_substitute != "" -%}
                {%- do args.append("digitChar => '" ~ digit_char_substitute ~ "'") -%}
            {%- endif -%}

            {%- if other_char_substitute == "NULL" -%}
                {%- do args.append("otherChar => NULL") -%}
            {%- elif other_char_substitute != "" -%}
                {%- do args.append("otherChar => '" ~ other_char_substitute ~ "'") -%}
            {%- endif -%}
            {%- set arg_string = args | join(', ') -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- do withColumn_clause.append("mask(" ~ arg_string ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("mask(" ~ arg_string ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("mask(" ~ arg_string ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}

    {%- elif masking_method == "hash" -%}
        {%- if masked_column_add_method == "combinedHash_substitute" -%}
            {%- set quoted_columns = [] -%}
            {%- for column in column_names -%}
                {%- do quoted_columns.append(prophecy_basics.quote_identifier(column)) -%}
            {%- endfor -%}
            {%- set arg_string = quoted_columns | join(', ') -%}
            {%- do withColumn_clause.append("hash(" ~ arg_string ~ ") AS " ~ prophecy_basics.quote_identifier(combined_hash_column_name)) -%}
        {%- else  -%}
            {% for column in column_names %}
                {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
                {%- if masked_column_add_method == "inplace_substitute" -%}
                    {%- do withColumn_clause.append("hash(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
                {%- elif prefix_suffix_opt == "Prefix" -%}
                    {%- do withColumn_clause.append("hash(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
                {%- else -%}
                    {%- do withColumn_clause.append("hash(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
                {%- endif -%}
            {% endfor %}
        {%- endif -%}

    {%- elif masking_method == "sha2" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- do withColumn_clause.append("sha2(" ~ quoted_column ~ ", " ~ sha2_bit_length ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("sha2(" ~ quoted_column ~ ", " ~ sha2_bit_length ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("sha2(" ~ quoted_column ~ ", " ~ sha2_bit_length ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}

    {%- else -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- do withColumn_clause.append(masking_method ~ "(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append(masking_method ~ "(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append(masking_method ~ "(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}

    {%- endif -%}

    {%- set select_clause_sql = withColumn_clause | join(', ') -%}

    {%- set select_cte_sql -%}
        {%- if select_clause_sql == "" -%}
            WITH final_cte AS (
                SELECT *
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif (masked_column_add_method == "prefix_suffix_substitute") or (masking_method == "hash" and masked_column_add_method == "combinedHash_substitute") -%}
            WITH final_cte AS (
                SELECT *, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif remaining_columns == "" -%}
            WITH final_cte AS (
                SELECT {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- else -%}
            WITH final_cte AS (
                SELECT {{ remaining_columns }}, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- endif -%}
    {%- endset -%}

    {%- set final_select_query = select_cte_sql ~ "\nSELECT * FROM final_cte" -%}

    {{ log("final select query is -> ", info=True) }}
    {{ log(final_select_query, info=True) }}

    {{ return(final_select_query) }}

{%- endmacro -%}

{%- macro duckdb__DataMasking(
    relation_name,
    column_names,
    remaining_columns,
    masking_method,
    upper_char_substitute,
    lower_char_substitute,
    digit_char_substitute,
    other_char_substitute,
    sha2_bit_length,
    masked_column_add_method,
    prefix_suffix_opt,
    prefix_suffix_val,
    combined_hash_column_name
) -%}

    {{ log("Applying Masking-specific column operations", info=True) }}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- set withColumn_clause = [] -%}
    {%- if masking_method == "mask" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- set mask_expression = "CASE " -%}
            {%- set mask_expression = mask_expression ~ "WHEN " ~ quoted_column ~ " IS NULL THEN NULL " -%}
            {%- set mask_expression = mask_expression ~ "ELSE regexp_replace(" ~ quoted_column ~ ", '[A-Z]', '" ~ (upper_char_substitute if upper_char_substitute != "NULL" else "X") ~ "', 'g')" -%}
            {%- set mask_expression = mask_expression ~ "END" -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- do withColumn_clause.append(mask_expression ~ " AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append(mask_expression ~ " AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append(mask_expression ~ " AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}

    {%- elif masking_method == "hash" -%}
        {%- if masked_column_add_method == "combinedHash_substitute" -%}
            {%- set quoted_columns = [] -%}
            {%- for column in column_names -%}
                {%- do quoted_columns.append(prophecy_basics.quote_identifier(column)) -%}
            {%- endfor -%}
            {%- set concat_expression = quoted_columns | join(' || ') -%}
            {%- do withColumn_clause.append("md5(CAST(" ~ concat_expression ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(combined_hash_column_name)) -%}
        {%- else  -%}
            {% for column in column_names %}
                {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
                {%- if masked_column_add_method == "inplace_substitute" -%}
                    {%- do withColumn_clause.append("md5(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column)) -%}
                {%- elif prefix_suffix_opt == "Prefix" -%}
                    {%- do withColumn_clause.append("md5(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
                {%- else -%}
                    {%- do withColumn_clause.append("md5(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
                {%- endif -%}
            {% endfor %}
        {%- endif -%}

    {%- elif masking_method == "sha2" -%}
        {%- if sha2_bit_length != "256" -%}
            {{ exceptions.raise_compiler_error("DuckDB only supports SHA2 with 256-bit length. sha2_bit_length=" ~ sha2_bit_length ~ " is not supported. Please use sha2_bit_length=256.") }}
        {%- endif -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- do withColumn_clause.append("sha256(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("sha256(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("sha256(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}

    {%- else -%}
        {%- if masking_method == "crc32" -%}
            {{ exceptions.raise_compiler_error("crc32 is not supported in duckdb") }}
        {%- endif -%}

        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if masked_column_add_method == "inplace_substitute" -%}
                {%- if masking_method == "sha" -%}
                    {%- do withColumn_clause.append("sha1(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column)) -%}
                {%- else -%}
                    {%- do withColumn_clause.append(masking_method ~ "(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column)) -%}
                {%- endif -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- if masking_method == "sha" -%}
                    {%- do withColumn_clause.append("sha1(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
                {%- else -%}
                    {%- do withColumn_clause.append(masking_method ~ "(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
                {%- endif -%}
            {%- else -%}
                {%- if masking_method == "sha" -%}
                    {%- do withColumn_clause.append("sha1(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
                {%- else -%}
                    {%- do withColumn_clause.append(masking_method ~ "(CAST(" ~ quoted_column ~ " AS VARCHAR)) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
                {%- endif -%}
            {%- endif -%}
        {% endfor %}

    {%- endif -%}

    {%- set select_clause_sql = withColumn_clause | join(', ') -%}

    {%- set select_cte_sql -%}
        {%- if select_clause_sql == "" -%}
            WITH final_cte AS (
                SELECT *
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif (masked_column_add_method == "prefix_suffix_substitute") or (masking_method == "hash" and masked_column_add_method == "combinedHash_substitute") -%}
            WITH final_cte AS (
                SELECT *, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif remaining_columns == "" -%}
            WITH final_cte AS (
                SELECT {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- else -%}
            WITH final_cte AS (
                SELECT {{ remaining_columns }}, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- endif -%}
    {%- endset -%}

    {%- set final_select_query = select_cte_sql ~ "\nSELECT * FROM final_cte" -%}

    {{ log("final select query is -> ", info=True) }}
    {{ log(final_select_query, info=True) }}

    {{ return(final_select_query) }}

{%- endmacro -%}
