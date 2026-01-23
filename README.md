# Bybit to Notion Sync

This Python script fetches trade and transaction history from Bybit (v5 API) and incrementally syncs it to a Notion database. It's designed for multi-account management (though simplified in the current version), robust error handling, and extensibility.

## Features

- **Incremental Sync**: Fetches only new activities since the last sync.
- **Bybit V5 API**: Uses the latest Bybit API for linear perpetual contracts.
- **Extensible Design**: Adapter pattern allows for adding other exchanges (e.g., Binance, MEXC) in the future.
- **Robustness**: Handles API rate limits and connection errors gracefully.
- **Monitoring**: Logs to both console and a `sync.log` file. Sends alerts to Discord on failures.
- **Tax Reporting**: Generates a monthly PnL summary in CSV or Excel format.

## Project Structure

```
bybit_notion_sync/
├── src/
│   ├── adapters/      # Exchange API clients (e.g., Bybit)
│   ├── clients/       # External service clients (e.g., Notion)
│   ├── services/      # Core logic (syncing, reporting)
│   ├── utils/         # Helpers (logging, alerting)
│   ├── config.py      # Configuration loader
│   └── main.py        # Main entry point
├── .env.example       # Example environment variables
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd bybit_notion_sync
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables**:
    -   Copy `.env.example` to a new file named `.env`.
    -   Open `.env` and fill in your details:
        -   `BYBIT_API_KEY`: Your Bybit API key. A Master Key is recommended for sub-account access.
        -   `BYBIT_API_SECRET`: Your Bybit API secret.
        -   `NOTION_TOKEN`: Your Notion integration token.
        -   `NOTION_DB_ID`: The ID of your Notion database.
        -   `DISCORD_WEBHOOK_URL` (Optional): For receiving error alerts.

## How to Run

### Sync Data

To run the synchronization service:

```bash
python src/main.py
```

The script will fetch new records from Bybit and add them to your Notion database.

### Generate Tax Report

To generate a monthly PnL report for the current year:

```bash
# For CSV format
python src/main.py --report

# For Excel format
python src/main.py --report-excel
```
The report will be saved in the project's root directory.

## Notion Database & Dashboard Setup

For the script to work, your Notion database must have the following columns with the **exact names and types**:

-   **Symbol**: `Select`
-   **Side**: `Select` (Values like 'Buy', 'Sell', 'Funding' will be added automatically)
-   **Size**: `Number`
-   **Entry/Exit Price**: `Number`
-   **Fee**: `Number`
-   **PnL**: `Number`
-   **Timestamp**: `Date`
-   **Subaccount**: `Text`

### Dashboard Formulas

You can add `Formula` columns to your database to create a simple performance dashboard.

#### 1. Win/Loss Status (IsWin)

Create a `Formula` column named `IsWin` to quickly see if a trade was profitable. This excludes funding fees.

```
if(prop("PnL") > 0, "✅ Win", if(prop("PnL") < 0, "❌ Loss", "⚪️ Break-even"))
```

#### 2. Win Rate

Notion's `rollup` feature can calculate the win rate.

1.  In your database, add a "Relation" property pointing to the database itself. You can hide this property.
2.  Create a `Rollup` column named "Win Rate".
    -   **Relation**: Select the relation you just created.
    -   **Property**: Select your `IsWin` formula property.
    -   **Calculate**: Select "Percent per group" -> "✅ Win".

This will show the percentage of trades that are wins.

*Note: This is a simplified approach. For a more accurate trading-focused win rate, you might want to filter out non-trade entries like 'Funding'.*

#### 3. Max Drawdown (Limitation)

Calculating a true, running Max Drawdown is not feasible with Notion's standard formulas because they cannot reference previous rows' values in a sequence.

However, you can easily find your **Largest Single Loss**.

1.  Create a `Rollup` on the `PnL` property.
2.  For the **Calculate** option, choose **Min**. This will show you the single largest negative PnL value in your database.

## Deployment

### Cron Job (Linux/macOS)

You can schedule the script to run automatically using a cron job.

1.  Open your crontab editor:
    ```bash
    crontab -e
    ```

2.  Add a line to run the script at your desired frequency. For example, to run every hour:
    ```cron
    0 * * * * /usr/bin/python /path/to/your/project/bybit_notion_sync/src/main.py >> /path/to/your/project/bybit_notion_sync/cron.log 2>&1
    ```
    *Make sure to use the absolute paths to your Python interpreter and script.*

### AWS Lambda

Deploying as a Lambda function is a great serverless option.

1.  **Package**: Create a ZIP file containing the `src` directory and all dependencies from `requirements.txt`.
    ```bash
    pip install -r requirements.txt -t ./package
    cd package
    zip -r ../deployment.zip .
    cd ..
    zip -g deployment.zip -r src
    ```

2.  **Lambda Function**:
    -   Create a new Lambda function with a Python runtime.
    -   Upload the `deployment.zip` file.
    -   Set the **Handler** to `src.main.main`.
    -   In **Configuration -> Environment variables**, add all the variables from your `.env` file (`BYBIT_API_KEY`, `NOTION_TOKEN`, etc.).
    -   Increase the **Timeout** under **Configuration -> General configuration** to at least 1 minute, as the initial sync might take time.

3.  **Trigger**:
    -   Add an **EventBridge (CloudWatch Events)** trigger.
    -   Configure it to run on a schedule (e.g., `rate(1 hour)`).
