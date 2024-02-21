# Marketing-Personalization-POC
The objective of this project is to analyze and optimize campaign targeting by distributing user IDs (zuids) across multiple campaigns associated with different segments. The project involves fetching data from a segment table and a campaign table stored in a database. 

Here's an overview of the project workflow:

Data Acquisition:

The project starts by retrieving segment information from a segment table and corresponding user IDs (zuids) associated with each segment. This data provides insights into the target audience for various campaigns.

Additionally, it fetches campaign details from a campaign table, including the campaign name, segment ID, subject, body, and footer content.

Data Processing:

The retrieved data undergoes several processing steps:
Eliminating any duplicate campaigns from the campaign data.
Adding a row number to each campaign entry to facilitate matching with the user IDs later.
Campaign Distribution:

The project calculates the count of each distinct campaign and orders them. This step ensures an even distribution of user IDs across campaigns.
Iterative Campaign Processing:

For each campaign, the project resets the row number index of the user IDs DataFrame based on the count of the current campaign. This step evenly distributes the user IDs across campaigns.

It then joins the user IDs DataFrame with the campaign DataFrame based on their respective row number columns and campaign IDs.

The resulting DataFrame for each campaign join is stored.

Result Combination:

Finally, the project combines the results of all campaign joins into a single DataFrame. This consolidated DataFrame contains user IDs mapped to their corresponding campaigns.
Output and Analysis:

The project outputs the combined DataFrame for further analysis and optimization of campaign targeting strategies.
