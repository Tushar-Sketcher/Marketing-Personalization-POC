import json
import yaml
from pathlib import Path
from datetime import datetime
from dateutil import parser
from pyspark.sql import SparkSession
from pyspark.sql.types import *
import pyspark.sql.functions as f


class OperatorMapper:
    def __init__(self):
        self.operator_mapping = {
            'eq': '=',
            'neq': '!=',
            'contains': 'LIKE',
            'does not contain': 'NOT LIKE',
            'is available': 'IS NOT NULL',
            'is not available': 'IS NULL',
            'in': 'IN',
            'lt': '<',
            'gt': '>',
            'gte': '>=',
            'lte': '<=',
            'is between': 'BETWEEN',
            'is null': 'IS NULL',
            'is not null': 'IS NOT NULL',
            'is': '=',
            'is not': '!=',
            'is before date': '<',
            'is after date': '>',
            'is between dates': 'BETWEEN',
            'at least': '>=',
            'at most': '<='
        }


    def map_operator_to_sql(self, operator):
        """Map the given operator to its corresponding SQL operator."""
        sql_operator = self.operator_mapping.get(operator.lower())

        if sql_operator is None:
            raise ValueError(f"Unsupported operator: {operator}")

        return sql_operator


def cast_value(value, data_type):
    """Cast the value to the specified data type."""
    if data_type == 'INTEGER':
        return f"CAST({value} AS INTEGER)"
    elif data_type == 'DATE':
        try:
            date_value = parser.parse(value)
            return f"CAST('{value}' AS DATE)"
        except ValueError:
            raise ValueError(f"Invalid date format for value: {value}")
    elif data_type == 'VARCHAR':
        return f"CAST('{value}' AS VARCHAR)"
    else:
        raise ValueError(f"Unsupported data type: {data_type}")


def generate_conditions(criteria):
    """Generate SQL conditions based on the provided criteria."""
    conditions = []
    operator_mapper = OperatorMapper()

    for criterion in criteria:
        table_name = criterion['datasource']
        attr_name = criterion['name']
        value = criterion['value']
        operator = operator_mapper.map_operator_to_sql(criterion['Operator'])


        # Define data type based on the attribute name (customize as needed)
        # If some how we can get the data type of the columns of datasource using dtypes in spark or somthing then we can map them in below dict and further will be used to casting
        data_type_mapping = {
            'numeric_attribute': 'INTEGER',
            'date_attribute': 'DATE',
            'varchar_attribute': 'VARCHAR',
            # Add more data type mappings as needed
        }

        data_type = data_type_mapping.get(attr_name.lower())

        if operator.upper() == 'BETWEEN':
            value = value[1:-1].split(',')
            try:
                value_start = cast_value(value[0], data_type)
                value_end = cast_value(value[1], data_type)
                conditions.append((table_name, attr_name, operator, f"{value_start} AND {value_end}"))
            except ValueError as e:
                # print(f"Error: {e}. Skipping condition.") Once we implement data_type_mapping, This line will be uncommented and below condition will be removed.
                conditions.append((table_name, attr_name, operator, f'{value[0]} AND {value[1]}'))
        else:
            try:
                casted_value = cast_value(value, data_type)
                conditions.append((table_name, attr_name, operator, casted_value))
            except ValueError as e:
                # print(f"Error: {e}. Skipping condition.") Once we implement data_type_mapping, This line will be uncommented and below condition will be removed.
                conditions.append((table_name, attr_name, operator, value))

    return conditions

def event_type_aggregation_sql(query, aggregate, table, conj):
    """Generate SQL aggregation conditions for event-type criteria."""
    agg_mapping = {
            'average of': 'AVG',
            'sum of': 'SUM',
            'count of': 'COUNT',
            # Add more aggregate type mappings as needed
        }
    operator_mapper = OperatorMapper()
    
    conditions = []
    for agg_item in aggregate:
        agg_col = agg_item['name']
        agg_func = agg_mapping.get(agg_item['aggregates'].lower())
        agg_op = operator_mapper.map_operator_to_sql(agg_item['Operator'])
        agg_val = agg_item['value']

        condition = f"{agg_func}({agg_col}) {agg_op} {agg_val}"
        conditions.append(condition)
        
        prefix = f" {conj} ".join(conditions)
    
    query += f" GROUP BY zuid HAVING ( {prefix} )"
    
    return query


def group_sql_query(group):
    """Generate a SQL query for a group of criteria."""
    conjunction = group.get('Operator', 'AND').upper()
    criteria = group.get('criteria', [])
    tables_list = []
    condition_groups = []

    for criterion in criteria:
        table_name = criterion['datasource']
        if table_name not in tables_list:
            tables_list.append(table_name)

    conditions = generate_conditions(criteria)
    condition_groups.append((conjunction, conditions))

    if conjunction == 'AND' or conjunction == 'NONE':
        sql_query = f"SELECT zuid FROM {tables_list[0]}"

        for table in tables_list[1:]:
            sql_query += f" JOIN {table} ON {tables_list[0]}.zuid = {table}.zuid"

        if conditions:
            where_conditions = []
            for conjunction, conditions in condition_groups:
                condition_str = f" {f' {conjunction} '.join([f'{table}.{attr} {op} {value}' for table, attr, op, value in conditions])}"
                where_conditions.append(f"({''.join(condition_str)})")
            sql_query += f" WHERE {f' '.join(where_conditions)}"

    elif conjunction == 'OR':
        if conditions:
            combined_conditions = {}

            for condition in conditions:
                table_name, attr_name, op, value = condition
                key = (table_name)
                
                if key not in combined_conditions:
                    combined_conditions[key] = []
                
                combined_conditions[key].append(f"{table_name}.{attr_name} {op} {value}")

            union_queries = []

            for key, combined_condition_list in combined_conditions.items():
                table_name = key
                where_clause = f' {conjunction} '.join(combined_condition_list)
                query = f"SELECT zuid FROM {table_name} WHERE ({where_clause})"
                union_queries.append(query)
            sql_query = f" UNION ".join(union_queries)

    if group.get('type') == 'event' and group.get('aggregate'):
        aggregate = group.get('aggregate')
        aggregate_op = group.get('aggregate_operator', 'AND')
        sql_query = event_type_aggregation_sql(sql_query, aggregate, tables_list[0], aggregate_op) if len(aggregate) > 0 else ''
    
    return sql_query


def cte_views_sql(select_queries, outer_operator, count_flag):
    """Generate Common Table Expression (CTE) views."""
    cte_views = []

    for num, query in enumerate(select_queries):
        if num == 0:
            cte_views.append(f'WITH CTE_{num} AS ({query})')
        else:
            cte_views.append(f'CTE_{num} AS ({query})')

    cte_prefix = ', '.join(cte_views)

    if count_flag is True:
        prefix = 'COUNT(DISTINCT zuid)'
    else: 
        prefix = 'zuid'    

    if outer_operator == 'OR':
        final_selects = [f'SELECT {prefix} FROM CTE_{num}' for num in range(len(select_queries))]
        select_prefix = ' UNION '.join(final_selects)
        final_query = cte_prefix + ' ' + select_prefix

    elif outer_operator == 'AND':
        select_prefix = f"SELECT {prefix} FROM CTE_0" if len(select_queries) > 0 else ""
        for num in range(1, len(select_queries)):
            select_prefix += f" JOIN CTE_{num} ON CTE_0.zuid = CTE_{num}.zuid"
        final_query = cte_prefix + ' ' + select_prefix

    else:
        final_query = select_queries[0] if len(select_queries) > 0 else ""

    return final_query


def dynamic_sql_from_json(json_data):
    """Generate a dynamic SQL query based on the provided JSON structure."""
    outer_operator = json_data.get('Operator', 'AND').upper()
    count_flag = bool(json_data.get('Count', False))

    groups = json_data.get('groups', [])
    select_queries = []


    for group in groups:
        sql_query = group_sql_query(group)
        select_queries.append(sql_query)

    final_query = cte_views_sql(select_queries, outer_operator, count_flag)
    print(final_query)

    return final_query


if __name__ == '__main__':

    # Load JSON data from YAML file

    config = yaml.safe_load(open('segments.yaml'))
    segments = config['segments']
    data = []

    spark = SparkSession.builder.appName("SQL sgenerator").enableHiveSupport().config("spark.databricks.driver.strace.enabled", "true").getOrCreate()

    schema = StructType([StructField('segment_json', StringType(), nullable=True),
                         StructField('sql_query', StringType(), nullable=True),
                         StructField('update_date', DateType(), nullable=True)])

    for segment in segments:
        json_data = json.loads(segment['segment'])
        sql_queries = dynamic_sql_from_json(json_data)
        data.append([json_data, sql_queries, datetime.now()])
    
    # print(data)
    df = spark.createDataFrame(data, schema=schema)

    df.createOrReplaceTempView('sql_generator_view')
    
    # Create a Table naming as sql_generator_data under u_v_tushara database.
    spark.sql("CREATE TABLE IF NOT EXISTS platform_dev.u_v_tushara.sql_generator_data (segment_id INT, segment_json STRING, sql_query STRING, update_date DATE)")

    # Insert into sql_generator_data using the sql_generator_view. 
    spark.sql("""INSERT OVERWRITE TABLE platform_dev.u_v_tushara.sql_generator_data 
                SELECT row_number() OVER (ORDER BY update_date) as segment_id, segment_json, sql_query, update_date FROM sql_generator_view""")

    spark.sql("SELECT * FROM platform_dev.u_v_tushara.sql_generator_data").show(truncate=0)
