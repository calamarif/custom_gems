{%- macro XMLParse(
  relation_name,
  columnName,
  columnSuffix
  )
-%}

{%- set evaluation_result = SnowflakeSqlBasics.XmlToJson() -%}

SELECT
  *,
  {%- for col in columnName %}
    PARSE_JSON({{target.database}}.{{target.schema}}.xml_to_json({{col}})) AS {{ col }}_{{ columnSuffix }}{{ "," if not loop.last }}
  {%- endfor %}
FROM {{ relation_name }}

{%- endmacro -%}