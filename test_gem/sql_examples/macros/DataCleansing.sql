{% macro DataCleansing(
    relation_name,
    schema,
    modifyCase,
    columnNames=[],
    replaceNullTextFields=False,
    replaceNullTextWith="NA",
    replaceNullForNumericFields=False,
    replaceNullNumericWith=0,
    trimWhiteSpace=False,
    removeTabsLineBreaksAndDuplicateWhitespace=False,
    allWhiteSpace=False,
    cleanLetters=False,
    cleanPunctuations=False,
    cleanNumbers=False,
    removeRowNullAllCols=False,
    replaceNullDateFields=False,
    replaceNullDateWith="1970-01-01",
    replaceNullTimeFields=False,
    replaceNullTimeWith="1970-01-01 00:00:00"
) %}

    {{ log("Applying dataset-specific cleansing operations", info=True) }}
    {%- if removeRowNullAllCols -%}
        {{ log("Removing rows where all columns are null", info=True) }}
        {%- set where_clause = [] -%}
        {%- for col in schema -%}
            {%- do where_clause.append('"' ~ col['name'] ~ '"' ~ ' IS NOT NULL') -%}
        {%- endfor -%}
        {%- set where_clause_sql = where_clause | join(' OR ') -%}

        {%- set cleansed_cte -%}
            WITH cleansed_data AS (
                SELECT *
                FROM {{ relation_name }}
                WHERE {{ where_clause_sql }}
            )
        {%- endset -%}

    {%- else  -%}
        {{ log("Returning all columns since dataset-specific cleansing operations are not specified", info=True) }}
        {%- set cleansed_cte -%}
            WITH cleansed_data AS (
                SELECT *
                FROM {{ relation_name }}
            )
        {%- endset -%}
    {%- endif -%}

    {{ log("Applying column-specific cleansing operations", info=True) }}
    {# Check if columnNames is not empty #}
    {%- if columnNames | length > 0 -%}
        {%- set columns_to_select = [] -%}
        {%- set col_type_map = {} -%}
        {%- for col in schema -%}
            {%- set col_type_map = col_type_map.update({ col.name: col.dataType | lower }) -%}
        {%- endfor -%}
        {%- set numeric_types = ["number", "float"] -%}

        {{ log(col_type_map, info = True) }}
        {%- for col_name in columnNames -%}
            {%- set col_expr = '"' ~ col_name ~ '"' -%}

            {%- if col_type_map.get(col_name) in numeric_types -%}
                {%- if replaceNullForNumericFields -%}
                    {%- set col_expr = "COALESCE(" ~ col_expr ~ ", " ~ replaceNullNumericWith | string ~ ")" -%}
                {%- endif -%}
            {%- endif -%}

            {%- if col_type_map.get(col_name) == "string" -%}

                {%- if replaceNullTextFields -%}
                    {%- set col_expr = "COALESCE(" ~ col_expr ~ ", '" ~ replaceNullTextWith ~ "')" -%}
                {%- endif -%}

                {%- if trimWhiteSpace -%}
                    {%- set col_expr = "LTRIM(RTRIM(" ~ col_expr ~ "))" -%}
                {%- endif -%}

                {%- if removeTabsLineBreaksAndDuplicateWhitespace -%}
                    {%- set col_expr = "REGEXP_REPLACE(" ~ col_expr ~ ", '\\\\s+', ' ')" -%}
                {%- endif -%}

                {%- if allWhiteSpace -%}
                    {%- set col_expr = "REGEXP_REPLACE(" ~ col_expr ~ ", '\\\\s+', '')" -%}
                {%- endif -%}

                {%- if cleanLetters -%}
                    {%- set col_expr = "REGEXP_REPLACE(" ~ col_expr ~ ", '[^A-Za-z]', '')" -%}
                {%- endif -%}

                {%- if cleanPunctuations -%}
                    {%- set col_expr = "REGEXP_REPLACE(" ~ col_expr ~ ", '[^a-zA-Z0-9\\\\s]', '')" -%}
                {%- endif -%}

                {%- if cleanNumbers -%}
                    {%- set col_expr = "REGEXP_REPLACE(" ~ col_expr ~ ", '\\\\d+', '')" -%}
                {%- endif -%}

                {%- if modifyCase == "makeLowercase" -%}
                    {%- set col_expr = "LOWER(" ~ col_expr ~ ")" -%}
                {%- endif -%}

                {%- if modifyCase == "makeUppercase" -%}
                    {%- set col_expr = "UPPER(" ~ col_expr ~ ")" -%}
                {%- endif -%}

                {%- if modifyCase == "makeTitlecase" -%}
                    {%- set col_expr = "INITCAP(" ~ col_expr ~ ")" -%}
                {%- endif -%}

            {%- endif -%}

            {%- if col_type_map.get(col_name) == "date" -%}
                {%- if replaceNullDateFields -%}
                    {%- set col_expr = "COALESCE(" ~ col_expr ~ ", DATE '" ~ replaceNullDateWith ~ "')" -%}
                {%- endif -%}
            {%- endif -%}

            {%- if col_type_map.get(col_name) == "timestamp" -%}
                {%- if replaceNullTimeFields -%}
                    {%- set col_expr = "COALESCE(" ~ col_expr ~ ", TIMESTAMP '" ~ replaceNullTimeWith ~ "')" -%}
                {%- endif -%}
            {%- endif -%}



            {{ log("Appending transformed column expression", info=True) }}
            {%- set col_expr = col_expr ~ "::" ~ col_type_map.get(col_name) -%}
            {%- do columns_to_select.append(col_expr ~ ' AS ' ~ '"' ~ col_name ~ '"') -%}
        {%- endfor -%}

        {# Get the schema of cleansed data #}
        {%- set output_columns = [] -%}
        {%- for col_name_val in schema -%}
            {% set flag_dict = {"flag": false} %}
            {%- for expr in columns_to_select -%}
                {# Split on 'AS' to get the alias; assumes expression contains "AS" #}
                {%- set parts = expr.split(' AS "') -%}
                {%- set alias = parts[-1] | trim | replace('"', '') | upper -%}

                {%- if col_name_val['name'] | trim | replace('"', '') | upper == alias -%}
                    {%- do output_columns.append(expr) -%}
                    {% do flag_dict.update({"flag": true}) %}
                    {%- break -%}
                {%- endif -%}
            {%- endfor -%}

            {%- if flag_dict.flag == false -%}
                {%- do output_columns.append('"' ~ col_name_val['name'] ~ '"') -%}
            {%- endif -%}
        {%- endfor -%}        
        {{ log("Columns after expression evaluation:" ~ output_columns, info=True) }}

        {# Now, all_columns contains the original names with any overrides applied #}
        {%- set final_output_columns = output_columns | unique | join(', ') -%}
        {{ log("Final Output Columns: " ~ final_output_columns, info=True) }}            

        {%- set final_select -%}
            {%- if columns_to_select -%}
                SELECT {{ final_output_columns }} FROM cleansed_data
            {%- else -%}
                SELECT * FROM cleansed_data
            {%- endif -%}
        {%- endset -%}

    {%- else -%}
        {%- set final_select -%}
            SELECT * FROM cleansed_data
        {%- endset -%}
    {%- endif -%}

    {%- set final_query = cleansed_cte ~ "\n" ~ final_select -%}
    {{ return(final_query) }}
    
{%- endmacro -%}