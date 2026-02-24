{% macro TableOperations(
    catalog='',
    database='',
    tableName='',
    action='',
    path='',
    useExternalFilePath=false,
    vacuumRetainNumHours='',
    useOptimiseWhere=false,
    optimiseWhere='',
    useOptimiseZOrder=false,
    optimiseZOrderColumns='',
    restoreVia='',
    restoreValue='',
    deleteCondition='true',
    updateSetClause='',
    updateCondition='',
    runDDL=''    
) -%}
    {{ return(adapter.dispatch('TableOperations', 'prophecy_basics')(
        catalog,
        database,
        tableName,
        action,
        path,
        useExternalFilePath,
        vacuumRetainNumHours,
        useOptimiseWhere,
        optimiseWhere,
        useOptimiseZOrder,
        optimiseZOrderColumns,
        restoreVia,
        restoreValue,
        deleteCondition,
        updateSetClause,
        updateCondition,
        runDDL
    )) }}
{% endmacro %}

{% macro default__TableOperations(
    catalog='',
    database='',
    tableName='',
    action='',
    path='',
    useExternalFilePath=false,
    vacuumRetainNumHours='',
    useOptimiseWhere=false,
    optimiseWhere='',
    useOptimiseZOrder=false,
    optimiseZOrderColumns='',
    restoreVia='',
    restoreValue='',
    deleteCondition='true',
    updateSetClause='',
    updateCondition='',
    runDDL=''
) %}

    {%- set sql_command = '' -%}
    {%- set target_table = "`" ~ catalog ~ "`.`" ~ database ~ "`.`" ~ tableName ~ "`" -%}

    {#- Register Table in Catalog -#}
    {%- if action == 'registerTableInCatalog' -%}
        {%- set sql_command -%}
            CREATE TABLE {{ target_table }} USING DELTA LOCATION '{{ path }}'
        {%- endset -%}

    {#- Vacuum Table -#}
    {%- elif action == 'vacuumTable' -%}
        {%- if vacuumRetainNumHours != '' -%}
            {%- set sql_command -%}
                VACUUM {{ target_table }} RETAIN {{ vacuumRetainNumHours }} HOURS
            {%- endset -%}
        {%- else -%}
            {%- set sql_command -%}
                VACUUM {{ target_table }}
            {%- endset -%}
        {%- endif -%}

    {#- Optimize Table -#}
    {%- elif action == 'optimiseTable' -%}
        {%- set optimize_clause = 'OPTIMIZE ' ~ target_table -%}
        
        {%- if useOptimiseWhere -%}
            {%- set optimize_clause = optimize_clause ~ ' WHERE ' ~ optimiseWhere -%}
        {%- endif -%}
        
        {%- if useOptimiseZOrder -%}
            {%- set zorder_cols = optimiseZOrderColumns | trim -%}
            {%- set optimize_clause = optimize_clause ~ ' ZORDER BY (' ~ zorder_cols ~ ')' -%}
        {%- endif -%}
        
        {%- set sql_command = optimize_clause -%}

    {#- Restore Table -#}
    {%- elif action == 'restoreTable' -%}
        {%- if restoreVia == 'restoreViaVersion' -%}
            {%- set sql_command -%}
                RESTORE TABLE {{ target_table }} TO VERSION AS OF {{ restoreValue }}
            {%- endset -%}
        {%- elif restoreVia == 'restoreViaTimestamp' -%}
            {%- set sql_command -%}
                RESTORE TABLE {{ target_table }} TO TIMESTAMP AS OF '{{ restoreValue }}'
            {%- endset -%}
        {%- endif -%}

    {#- Delete from Table -#}
    {%- elif action == 'deleteFromTable' -%}
        {%- set sql_command -%}
            DELETE FROM {{ target_table }} WHERE {{ deleteCondition }}
        {%- endset -%}

    {#- Update Table -#}
    {%- elif action == 'updateTable' -%}
        {%- set update_cmd = 'UPDATE ' ~ target_table ~ ' SET ' -%}
        {%- set update_cmd = update_cmd ~ updateSetClause -%}
        
        {%- if updateCondition != '' -%}
            {%- set update_cmd = update_cmd ~ ' WHERE ' ~ updateCondition -%}
        {%- endif -%}
        
        {%- set sql_command = update_cmd -%}

    {#- Drop Table -#}
    {%- elif action == 'dropTable' -%}
        {%- set sql_command -%}
            DROP TABLE {{ target_table }}
        {%- endset -%}    

    {#- FSCK Repair Table -#}
    {%- elif action == 'fsckRepairTable' -%}
        {%- set sql_command -%}
            FSCK REPAIR TABLE {{ target_table }}
        {%- endset -%}

    {#- Run Custom DDL (modifies table) -#}
    {%- elif action == 'runDDL' -%}
        {%- set sql_command = runDDL | replace('{table_name}', target_table) -%}
    {%- endif -%}

    {#- Return the SQL command to be executed by dbt -#}
    {%- if sql_command != '' -%}
        {{ log("Table Operation - Action: " ~ action ~ " on Table: " ~ target_table, info=true) }}
        {{ log("SQL Command: " ~ sql_command, info=true) }}
        {% do run_query(sql_command) %}
        {{ return("SELECT '" ~ action ~ "' as operation, '" ~ target_table ~ "' as target_table, 'Success' as status, current_timestamp() as executed_at") }}
    {%- else -%}
        {{ log("No SQL command generated for action: " ~ action, info=true) }}
        {{ return("SELECT 'No Action' as operation, '" ~ target_table ~ "' as target_table, 'Failed' as status, current_timestamp() as executed_at") }}
    {%- endif -%}

{% endmacro %}
