# Databricks notebook source
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

if __name__ == '__main__':
  # Sample campaign data
  campaign_data = [("ABC", 1, "S1", "B1", "F1"),
          ("ABC", 1, "S2", "B2", "F2"),
          ("ABC", 1, "S3", "B3", "F3"),
          ("DEF", 1, "S1", "B1", "F1"),
          ("DEF", 1, "S2", "B2", "F2"),
          ("DEF", 1, "S3", "B3", "F3"),
          ("MNO", 1, "S1", "B1", "F1"),
          ("MNO", 1, "S2", "B2", "F2"),
          ("ERF", 1, "S1", "B1", "F1"),
          ]

  spark = SparkSession.builder.appName("Content Assignment").enableHiveSupport().getOrCreate()

  spark.createDataFrame(campaign_data, ["Campaign", "Segment_Id", "Subject", "Body", "Footer"]).write \
    .mode("overwrite") \
    .saveAsTable("platform_dev.u_v_tushara.campaign_2")

  # Read segment table 
  segment = spark.sql("select * from platform_dev.u_v_tushara.segment")

  # Iterate through each row in the segment DataFrame
  for row in segment.collect():
    # Perform segment query to collect uids
    zuid_df = spark.sql(row['sql'])

    # Read campaign table
    query = "select * from platform_dev.u_v_tushara.campaign_2 where Segment_Id = {id} order by Subject, Body, Footer".format(id = row['segment_id'])
    campaign = spark.sql(query)

    # Check if campaign DataFrame is empty
    if campaign.isEmpty():
      print("No Campaigns are present for the segment_id = {id} in campaign table".format(id=row['segment_id']))
    
    else:
      campaign = campaign.dropDuplicates()
      
      # Add a row number to campain df
      campaign_df = campaign.withColumn("row_num_campaign", F.row_number().over(Window.partitionBy("Campaign",'Segment_Id').orderBy("Campaign","Segment_Id","Subject", "Body", "Footer")))
      campaign_df.show()

      # Group by campaign and count occurrences
      dist_campaign = campaign_df.groupBy('Campaign').count().alias('count').orderBy('Campaign')

      result_dfs = []
      # Iterate through each campaign and its count
      for i, (campaign,campaign_count) in enumerate(dist_campaign.collect(), 1):
        # Add row number for zuid's df and reset the index based on num_campaign_records in campaign table. Please check output df printed. 
        zuid_df = zuid_df.withColumn("row_num_zuid", F.row_number().over(Window.orderBy("zuid"))) \
                        .withColumn("row_num_zuid", (F.col("row_num_zuid") - 1) % campaign_count + 1)

        # Join the the zuid df with campaign df on row number columns
        df = zuid_df.join(campaign_df, (F.col("row_num_zuid") == F.col("row_num_campaign")) & (campaign_df["Campaign"] == campaign)) \
                          .drop("row_num_zuid", "row_num_campaign")
        result_dfs.append(df)
        # df.show(truncate=0)

      # Combine individual result DataFrames into a single DataFrame
      combined_result_df = result_dfs[0]
      for df in result_dfs[1:]:
        combined_result_df = combined_result_df.unionByName(df)
      combined_result_df.show(100, truncate=0)
