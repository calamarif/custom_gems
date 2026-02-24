{% macro DataEncoderDecoder(relation_name,
    column_names,
    remaining_columns,
    enc_dec_method,
    enc_dec_charSet,
    aes_enc_dec_secretScope_key,
    aes_enc_dec_secretKey_key,
    aes_enc_dec_mode,
    aes_enc_dec_secretScope_aad,
    aes_enc_dec_secretKey_aad,
    aes_enc_dec_secretScope_iv,
    aes_enc_dec_secretKey_iv,
    prefix_suffix_opt,
    change_col_name,
    prefix_suffix_val) -%}
    {{ return(adapter.dispatch('DataEncoderDecoder', 'prophecy_basics')(relation_name,
    column_names,
    remaining_columns,
    enc_dec_method,
    enc_dec_charSet,
    aes_enc_dec_secretScope_key,
    aes_enc_dec_secretKey_key,
    aes_enc_dec_mode,
    aes_enc_dec_secretScope_aad,
    aes_enc_dec_secretKey_aad,
    aes_enc_dec_secretScope_iv,
    aes_enc_dec_secretKey_iv,
    prefix_suffix_opt,
    change_col_name,
    prefix_suffix_val)) }}
{% endmacro %}


{% macro default__DataEncoderDecoder(
    relation_name,
    column_names,
    remaining_columns,
    enc_dec_method,
    enc_dec_charSet,
    aes_enc_dec_secretScope_key,
    aes_enc_dec_secretKey_key,
    aes_enc_dec_mode,
    aes_enc_dec_secretScope_aad,
    aes_enc_dec_secretKey_aad,
    aes_enc_dec_secretScope_iv,
    aes_enc_dec_secretKey_iv,
    prefix_suffix_opt,
    change_col_name,
    prefix_suffix_val
) %}
    {{ log("Applying encoding-specific column operations", info=True) }}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- set withColumn_clause = [] -%}
    {%- if enc_dec_method == "aes_encrypt" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- set args = [
                quoted_column,
                "secret('" ~ aes_enc_dec_secretScope_key ~ "','" ~ aes_enc_dec_secretKey_key ~ "')",
                "'" ~ aes_enc_dec_mode ~ "'",
                "'DEFAULT'"
            ] -%}
            {%- if aes_enc_dec_secretScope_iv != "" and aes_enc_dec_secretKey_iv != "" -%}
                {%- do args.append("secret('" ~ aes_enc_dec_secretScope_iv ~ "','" ~ aes_enc_dec_secretKey_iv ~ "')") -%}
            {%- else -%}
                {%- do args.append('""') -%}
            {%- endif -%}

            {%- if aes_enc_dec_secretScope_aad != "" and aes_enc_dec_secretKey_aad != "" -%}
                {%- do args.append("secret('" ~ aes_enc_dec_secretScope_aad ~ "','" ~ aes_enc_dec_secretKey_aad ~ "')") -%}
            {%- endif -%}

            {%- set arg_string = args | join(', ') -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("base64(aes_encrypt(" ~ arg_string ~ ")) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("base64(aes_encrypt(" ~ arg_string ~ ")) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("base64(aes_encrypt(" ~ arg_string ~ ")) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {#  ──────────────────────────────────── AES DECRYPT DISABLED BLOCK  ──────────────────────────────────────────────────── #}
    {#
    {%- if enc_dec_method == "aes_decrypt" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- set args = [
                "unbase64(" ~ quoted_column ~ ")",
                "secret('" ~ aes_enc_dec_secretScope_key ~ "','" ~ aes_enc_dec_secretKey_key ~ "')",
                "'" ~ aes_enc_dec_mode ~ "'",
                "'DEFAULT'"
            ] -%}
            {%- if aes_enc_dec_secretScope_aad != "" and aes_enc_dec_secretKey_aad != "" -%}
                {%- do args.append("secret('" ~ aes_enc_dec_secretScope_aad ~ "','" ~ aes_enc_dec_secretKey_aad ~ "')") -%}
            {%- endif -%}
            {%- set arg_string = args | join(', ') -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("CAST(" ~ "aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("CAST(" ~ "aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("CAST(" ~ "aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "try_aes_decrypt" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- set args = [
                "unbase64(" ~ quoted_column ~ ")",
                "secret('" ~ aes_enc_dec_secretScope_key ~ "','" ~ aes_enc_dec_secretKey_key ~ "')",
                "'" ~ aes_enc_dec_mode ~ "'",
                "'DEFAULT'"
            ] -%}
            {%- if aes_enc_dec_secretScope_aad != "" and aes_enc_dec_secretKey_aad != "" -%}
                {%- do args.append("secret('" ~ aes_enc_dec_secretScope_aad ~ "','" ~ aes_enc_dec_secretKey_aad ~ "')") -%}
            {%- endif -%}
            {%- set arg_string = args | join(', ') -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("CAST(" ~ "try_aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("CAST(" ~ "try_aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("CAST(" ~ "try_aes_decrypt(" ~ arg_string ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    #}
    {%- if enc_dec_method == "base64" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("base64(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("base64(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("base64(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "unbase64" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("CAST(" ~ "unbase64(" ~ quoted_column ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("CAST(" ~ "unbase64(" ~ quoted_column ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("CAST(" ~ "unbase64(" ~ quoted_column ~ ") AS STRING) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "hex" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "unhex" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("decode(" ~ "unhex(" ~ quoted_column ~ "), 'UTF-8') AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("decode(" ~ "unhex(" ~ quoted_column ~ "), 'UTF-8') AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("decode(" ~ "unhex(" ~ quoted_column ~ "), 'UTF-8') AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "encode" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("encode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("encode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("encode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- if enc_dec_method == "decode" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("decode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("decode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("decode(" ~ quoted_column ~ ", '" ~ enc_dec_charSet ~ "') AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    {%- set select_clause_sql = withColumn_clause | join(', ') -%}
    {%- set quoted_remaining_columns_sql = prophecy_basics.quote_column_list(remaining_columns) -%}
    {%- set select_cte_sql -%}
        {%- if select_clause_sql == "" -%}
            WITH final_cte AS (
                SELECT *
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif change_col_name == "prefix_suffix_substitute" -%}
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
                SELECT {{ quoted_remaining_columns_sql }}, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- endif -%}
    {%- endset -%}
    {%- set final_select_query = select_cte_sql ~ "\nSELECT * FROM final_cte" -%}
    {{ log("final select query is -> ", info=True) }}
    {{ log(final_select_query, info=True) }}
    {{ return(final_select_query) }}
{%- endmacro %}

{%- macro duckdb__DataEncoderDecoder(
    relation_name,
    column_names,
    remaining_columns,
    enc_dec_method,
    enc_dec_charSet,
    aes_enc_dec_secretScope_key,
    aes_enc_dec_secretKey_key,
    aes_enc_dec_mode,
    aes_enc_dec_secretScope_aad,
    aes_enc_dec_secretKey_aad,
    aes_enc_dec_secretScope_iv,
    aes_enc_dec_secretKey_iv,
    prefix_suffix_opt,
    change_col_name,
    prefix_suffix_val
) -%}
    {{ log("Applying encoding-specific column operations", info=True) }}
    {% set relation_list = relation_name if relation_name is iterable and relation_name is not string else [relation_name] %}
    {%- set withColumn_clause = [] -%}
    
    {# Note: DuckDB doesn't have native AES encryption functions like Databricks #}
    {# For now, we'll implement basic encoding methods that DuckDB supports #}
    
    {%- if enc_dec_method == "base64" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("base64(CAST(" ~ quoted_column ~ " AS BLOB)) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("base64(CAST(" ~ quoted_column ~ " AS BLOB)) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("base64(CAST(" ~ quoted_column ~ " AS BLOB)) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}

    {%- if enc_dec_method == "unbase64" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("CAST(from_base64(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("CAST(from_base64(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("CAST(from_base64(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}

    {%- if enc_dec_method == "hex" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("hex(" ~ quoted_column ~ ") AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}

    {%- if enc_dec_method == "unhex" -%}
        {% for column in column_names %}
            {%- set quoted_column = prophecy_basics.quote_identifier(column) -%}
            {%- if change_col_name == "inplace_substitute" -%}
                {%- do withColumn_clause.append("CAST(unhex(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(column)) -%}
            {%- elif prefix_suffix_opt == "Prefix" -%}
                {%- do withColumn_clause.append("CAST(unhex(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(prefix_suffix_val ~ column)) -%}
            {%- else -%}
                {%- do withColumn_clause.append("CAST(unhex(" ~ quoted_column ~ ") AS VARCHAR) AS " ~ prophecy_basics.quote_identifier(column ~ prefix_suffix_val)) -%}
            {%- endif -%}
        {% endfor %}
    {%- endif -%}
    
    {%- set select_clause_sql = withColumn_clause | join(', ') -%}
    {%- set quoted_remaining_columns_sql = prophecy_basics.quote_column_list(remaining_columns) -%}
    {%- set select_cte_sql -%}
        {%- if select_clause_sql == "" -%}
            WITH final_cte AS (
                SELECT *
                FROM {{ relation_list | join(', ') }}
            )
        {%- elif change_col_name == "prefix_suffix_substitute" -%}
            {%- if remaining_columns == "" -%}
                WITH final_cte AS (
                    SELECT *, {{ select_clause_sql }}
                    FROM {{ relation_list | join(', ') }}
                )
            {%- else -%}
                WITH final_cte AS (
                    SELECT {{ quoted_remaining_columns_sql }}, {{ select_clause_sql }}
                    FROM {{ relation_list | join(', ') }}
                )
            {%- endif -%}
        {%- elif remaining_columns == "" -%}
            WITH final_cte AS (
                SELECT {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- else -%}
            WITH final_cte AS (
                SELECT {{ quoted_remaining_columns_sql }}, {{ select_clause_sql }}
                FROM {{ relation_list | join(', ') }}
            )
        {%- endif -%}
    {%- endset -%}
    {%- set final_select_query = select_cte_sql ~ "\nSELECT * FROM final_cte" -%}
    {{ log("final select query is -> ", info=True) }}
    {{ log(final_select_query, info=True) }}
    {{ return(final_select_query) }}
{%- endmacro -%}