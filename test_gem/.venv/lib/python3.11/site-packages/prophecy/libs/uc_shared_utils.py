import os
import re
from pyspark.sql.functions import *
from pyspark.sql import SparkSession, DataFrame, Row
from pyspark.sql.types import *
from datetime import datetime
from pathlib import Path


def list_local_files(spark, directory_path, recursive, pattern):
    """
    List files in a directory with local file system.

    Args:
        spark: The Spark session.
        directory_path: The path to the local file directory.
        recursive: Whether to list files recursively in a directory.
        pattern: Glob pattern for file matching.

    Returns:
        pyspark.sql.DataFrame: A DataFrame with file information.
    """
    files = []
    for root, dirs, filenames in os.walk(directory_path):
        for filename in filenames:
            if pattern and not pattern.search(filename):
                continue  # Skip files that don't match the pattern
            file_path = os.path.join(root, filename)
            stat_info = os.stat(file_path)
            creation_time = datetime.fromtimestamp(stat_info.st_ctime)
            modification_time = datetime.fromtimestamp(stat_info.st_mtime)
            parent_directory = os.path.dirname(file_path)
            file_type = "file"
            files.append({
                "name": filename,
                "path": file_path,
                "size": stat_info.st_size,
                "creation_time": creation_time,
                "modification_time": modification_time,
                "parent_directory": parent_directory,
                "file_type": file_type
            })
        if not recursive:
            break
    if not files:
        from pyspark.sql.types import StructType, StructField, StringType, LongType, TimestampType

        schema = StructType([
            StructField("name", StringType(), True),
            StructField("path", StringType(), True),
            StructField("size", LongType(), True),
            StructField("creation_time", TimestampType(), True),
            StructField("modification_time", TimestampType(), True),
            StructField("parent_directory", StringType(), True),
            StructField("file_type", StringType(), True),
        ])
        # Return an empty DataFrame with the correct schema
        return spark.createDataFrame([], schema)

    return (spark.createDataFrame(files)
            .withColumn("name", expr("name").cast("string"))
            .withColumn("path", expr("path").cast("string"))
            .withColumn("size", expr("size").cast("long"))
            .withColumn("creation_time", expr("creation_time").cast("timestamp"))
            .withColumn("modification_time", expr("modification_time").cast("timestamp"))
            .withColumn("parent_directory", expr("parent_directory").cast("string"))
            .withColumn("file_type", expr("file_type").cast("string"))
            .select("name", "path", "size", "creation_time", "modification_time", "parent_directory", "file_type")
            )


def list_hdfs_files(spark, directory_path, recursive, pattern):
    """
    List files in a directory for hdfs file system.

    Args:
        spark: The Spark session.
        directory_path: The path to the hdfs file directory.
        recursive: Whether to list files recursively in a directory.
        pattern: Glob pattern for file matching.

    Returns:
        pyspark.sql.DataFrame: A DataFrame with file information.
    """
    # Read directory files using Spark
    if recursive:
        file_df = (
            spark.read.format("binaryFile")
            .option("pathGlobFilter", pattern)
            .option("recursiveFileLookup", recursive)
            .load(directory_path)
        )
    else:
        directory_path: str = directory_path.rstrip('/')
        """
            If the directory does not have any file, it raises dataPathNotExistError
            Returning emptyDataFrame in exception block if no file in the directory
        """
        file_df = (
            spark.read.format("binaryFile")
            .option("recursiveFileLookup", False)
            .load(f"{directory_path}/*.*")
        )

        # Filter as per the pattern
        file_df = file_df.withColumn("name", expr("substring_index(path, '/', -1)").cast("string")).filter(
            col("name").rlike(pattern))

        """
            In Spark, if any directory path contains a dot (`.`), Spark continues to traverse into it
            even if `recursiveFileLookup` is set to `False`.
            Example:
                - If `directory_path = "test.csv"`, Spark will still attempt to traverse into it.
            
            To avoid this, we check if the concatenation of `directory_path` and `file_name` matches the `path`.
            If they don't match, the record will be discarded.
        """
        file_df = file_df.filter(col("path").contains(concat(lit(directory_path), lit("/"), col("name"))))

    # Filter out metadata files starting with metadata_prefixes
    metadata_prefixes = ["_committed", "_started", "_SUCCESS", "_part"]
    condition = ~expr(" or ".join([f"name LIKE '{prefix}%'" for prefix in metadata_prefixes]))

    # Extract file metadata
    return (
        file_df
        .withColumn("name", expr("substring_index(path, '/', -1)").cast("string"))
        .withColumn("path", col("path").cast("string"))
        .withColumn("size", col("length").cast("long"))
        .withColumn("creation_time", lit(None).cast("timestamp"))
        .withColumn("modification_time", col("modificationTime").cast("timestamp"))
        .withColumn("parent_directory",
                    expr(
                        "substring_index(path, '/', size(split(path, '/')) - 1)").cast(
                        "string"))
        .withColumn("file_type", lit("file").cast("string"))
        .filter(condition)
        .select("name", "path", "size", "creation_time", "modification_time", "parent_directory", "file_type")
    )


def directory_listing(spark: SparkSession, directory_path: str, recursive: bool, pattern: str):
    """
    List files in a directory with hdfs or local file system.

    Args:
        spark: The Spark session.
        directory_path: The path to the hdfs or local file directory.
                        Path starting with file:// would be considered as local file system
        recursive: Whether to list files recursively in a directory.
        pattern: String pattern for file matching.

    Returns:
        pyspark.sql.DataFrame: A DataFrame with file information.
    """
    try:
        match_pattern = pattern.replace("*", ".*").replace("!", "^") + r"$"
        if directory_path.startswith("file:/"):
            files = list_local_files(spark=spark,
                                     directory_path=Path(directory_path[6:]),
                                     recursive=recursive,
                                     pattern=re.compile(match_pattern))
        else:
            files = list_hdfs_files(spark=spark,
                                    directory_path=directory_path,
                                    recursive=recursive,
                                    pattern=pattern if recursive else match_pattern)

        return files
    except Exception as e:
        # Check if the error message contains "dataPathNotExistError"
        if "dataPathNotExistError" not in str(e):
            raise e

        # Define an empty DataFrame with the same schema
        from pyspark.sql.types import StructType, StructField, StringType, LongType, TimestampType
        empty_schema = StructType([
            StructField("name", StringType(), True),
            StructField("path", StringType(), True),
            StructField("size", LongType(), True),
            StructField("creation_time", TimestampType(), True),
            StructField("modification_time", TimestampType(), True),
            StructField("parent_directory", StringType(), True),
            StructField("file_type", StringType(), False)
        ])

        return spark.createDataFrame([], empty_schema)


def evaluate_expression(dataframe: DataFrame, user_expression: str, selected_column_names: list,
                        spark: SparkSession) -> DataFrame:
    """
    Filters columns in a Spark DataFrame based on a given expression.

    Args:
        dataframe: The input DataFrame.
        user_expression: A string representing the expression to evaluate for selected columns
        selected_column_names: A list of columns selected to evaluate the expression
        spark: A SparkSession object.

    Returns:
        A new DataFrame containing modified dataframe columns along with unmodified columns.

    Raises:
        Exception: If an error occurs during column evaluation.
    """

    try:
        # Filter columns that are in the selected_column_names list
        df_columns = (spark.createDataFrame(
            [(col_name,) for col_name in dataframe.columns if col_name in selected_column_names],
            ["column_name"]
        ))

        # Add the new column names using the user expression
        new_columns = (df_columns
                       .withColumn("new_column_name", expr(user_expression))
                       .collect()
                       )
        new_columns_list = [(row["column_name"], row["new_column_name"]) for row in new_columns]

        # Identify remaining columns that are not selected
        remaining_columns = [col(col_name) for col_name in dataframe.columns if col_name not in selected_column_names]

        # Create the renamed column list using old and new column names
        renamed_columns_list = [col(old_col).alias(new_col) for old_col, new_col in new_columns_list]

        # Select renamed columns and remaining columns
        return dataframe.select(*renamed_columns_list, *remaining_columns)

    except Exception as e:
        print(f"Error while evaluating expression {user_expression} for select columns {selected_column_names}: {e}")
        raise e

def filter_columns_by_type(dataframe: DataFrame, types: str) -> DataFrame:
    """
    Filters columns in a DataFrame based on specified data types.

    Args:
        dataframe (DataFrame): The DataFrame to filter.
        types (str): A comma-separated string of data types to keep.

    Returns:
        DataFrame: A new DataFrame containing only columns with matching data types.

    Raises:
        Exception: If an error occurs during column filtering.
    """

    type_array = types.split(",") if types else []
    data_types = [
        StringType if t == "string" else
        ShortType if t == "short" else
        ByteType if t == "byte" else
        LongType if t == "long" else
        IntegerType if t == "int" else
        DoubleType if t == "double" else
        DecimalType if t == "decimal" else
        FloatType if t == "float" else
        BooleanType if t == "boolean" else
        BinaryType if t == "binary" else
        DateType if t == "date" else
        TimestampType if t == "timestamp" else
        ArrayType if t == "array" else
        StructType if t == "struct" else
        MapType if t == "map" else
        StringType  # Default type
        for t in type_array
    ]

    try:
        columns_to_keep = [f.name for f in dataframe.schema.fields if isinstance(f.dataType, tuple(data_types))]
        return dataframe.select(*[dataframe[col_name] for col_name in columns_to_keep])

    except Exception as e:
        print(f"An error occurred while filtering columns by type: {e}")
        return dataframe


def filter_columns_by_expr(spark: SparkSession, dataframe: DataFrame, expression: str):
    """
    Filters columns in a Spark DataFrame based on a given expression.

    Args:
        spark: A SparkSession object.
        dataframe: The input DataFrame.
        expression: A string representing the expression to evaluate for each column.
                    The expression should evaluate to a boolean value (True or False).

    Returns:
        A new DataFrame containing only the columns where the expression evaluates to True.

    Raises:
        Exception: If an error occurs during column filtering.
    """

    type_sizes = {
        BooleanType: 1,
        ByteType: 1,
        ShortType: 2,
        IntegerType: 4,
        LongType: 8,
        FloatType: 4,
        DoubleType: 8,
        DecimalType: 16,  # Approximate size
        StringType: -1,
        BinaryType: -1,
        DateType: 4,
        TimestampType: 8,
        ArrayType: -1,
        StructField: -1,
        MapType: -1,
        NullType: 1,
    }

    type_column = {
        BooleanType: "boolean",
        ByteType: "byte",
        ShortType: "short",
        IntegerType: "int",
        LongType: "long",
        FloatType: "float",
        DoubleType: "double",
        DecimalType: "decimal",
        StringType: "string",
        BinaryType: "binary",
        DateType: "date",
        TimestampType: "timestamp",
        ArrayType: "array",
        StructType: "struct",
        MapType: "map",
        NullType: "null",
    }

    try:

        column_names = [
            Row(field.name, type_column.get(type(field.dataType), -1), type_sizes.get(type(field.dataType), -1), i)
            for i, field in enumerate(dataframe.schema.fields)
        ]

        col_schema = StructType(
            [
                StructField("column_name", StringType(), nullable=False),
                StructField("column_type", StringType(), nullable=False),
                StructField("column_size", IntegerType(), nullable=False),
                StructField("field_number", IntegerType(), nullable=False),
            ]
        )

        col_df = spark.createDataFrame(column_names, col_schema)

        col_df_with_flag = col_df.withColumn("flag", expr(expression))

        filtered_column_names = [row.column_name for row in
                                 col_df_with_flag.filter(col("flag") == True).select("column_name").collect()]
        return dataframe.select(filtered_column_names)

    except Exception as e:
        print("Error while filtering columns by expression:", e)
        return dataframe


def send_email_with_attachment_for_email_data(
        smtp_host,
        smtp_port,
        username,
        password,
        email_from,
        email_to,
        subject,
        body="",
        attachment_paths="",
        cc="",
        bcc="",
        is_body_html=False,
        clean_local_files=True
):
    """
    Sends an email with optional attachments using pure Python.

    :param smtp_host: SMTP host name
    :param smtp_port: SMTP port number (integer)
    :param username: Username for SMTP authentication
    :param password: Password for SMTP authentication
    :param email_from: Sender email address
    :param email_to: Comma-separated string of recipient email addresses
    :param subject: Email subject
    :param body: Email body (plain text or HTML)
    :param attachment_paths: Comma-separated list of file paths for attachments
    :param cc: Comma-separated list of CC email addresses
    :param bcc: Comma-separated list of BCC email addresses
    :param is_body_html: Boolean flag indicating whether the body is HTML
    :param clean_local_files: Boolean flag indicating whether to delete temporary files after sending
    """
    import os
    import smtplib

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    # Build the email message.
    msg = MIMEMultipart()
    msg["From"] = email_from
    to_emails = [x.strip() for x in email_to.split(",") if x.strip()]
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject

    # Process CC and BCC.
    cc_emails = [x.strip() for x in cc.split(",") if x.strip()]
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)
    bcc_emails = [x.strip() for x in bcc.split(",") if x.strip()]

    # Set the email body.
    if is_body_html and body.strip():
        # Create an alternative part with both HTML and a plain text fallback.
        alt_part = MIMEMultipart("alternative")
        fallback_text = ("Error occurred while adding HTML body, "
                         "Your email client does not support HTML messages.")
        alt_part.attach(MIMEText(fallback_text, "plain"))
        alt_part.attach(MIMEText(body, "html"))
        msg.attach(alt_part)
    else:
        if not body.strip():
            msg.attach(MIMEText("No body content provided.", "plain"))
        else:
            msg.attach(MIMEText(body, "plain"))

    # Process attachments.
    files_to_clean = []  # This list will hold temporary file paths to delete later.
    if attachment_paths.strip():
        attachment_list = [x.strip() for x in attachment_paths.split(",") if x.strip()]
        files_to_clean = attachment_list
        for file_path in attachment_list:
            try:
                # Attach the file.
                with open(file_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f'attachment; filename="{os.path.basename(file_path)}"')
                msg.attach(part)
            except Exception as e:
                print(f"Error processing attachment {file_path}: {e}")
                raise e

    # Send the email.
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(username, password)
        all_recipients = to_emails + cc_emails + bcc_emails
        server.sendmail(email_from, all_recipients, msg.as_string())
        server.quit()
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise e
    finally:
        # Clean up any temporary files if clean_local_files=True
        if clean_local_files:
            for temp_file in files_to_clean:
                try:
                    if os.path.exists(temp_file):
                        print(f"Deleting temporary file {temp_file}")
                        os.remove(temp_file)
                except Exception as e:
                    print(f"Error deleting temporary file {temp_file}: {e}")