{% macro column_exists_in_schema(schema, column_name) %}
    {# Check if a column exists in the provided schema #}
    {# Schema is a JSON array of objects with 'name' and 'dataType' keys #}
    {# Returns true if column exists, false otherwise #}
    {% if schema is none or schema == '' or schema == '[]' or schema == "''" or schema is undefined %}
        {{ return(false) }}
    {% endif %}

    {# Parse the JSON schema string into a list of objects #}
    {# Only parse if schema is a string (not already parsed) #}
    {% set schema_parsed = [] %}
    {% if schema is string %}
        {% set schema_parsed = fromjson(schema) %}
    {% elif schema is iterable %}
        {# Already a list/array, use directly #}
        {% set schema_parsed = schema %}
    {% else %}
        {{ return(false) }}
    {% endif %}

    {# Check if parsing was successful and result is iterable #}
    {% if schema_parsed is none %}
        {{ return(false) }}
    {% endif %}

    {% if schema_parsed is not iterable or schema_parsed is string or schema_parsed is number %}
        {{ return(false) }}
    {% endif %}

    {% set unquoted_col = prophecy_basics.unquote_identifier(column_name) | trim %}

    {# Iterate through schema objects and check if column name matches (using adapter-specific case sensitivity) #}
    {% for c in schema_parsed %}
        {# Each c should be an object with 'name' and 'dataType' keys #}
        {% set schema_col_name = c.name | trim %}
        {% if prophecy_basics.column_names_match(schema_col_name, unquoted_col) %}
            {{ return(true) }}
        {% endif %}
    {% endfor %}

    {{ return(false) }}
{% endmacro %}
