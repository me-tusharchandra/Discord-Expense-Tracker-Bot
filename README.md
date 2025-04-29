# Discord Expense Tracker Bot

A Discord bot that tracks both expenses and income, then updates them to a Google Sheet with advanced visualization and reporting features.
--------

![Demo](GIF.gif)

## Setup Instructions

### 1. Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section and create a bot
4. Enable "Message Content Intent" under Privileged Gateway Intents
5. Under "OAuth2" > "URL Generator", select:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Read Messages/View Channels`
6. Copy the bot token
7. Use the generated URL to add the bot to your server

### 2. Google Sheets Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Google Sheets API
4. Create a service account and download the credentials JSON file
5. Create a new Google Sheet and share it with the service account email
6. Copy the spreadsheet ID from the URL

#### Important Note on API Quota Limits
Google Sheets API has usage quotas:
- Free tier: 500 requests per 100 seconds per project, 100 requests per 100 seconds per user
- If you exceed these limits, you'll get a 429 "Resource Exhausted" error
- The bot includes rate limiting to help manage these quotas
- For heavy usage, consider:
  - Upgrading to a paid Google Cloud account
  - Implementing a local database cache
  - Batching requests

### 3. Environment Setup
1. Create a `.env` file in the project root with the following variables:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
   SPREADSHEET_ID=your_google_sheet_id_here
   ```
2. Place your Google Sheets credentials JSON file in the project root

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the Bot
```bash
python bot.py
```

## Available Commands

The bot supports tracking both income and expenses through an easy-to-use interface:

### Income & Expense Tracking

- `/expense amount:<amount> description:<description> [category:<category>]`
- `/income amount:<amount> description:<description> [category:<category>]`
- `/category entry_id:<id> category:<category>`

### Financial Analysis

- `/balance [period:<All Time/This Month/This Week>]` - View your current financial balance
- `/total [period:<All Time/This Month/This Week>] [type:<Expenses/Income/All>]` - View total amounts
- `/summary [period:<All Time/This Month/This Week>] [type:<Expenses/Income/All>]` - View summary by category
- `/history [limit:<number>] [type:<All/Expenses/Income>]` - View recent entries

### Data Visualization

- `/chart chart_type:<Chart Type> [period:<Time Period>]` - Generate visual charts of your finances

Available chart types:
- **Expense By Category** - Pie chart showing expense distribution
- **Income By Category** - Pie chart showing income sources
- **Income vs Expense** - Bar chart comparing income, expenses and balance
- **Balance Over Time** - Timeline showing daily financial activity

### Traditional Prefix Commands 

These still work for backward compatibility:

- `!expense <amount> <description>`
- `!income <amount> <description>`
- `!category <entry_id> <category>`
- `!balance [all/month/week]`

## Example Usage

### Recording Transactions
1. Record an expense:
   ```
   /expense amount:15.99 description:Lunch at Chipotle category:Food
   ```

2. Record income:
   ```
   /income amount:1500 description:Monthly Salary category:Salary
   ```

3. Categorize a transaction:
   ```
   /category entry_id:1 category:Groceries
   ```

### Analyzing Your Finances
1. Check your balance:
   ```
   /balance period:This Month
   ```

2. View spending by category:
   ```
   /summary type:Expenses period:This Month
   ```

3. Check your recent income:
   ```
   /history limit:10 type:Income
   ```

4. View total income for the week:
   ```
   /total period:This Week type:Income
   ```

### Visualizing Your Finances
1. Generate a pie chart of expenses:
   ```
   /chart chart_type:Expense By Category period:This Month
   ```

2. Compare income vs expenses:
   ```
   /chart chart_type:Income vs Expense period:This Month
   ```

3. See your balance over time:
   ```
   /chart chart_type:Balance Over Time period:This Week
   ```

## Troubleshooting

### Google Sheets API Quota Issues
If you see an error like `gspread.exceptions.APIError: {'code': 429, 'message': 'Resource has been exhausted...'}`:

1. **Temporary Solution**: Wait a few minutes before trying again
2. **Verify API Quota**: Go to Google Cloud Console > APIs & Services > Dashboard > Google Sheets API > Quotas
3. **Increase Quota**: For serious usage, upgrade to a paid Google Cloud account
4. **Reduce Usage**: Make fewer requests by batching data or using local storage 