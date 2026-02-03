from pyspark.sql import DataFrame
from pyspark.sql import SQLContext
from pyspark.sql.functions import array, lit, struct, expr, concat_ws, collect_list

from prophecy.config import ConfigBase


def typed_lit(obj):
    if isinstance(obj, list):
        return array([typed_lit(x) for x in obj])
    elif isinstance(obj, dict):
        elementsList = []
        for key, value in obj.items():
            elementsList.append(typed_lit(value).alias(key))
        return struct(elementsList)
    elif isinstance(obj, ConfigBase.SecretValue):
        return lit(str(obj))
    else:
        try:
            # int, float, string
            return lit(obj)
        except:
            # class type
            return typed_lit(obj.__dict__)


def has_column(df, col):
    try:
        df[col]
        return True
    except:
        return False


def createScalaList(spark, l):
    return spark.sparkContext._jvm.PythonUtils.toList(l)


def createScalaColumnList(spark, cols):
    return spark.sparkContext._jvm.PythonUtils.toList([item._jc for item in list(cols)])


def createScalaMap(spark, dict):
    return spark.sparkContext._jvm.PythonUtils.toScalaMap(dict)


def createScalaColumnMap(spark, dict):
    jcolDict = {k: col._jc for k, col in dict.items()}
    return spark.sparkContext._jvm.PythonUtils.toScalaMap(jcolDict)


def createScalaColumnOption(spark, value):
    if value is None:
        return spark.sparkContext._jvm.scala.Option.apply(None)
    else:
        return spark.sparkContext._jvm.scala.Some(value._jc)


def createScalaOption(spark, value):
    if value is None:
        return spark.sparkContext._jvm.scala.Option.apply(None)
    else:
        return spark.sparkContext._jvm.scala.Some(value)


def isBlank(myString):
    if isinstance(myString, str) and myString and myString.strip():
        return False
    return True


def directory_listing(spark, directory_path, recursive, pattern):
    try:
        if spark.sparkContext.emptyRDD():
            df_java = spark.sparkContext._jvm.io.prophecy.abinitio.ScalaFunctions._directory_listing_v2(
                spark._jsparkSession,
                directory_path,
                recursive,
                pattern)
            return DataFrame(df_java, SQLContext(spark.sparkContext, sparkSession=spark))
    except AttributeError as ex:
        """
            Changes: For Shared UC cluster compatibility           
        """
        from prophecy.libs.uc_shared_utils import directory_listing as shared_directory_listing
        return shared_directory_listing(spark=spark, directory_path=directory_path, recursive=recursive,
                                        pattern=pattern)


def filter_columns_by_expr(spark, df, expr):
    try:
        if spark.sparkContext.emptyRDD():
            df_java = spark.sparkContext._jvm.io.prophecy.abinitio.ScalaFunctions.filterColumnsByExpr(
                spark._jsparkSession, df._jdf, expr
            )
            return DataFrame(df_java, SQLContext(spark.sparkContext, sparkSession=spark))
    except AttributeError as ex:
        """
        Changes: For Shared UC cluster compatibility
        Note: Putting AttributeError instead of pyspark.errors.exceptions.base.PySparkAttributeError (>=3.4.0)
              for backward compatibility purpose            
        """
        from prophecy.libs.uc_shared_utils import filter_columns_by_expr as shared_filter_columns_by_expr
        return shared_filter_columns_by_expr(spark=spark, dataframe=df, expression=expr)


def filter_columns_by_type(spark, df, types):
    try:
        if spark.sparkContext.emptyRDD():
            df_java = spark.sparkContext._jvm.io.prophecy.abinitio.ScalaFunctions.filterColumnsByType(
                spark._jsparkSession, df._jdf, types
            )
            return DataFrame(df_java, SQLContext(spark.sparkContext, sparkSession=spark))
    except AttributeError as ex:
        """
        Changes: For Shared UC cluster compatibility
        Note: Putting AttributeError instead of pyspark.errors.exceptions.base.PySparkAttributeError (>=3.4.0)
              for backward compatibility purpose            
        """
        from prophecy.libs.uc_shared_utils import filter_columns_by_type as shared_filter_columns_by_type
        return shared_filter_columns_by_type(dataframe=df, types=types)


def send_email_with_attachment(spark, smtp_host, smtp_port, username, password,
                               email_from, email_to, subject, body,
                               attachment_paths, cc, bcc,
                               isBodyHtml=False, cleanLocalFiles=False):
    spark.sparkContext._jvm.io.prophecy.abinitio.ScalaFunctions.sendEmailWithAttachment(
        spark._jsparkSession,
        smtp_host, smtp_port,
        username, password,
        email_from, email_to,
        subject, body,
        attachment_paths, cc, bcc,
        isBodyHtml, cleanLocalFiles
    )


def send_email_with_attachment_for_email_data(smtp_host, smtp_port, username, password,
                                              email_from, email_to, subject, body,
                                              attachment_paths, cc, bcc,
                                              isBodyHtml=False, cleanLocalFiles=True):
    """
    Changes: For Shared UC cluster compatibility
    Note: Creating a separate function to handle email data gem for uc shared cluster.
          In UC Shared cluster, not possible to access hdfs file system using sparkContext. So, new function is getting created.
    """
    from prophecy.libs.uc_shared_utils import \
        send_email_with_attachment_for_email_data as shared_send_email_with_attachment_for_email_data
    shared_send_email_with_attachment_for_email_data(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        username=username,
        password=password,
        email_from=email_from,
        email_to=email_to,
        subject=subject,
        body=body,
        attachment_paths=attachment_paths,
        cc=cc,
        bcc=bcc,
        is_body_html=isBodyHtml,
        clean_local_files=cleanLocalFiles
    )


def export_tableau_hyperfile(spark_df, tableau_token_name, tableau_token, tableau_site_id,
                             tableau_host_url, tableau_extract_name, tableau_project_name):
    try:
        import pantab
        import tableauserverclient as TSC
        tableau_hyper_path = f"{tableau_extract_name}.hyper"
        df = spark_df.toPandas()
        pantab.frame_to_hyper(df, tableau_hyper_path, table=tableau_hyper_path)
        # todo: make sure to delete the files after uploading to tableau server
        print(f"Data written to Hyper file successfully at {tableau_hyper_path}.")
        # Using Personal Access Token
        tableau_auth = TSC.PersonalAccessTokenAuth(tableau_token_name,
                                                   tableau_token,
                                                   site_id=tableau_site_id)
        server = TSC.Server(tableau_host_url, use_server_version=True)

        with server.auth.sign_in(tableau_auth):
            all_projects = TSC.Pager(server.projects.get)
            project = [project for project in all_projects if project.name == tableau_project_name][0]
            print("Writing into project: " + str(project.name))
            # Publish Hyper file to Tableau Server
            new_datasource_item = TSC.DatasourceItem(project.id)
            datasource = server.datasources.publish(new_datasource_item, tableau_hyper_path, 'Overwrite')
            print("Datasource published. ID: ", datasource.id)
    except Exception as e:
        print(f"An error occurred while exporting tableau hyperfile: {e}")


def xml_parse(in0, column_to_parse, parsingMethod, sampleRecord, schema):
    try:
        from pyspark.sql.functions import from_xml, schema_of_xml, lit
        from pyspark.sql.types import StructType
        if parsingMethod in ["parseFromSampleRecord", "parseAuto"]:
            if parsingMethod == "parseFromSampleRecord":
                sample_xml = sampleRecord
            else:
                sample_xml = in0.limit(1).select(column_to_parse).collect()[0][0]
            xml_schema = schema_of_xml(lit(sample_xml))
            output_df = in0.withColumn("xml_parsed_content",
                                       from_xml(column_to_parse, xml_schema))
        else:
            try:
                xml_schema = schema
                output_df = in0.withColumn("xml_parsed_content",
                                           expr(f"from_xml({column_to_parse}, '{xml_schema}')"))
            except Exception as e:
                xml_schema = StructType.fromDDL(schema)
                output_df = in0.withColumn("xml_parsed_content",
                                           from_xml(column_to_parse, xml_schema))
        return output_df
    except Exception as e:
        print(f"An error occurred while fetching data: {e}")
        raise e


def json_parse(in0, column_to_parse, parsingMethod, sampleRecord, schema, schemaInferCount):
    try:
        from pyspark.sql.functions import from_json, schema_of_json, lit
        from pyspark.sql.types import StructType
        if parsingMethod in ["parseFromSampleRecord", "parseAuto"]:
            if parsingMethod == "parseFromSampleRecord":
                sample_json = sampleRecord
                json_schema = schema_of_json(lit(sample_json))
                output_df = in0.withColumn("json_parsed_content",
                                           from_json(column_to_parse, json_schema))
            else:
                combined_json_df = in0.limit(schemaInferCount).select(
                    concat_ws(",", collect_list(column_to_parse)).alias("combined_json"))
                sample_json = "[" + combined_json_df.collect()[0]["combined_json"] + "]"
                json_schema = schema_of_json(lit(sample_json))
                output_df = in0.withColumn("json_parsed_content",
                                           from_json(column_to_parse, json_schema).getItem(0))
        else:
            try:
                json_schema = schema
                output_df = in0.withColumn("json_parsed_content",
                                           expr(f"from_json({column_to_parse}, '{json_schema}')"))
            except Exception as e:
                json_schema = StructType.fromDDL(schema)
                output_df = in0.withColumn("json_parsed_content",
                                           from_json(column_to_parse, json_schema))
        return output_df
    except Exception as e:
        print(f"An error occurred while fetching data: {e}")
        raise e


def get_email_html_dataframe(df, num_rows=20, title="Prophecy Data Export") -> str:
    # Collect the top `num_rows` rows from the DataFrame
    rows = df.limit(num_rows).collect()
    if len(rows) == 0:
        print("Empty dataframe")
        return ""
    columns = df.columns

    # Start building the HTML string for the entire df
    df_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            .content {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
            }}
            .header {{
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                text-align: center;
            }}
            .body {{
                margin: 20px;
            }}
            .footer {{
                background-color: #f1f1f1;
                color: #888;
                text-align: center;
                padding: 10px;
                margin-top: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <div class="content">
            <div class="header">
                <h1>{title}</h1>
            </div>
            <div class="body">
                <p>Dear <strong>Prophecy User</strong>,</p>
                <p>Below is the export of data <strong>(Top {num_rows} rows)</strong></p>
    """.format(title=title, num_rows=num_rows)

    # Generate the HTML table for the DataFrame
    df_html += "<table>\n"
    # Add the table header with column names
    df_html += "<thead><tr>"
    for col in columns:
        df_html += f"<th>{col}</th>"
    df_html += "</tr></thead>\n"

    # Add the table rows with data
    df_html += "<tbody>\n"
    for row in rows:
        df_html += "<tr>"
        for col in columns:
            df_html += f"<td>{row[col]}</td>"
        df_html += "</tr>\n"
    df_html += "</tbody>\n"
    df_html += "</table>"

    # Add closing sections for the body and footer
    df_html += """
            </div>
            <div class="footer">
                <p>This is an automated email. Please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return df_html


def write_df_locally(_df, attachmentFormat, attachmentName):
    from pathlib import Path
    import os

    pdf = _df.toPandas()
    if pdf.empty:
        print("Converted Pandas DataFrame is empty, nothing to attach.")
        return ""

    file_name = f"/tmp/{attachmentName}"
    # Check write permissions before writing
    directory = os.path.dirname(file_name)
    if not os.access(directory, os.W_OK):
        raise Exception(f"No write access to directory: {directory}")

    # Determine the file extension and write the data accordingly
    if attachmentFormat == "CSV":
        file_name += ".csv"

        pdf.to_csv(file_name, index=False)
    elif attachmentFormat == "EXCEL":
        file_name += ".xlsx"
        pdf.to_excel(file_name, index=False)
    elif attachmentFormat == "JSON":
        file_name += ".json"
        pdf.to_json(file_name, orient="records", lines=True)
    elif attachmentFormat == "PARQUET":
        file_name += ".parquet"
        pdf.to_parquet(file_name, index=False)
    else:
        raise Exception("Invalid format")

    # Verify that the file has been created
    if not Path(file_name).exists():
        raise FileNotFoundError(f"Error writing temporary file: {file_name} locally for attachment")
    print(f"Writing completed. File saved at: {file_name}")
    return file_name
