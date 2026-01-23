# src/services/reporter.py
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

from ..clients.notion import NotionClient
from ..utils.logger import log

class ReporterService:
    """
    Service for generating reports from data stored in Notion.
    """

    def __init__(self, notion_client: NotionClient):
        self.notion = notion_client

    def generate_pnl_report(self, output_format: str = 'csv'):
        """
        Generates a monthly PnL report from the Notion database.

        Args:
            output_format: The desired output format ('csv' or 'excel').
        """
        log.info("Starting PnL report generation...")
        
        # 1. Fetch all data from Notion
        all_records = self.notion.query_all_records()
        if not all_records:
            log.warning("No records found in Notion. Cannot generate report.")
            return

        # 2. Parse records into a list of dicts
        parsed_records = self._parse_notion_results(all_records)
        if not parsed_records:
            log.warning("Could not parse any valid records from Notion data.")
            return
            
        # 3. Create a Pandas DataFrame
        df = pd.DataFrame(parsed_records)

        # 4. Data processing
        # Convert timestamp to datetime objects
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        # Set Timestamp as the index
        df.set_index('Timestamp', inplace=True)
        
        # 5. Group by month and sum PnL
        # 'M' is a frequency string for month-end frequency
        monthly_pnl = df['PnL'].resample('M').sum()
        
        log.info("Monthly PnL aggregated:")
        log.info(monthly_pnl)

        # 6. Save the report
        current_year = datetime.now().year
        file_name = f"tax_report_{current_year}"
        
        if output_format == 'csv':
            file_path = f"{file_name}.csv"
            monthly_pnl.to_csv(file_path)
            log.info(f"Successfully saved report to {file_path}")
        elif output_format == 'excel':
            file_path = f"{file_name}.xlsx"
            monthly_pnl.to_excel(file_path, sheet_name='Monthly PnL')
            log.info(f"Successfully saved report to {file_path}")
        else:
            log.error(f"Unsupported report format: {output_format}")

    def _parse_notion_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parses the raw list of Notion page objects into a simpler list of dictionaries.
        """
        parsed = []
        for page in results:
            try:
                properties = page["properties"]
                record = {
                    "Timestamp": properties["Timestamp"]["date"]["start"],
                    "PnL": properties["PnL"]["number"],
                    # Add other fields if needed for more complex reports
                }
                # Filter out records with no PnL value
                if record["PnL"] is not None:
                    parsed.append(record)
            except (KeyError, TypeError) as e:
                page_id = page.get('id', 'N/A')
                log.warning(f"Skipping record {page_id} due to parsing error: {e}. Check if schema matches.")
                continue
        return parsed
