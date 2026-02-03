
{%- macro Transpose(
    relation_name,
    keyColumns,
    dataColumns,
    nameColumn,
    valueColumn,
    schema=[]) -%}

  {%- set available_cols = [] -%}
  {%- if keyColumns and dataColumns and nameColumn | length > 0 and valueColumn | length > 0 -%}
    {%- for col in dataColumns -%}
      {%- if col in schema -%}
        {%- do available_cols.append(col) -%}
      {%- endif -%}
    {%- endfor -%}

    {%- set union_queries = [] -%}
    {%- for data_col in available_cols -%}
      {%- set select_list = [] -%}
      {%- for key in keyColumns -%}
        {%- do select_list.append(key) -%}
      {%- endfor -%}
      {%- do select_list.append("'" ~ data_col ~ "' as " ~ nameColumn) -%}
      {%- do select_list.append('CAST("' ~ data_col ~ '" as string) as ' ~ valueColumn ) -%}
      
      {%- set query = 'SELECT ' ~ (select_list | join(', ')) ~ ' FROM ' ~ relation_name -%}
      {%- do union_queries.append(query) -%}
    {%- endfor -%}

    {{ union_queries | join('\nUNION ALL\n') }}
  {%- else -%}
    select * from {{ relation_name }}
  {%- endif -%}

{%- endmacro -%}