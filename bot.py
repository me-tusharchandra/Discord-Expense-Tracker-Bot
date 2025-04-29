import io
import os
import time
import gspread
import discord
import traceback
import numpy as np
import pandas as pd
import seaborn as sns
from dotenv import load_dotenv
from calendar import monthrange
import matplotlib.pyplot as plt
from discord.ext import commands
from discord import app_commands
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from collections import defaultdict
from typing import Optional, Literal
from datetime import datetime, timedelta
from matplotlib.colors import LinearSegmentedColormap
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables
load_dotenv()

# Discord bot setup with minimal required intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Google Sheets setup with rate limiting
class RateLimitedClient:
    def __init__(self, client):
        self.client = client
        self.last_request_time = 0
        self.min_request_interval = 1.0  # At least 1 second between requests

    def get_spreadsheet(self, spreadsheet_id):
        self._wait_for_rate_limit()
        return self.client.open_by_key(spreadsheet_id)
    
    def _wait_for_rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

# Set up Google Sheets with rate limiting
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_name(
    os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE'), scope)
client = gspread.authorize(credentials)
rate_limited_client = RateLimitedClient(client)

# Spreadsheet properties
HEADERS = ['User', 'Amount', 'Description', 'Category', 'Type', 'Date']

try:
    spreadsheet = rate_limited_client.get_spreadsheet(os.getenv('SPREADSHEET_ID'))
    worksheet = spreadsheet.sheet1
except Exception as e:
    print(f"Error connecting to Google Sheets: {e}")
    print("The bot will start, but Google Sheets features won't work until this is fixed.")
    worksheet = None

# Ensure headers exist and are in the right format
def ensure_headers():
    if worksheet is None:
        return False
        
    try:
        # Get current headers or initialize if sheet is empty
        try:
            current_headers = worksheet.row_values(1)
            if not current_headers:  # Empty row
                worksheet.insert_row(HEADERS, 1)
                print("Initialized empty sheet with headers")
                return True
        except IndexError:  # No rows in sheet
            worksheet.insert_row(HEADERS, 1)
            print("Created headers in empty sheet")
            return True
            
        # Check if headers match expected format
        if current_headers != HEADERS:
            # Clear the first row and insert correct headers
            worksheet.delete_row(1)
            worksheet.insert_row(HEADERS, 1)
            print(f"Updated headers from {current_headers} to {HEADERS}")
            
        return True
    except Exception as e:
        print(f"Error ensuring headers: {e}")
        traceback.print_exc()
        return False

# Process records into a proper DataFrame
def get_processed_records():
    if worksheet is None:
        return pd.DataFrame(columns=HEADERS)
        
    try:
        # Get all data from sheet
        all_values = worksheet.get_all_values()
        
        # Handle empty sheet
        if not all_values:
            ensure_headers()
            return pd.DataFrame(columns=HEADERS)
            
        # Get header row
        headers = all_values[0]
        
        # Get all data rows
        data_rows = all_values[1:] if len(all_values) > 1 else []
        
        # Create DataFrame
        df = pd.DataFrame(data_rows, columns=headers)
        
        # Handle empty DataFrame
        if df.empty:
            return pd.DataFrame(columns=HEADERS)
            
        # Ensure Amount column is numeric
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        
        # Handle NaN values
        df = df.fillna({'Amount': 0, 'Category': 'Uncategorized', 'Type': 'Expense'})
        
        # Ensure Date column is datetime
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        return df
    except Exception as e:
        print(f"Error processing records: {e}")
        traceback.print_exc()
        return pd.DataFrame(columns=HEADERS)

# Helper functions
def get_categories():
    try:
        df = get_processed_records()
        if 'Category' in df.columns:
            categories = df['Category'].unique().tolist()
            if categories:
                return categories
    except Exception as e:
        print(f"Error getting categories: {e}")
    
    # Default categories if retrieval fails
    return ['Food', 'Transportation', 'Utilities', 'Entertainment', 'Shopping', 'Salary', 'Gifts', 'Other']

# Get all available categories for autocomplete
def get_all_categories():
    custom_categories = get_categories()
    default_categories = ['Food', 'Transportation', 'Utilities', 'Entertainment', 'Shopping', 'Salary', 'Gifts', 'Other']
    
    # Combine and deduplicate
    all_categories = list(set(custom_categories + default_categories))
    all_categories.sort()
    return all_categories

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    if ensure_headers():
        print("Headers are properly set up in the Google Sheet")
    else:
        print("Warning: Could not set up headers in Google Sheet")
        
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
        traceback.print_exc()

# Category autocomplete
async def category_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    categories = get_all_categories()
    return [
        app_commands.Choice(name=category, value=category)
        for category in categories if current.lower() in category.lower()
    ][:25]  # Discord limits choices to 25

# Traditional commands (keep these for backward compatibility)
@bot.command(name='expense')
async def add_expense_prefix(ctx, amount: float, *, description: str):
    """Add an expense to the Google Sheet (prefix command)"""
    if worksheet is None:
        await ctx.send("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers before adding data
        ensure_headers()
        
        # Add the expense to the sheet
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.append_row([str(ctx.author), str(amount), description, 'Uncategorized', 'Expense', current_time])
        await ctx.send(f'Expense of ${amount:.2f} for "{description}" has been recorded!')
    except Exception as e:
        await ctx.send(f'Error recording expense: {str(e)}')
        print(f"Error in add_expense_prefix: {e}")
        traceback.print_exc()

@bot.command(name='income')
async def add_income_prefix(ctx, amount: float, *, description: str):
    """Add income to the Google Sheet (prefix command)"""
    if worksheet is None:
        await ctx.send("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers before adding data
        ensure_headers()
        
        # Add the income to the sheet
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.append_row([str(ctx.author), str(amount), description, 'Uncategorized', 'Income', current_time])
        await ctx.send(f'Income of ${amount:.2f} for "{description}" has been recorded!')
    except Exception as e:
        await ctx.send(f'Error recording income: {str(e)}')
        print(f"Error in add_income_prefix: {e}")
        traceback.print_exc()

# Slash Commands
@bot.tree.command(name="expense", description="Record a new expense")
@app_commands.describe(
    amount="The amount spent (e.g., 15.99)",
    description="What the expense was for (optional)",
    category="Category of the expense (optional)"
)
@app_commands.autocomplete(category=category_autocomplete)
async def add_expense(interaction: discord.Interaction, amount: float, description: Optional[str] = "N/A", category: Optional[str] = 'Uncategorized'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers before adding data
        ensure_headers()
        
        # Use N/A if description is empty
        if not description or description.strip() == "":
            description = "N/A"
        
        # Add the expense to the sheet
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.append_row([str(interaction.user), str(amount), description, category, 'Expense', current_time])
        await interaction.response.send_message(f'Expense of ${amount:.2f} for "{description}" has been recorded in category "{category}"!')
    except Exception as e:
        await interaction.response.send_message(f'Error recording expense: {str(e)}')
        print(f"Error in add_expense: {e}")
        traceback.print_exc()

@bot.tree.command(name="income", description="Record new income")
@app_commands.describe(
    amount="The amount received (e.g., 1000.00)",
    description="Source of the income (optional)",
    category="Category of income (optional)"
)
@app_commands.autocomplete(category=category_autocomplete)
async def add_income(interaction: discord.Interaction, amount: float, description: Optional[str] = "N/A", category: Optional[str] = 'Salary'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers before adding data
        ensure_headers()
        
        # Use N/A if description is empty
        if not description or description.strip() == "":
            description = "N/A"
        
        # Add the income to the sheet
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.append_row([str(interaction.user), str(amount), description, category, 'Income', current_time])
        await interaction.response.send_message(f'Income of ${amount:.2f} from "{description}" has been recorded in category "{category}"!')
    except Exception as e:
        await interaction.response.send_message(f'Error recording income: {str(e)}')
        print(f"Error in add_income: {e}")
        traceback.print_exc()

@bot.tree.command(name="category", description="Set category for an entry")
@app_commands.describe(
    entry_id="The ID of the entry to categorize",
    category="Category to assign"
)
@app_commands.autocomplete(category=category_autocomplete)
async def set_category(interaction: discord.Interaction, entry_id: int, category: str):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get all records
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:  # Only header row or empty
            await interaction.response.send_message("No entries found to categorize.")
            return
            
        if 1 <= entry_id <= len(all_values) - 1:
            # Update the category (add 1 because entry_id is 1-indexed, and we skip header row)
            worksheet.update_cell(entry_id + 1, 4, category)
            await interaction.response.send_message(f'Category for entry #{entry_id} has been set to "{category}"')
        else:
            await interaction.response.send_message(f'Invalid entry ID. Please use a number between 1 and {len(all_values) - 1}')
    except Exception as e:
        await interaction.response.send_message(f'Error setting category: {str(e)}')
        print(f"Error in set_category: {e}")
        traceback.print_exc()

@bot.tree.command(name="balance", description="View your current balance")
@app_commands.describe(
    period="Time period for calculating balance (default: all)"
)
@app_commands.choices(period=[
    app_commands.Choice(name="All Time", value="all"),
    app_commands.Choice(name="This Month", value="month"),
    app_commands.Choice(name="This Week", value="week")
])
async def balance(interaction: discord.Interaction, period: str = 'all'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Check if there's data
        if df.empty:
            await interaction.response.send_message("No transactions found.")
            return
        
        # Filter by user
        df = df[df['User'] == str(interaction.user)]
        
        if df.empty:
            await interaction.response.send_message("You have no recorded transactions.")
            return

        # Filter by period
        if period.lower() == 'month':
            current_month = datetime.now().strftime('%Y-%m')
            df = df[df['Date'].dt.strftime('%Y-%m') == current_month]
            period_text = 'this month'
        elif period.lower() == 'week':
            current_week = datetime.now().isocalendar()[1]
            df = df[df['Date'].dt.isocalendar().week == current_week]
            period_text = 'this week'
        else:
            period_text = 'all time'

        # Calculate income and expenses
        income = df[df['Type'] == 'Income']['Amount'].sum()
        expenses = df[df['Type'] == 'Expense']['Amount'].sum()
        balance = income - expenses
        
        message = f"**Balance Summary for {period_text}:**\n"
        message += f"Total Income: ${income:.2f}\n"
        message += f"Total Expenses: ${expenses:.2f}\n"
        message += f"**Net Balance: ${balance:.2f}**"
        
        if balance > 0:
            message += "\n✅ You're in the green! Keep it up!"
        elif balance < 0:
            message += "\n❌ You're spending more than you earn."
        else:
            message += "\n⚖️ Your budget is perfectly balanced."
            
        await interaction.response.send_message(message)
    except Exception as e:
        await interaction.response.send_message(f'Error calculating balance: {str(e)}')
        print(f"Error in balance: {e}")
        traceback.print_exc()

@bot.tree.command(name="total", description="View total expenses for a period")
@app_commands.describe(
    period="Time period for expenses (default: all)",
    type="Type of transactions to total (default: expense)"
)
@app_commands.choices(period=[
    app_commands.Choice(name="All Time", value="all"),
    app_commands.Choice(name="This Month", value="month"),
    app_commands.Choice(name="This Week", value="week")
])
@app_commands.choices(type=[
    app_commands.Choice(name="Expenses", value="Expense"),
    app_commands.Choice(name="Income", value="Income"),
    app_commands.Choice(name="All", value="All")
])
async def total_entries(interaction: discord.Interaction, period: str = 'all', type: str = 'Expense'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Check if there's data
        if df.empty:
            await interaction.response.send_message("No transactions found.")
            return

        # Filter by user
        df = df[df['User'] == str(interaction.user)]
        
        if df.empty:
            await interaction.response.send_message("You have no recorded transactions.")
            return

        # Filter by period
        if period.lower() == 'month':
            current_month = datetime.now().strftime('%Y-%m')
            df = df[df['Date'].dt.strftime('%Y-%m') == current_month]
            period_text = 'this month'
        elif period.lower() == 'week':
            current_week = datetime.now().isocalendar()[1]
            df = df[df['Date'].dt.isocalendar().week == current_week]
            period_text = 'this week'
        else:
            period_text = 'all time'

        # Filter by transaction type
        if type != 'All':
            df = df[df['Type'] == type]
        
        # Check if data exists after filtering
        if df.empty:
            type_text = "expenses" if type == 'Expense' else "income" if type == 'Income' else "transactions"
            await interaction.response.send_message(f"No {type_text} found for {period_text}.")
            return
            
        total = df['Amount'].sum()
        type_text = "expenses" if type == 'Expense' else "income" if type == 'Income' else "transactions"
        
        await interaction.response.send_message(f'Total {type_text} for {period_text}: ${total:.2f}')
    except Exception as e:
        await interaction.response.send_message(f'Error calculating total: {str(e)}')
        print(f"Error in total_entries: {e}")
        traceback.print_exc()

@bot.tree.command(name="summary", description="View financial summary by category")
@app_commands.describe(
    period="Time period for summary (default: month)",
    type="Type of transactions to include in detail (default: All)"
)
@app_commands.choices(period=[
    app_commands.Choice(name="All Time", value="all"),
    app_commands.Choice(name="This Month", value="month"),
    app_commands.Choice(name="This Week", value="week")
])
@app_commands.choices(type=[
    app_commands.Choice(name="Expenses", value="Expense"),
    app_commands.Choice(name="Income", value="Income"),
    app_commands.Choice(name="All", value="All")
])
async def financial_summary(interaction: discord.Interaction, period: str = 'month', type: str = 'All'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Check if there's data
        if df.empty:
            await interaction.response.send_message("No transactions found.")
            return

        # Filter by user
        df = df[df['User'] == str(interaction.user)]
        
        if df.empty:
            await interaction.response.send_message("You have no recorded transactions.")
            return

        # Filter by period
        if period.lower() == 'month':
            current_month = datetime.now().strftime('%Y-%m')
            df = df[df['Date'].dt.strftime('%Y-%m') == current_month]
            period_text = 'this month'
        elif period.lower() == 'week':
            current_week = datetime.now().isocalendar()[1]
            df = df[df['Date'].dt.isocalendar().week == current_week]
            period_text = 'this week'
        else:
            period_text = 'all time'
        
        # Check if data exists after filtering by period
        if df.empty:
            await interaction.response.send_message(f"No transactions found for {period_text}.")
            return

        # Create full summary regardless of type parameter
        income_df = df[df['Type'] == 'Income'].copy()
        expense_df = df[df['Type'] == 'Expense'].copy()
        
        # Calculate totals
        total_income = income_df['Amount'].sum()
        total_expense = expense_df['Amount'].sum()
        net_balance = total_income - total_expense
        
        # Build the summary message
        message = f"**Financial Summary for {period_text}:**\n\n"
        
        # Add Income section if there's income data
        if not income_df.empty:
            income_by_category = income_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
            message += "**💰 Income:**\n"
            for category, amount in income_by_category.items():
                message += f"{category}: ${amount:.2f}\n"
            message += f"**Total Income: ${total_income:.2f}**\n\n"
        else:
            message += "**💰 Income:** None recorded\n\n"
        
        # Add Expense section if there's expense data
        if not expense_df.empty:
            expense_by_category = expense_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
            message += "**💸 Expenses:**\n"
            for category, amount in expense_by_category.items():
                message += f"{category}: ${amount:.2f}\n"
            message += f"**Total Expenses: ${total_expense:.2f}**\n\n"
        else:
            message += "**💸 Expenses:** None recorded\n\n"
        
        # Add Net Balance section
        message += f"**⚖️ Net Balance: ${net_balance:.2f}**"
        
        # Add indicator based on balance
        if net_balance > 0:
            message += " ✅"
        elif net_balance < 0:
            message += " ❌"
        else:
            message += " ⚖️"
        
        await interaction.response.send_message(message)
    except Exception as e:
        await interaction.response.send_message(f'Error generating summary: {str(e)}')
        print(f"Error in financial_summary: {e}")
        traceback.print_exc()

@bot.tree.command(name="history", description="View recent financial history")
@app_commands.describe(
    limit="Number of recent entries to display (default: 5)",
    type="Type of transactions to show (default: all)"
)
@app_commands.choices(type=[
    app_commands.Choice(name="All", value="All"),
    app_commands.Choice(name="Expenses", value="Expense"),
    app_commands.Choice(name="Income", value="Income")
])
async def financial_history(interaction: discord.Interaction, limit: int = 5, type: str = 'All'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Check if there's data
        if df.empty:
            await interaction.response.send_message("No transactions found.")
            return
        
        # Filter by user
        df = df[df['User'] == str(interaction.user)]
        
        if df.empty:
            await interaction.response.send_message("You have no recorded transactions.")
            return
        
        # Filter by transaction type
        if type != 'All':
            df = df[df['Type'] == type]
        
        # Check if data exists after filtering
        if df.empty:
            type_text = "expenses" if type == 'Expense' else "income" if type == 'Income' else "transactions"
            await interaction.response.send_message(f"No {type_text} found.")
            return
            
        # Get the most recent entries
        recent_entries = df.sort_values('Date', ascending=False).head(limit)
        
        message = '**Recent Financial History:**\n'
        for _, entry in recent_entries.iterrows():
            amount = entry['Amount']
            if entry['Type'] == 'Expense':
                prefix = "💸"
            else:
                prefix = "💰"
                
            date_str = entry['Date'].strftime('%Y-%m-%d') if pd.notna(entry['Date']) else 'Unknown date'
            
            message += f"{prefix} ${amount:.2f} - {entry['Description']} " + \
                      f"({entry['Category']}) - {date_str} " + \
                      f"[{entry['Type']}]\n"
        
        await interaction.response.send_message(message)
    except Exception as e:
        await interaction.response.send_message(f'Error retrieving history: {str(e)}')
        print(f"Error in financial_history: {e}")
        traceback.print_exc()

@bot.tree.command(name="help_expense", description="Show all available commands")
async def help_expense(interaction: discord.Interaction):
    help_text = """
    **Available Commands:**
    
    **Income & Expense Tracking:**
    `/expense amount:<amount> description:<description> [category:<category>]` - Record an expense
    `/income amount:<amount> description:<description> [category:<category>]` - Record income
    `/category entry_id:<id> category:<category>` - Set category for an entry
    
    **Reporting & Analysis:**
    `/balance [period:<All Time/This Month/This Week>]` - View your current balance
    `/total [period:<All Time/This Month/This Week>] [type:<Expenses/Income/All>]` - View total amounts
    `/summary [period:<All Time/This Month/This Week>] [type:<Expenses/Income/All>]` - View summary by category
    `/history [limit:<number>] [type:<All/Expenses/Income>]` - View recent entries
    
    **Traditional Commands:**
    `!expense <amount> <description>` - Record an expense
    `!income <amount> <description>` - Record income
    
    **Examples:**
    ```
    /expense amount:15.99 description:Lunch at Chipotle category:Food
    /income amount:1500 description:Monthly Salary category:Salary
    /category entry_id:1 category:Groceries
    /balance period:This Month
    /summary type:Expenses period:This Month
    /history limit:10 type:Income
    ```
    """
    await interaction.response.send_message(help_text)

# Keep traditional commands (updating only the ones that need updating)
@bot.command(name='category')
async def set_category_prefix(ctx, entry_id: int, category: str):
    """Set category for an entry (prefix command)"""
    if worksheet is None:
        await ctx.send("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get all values
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:  # Only header row or empty
            await ctx.send("No entries found to categorize.")
            return
            
        if 1 <= entry_id <= len(all_values) - 1:
            # Update the category (add 1 because entry_id is 1-indexed, and we skip header row)
            worksheet.update_cell(entry_id + 1, 4, category)
            await ctx.send(f'Category for entry #{entry_id} has been set to "{category}"')
        else:
            await ctx.send(f'Invalid entry ID. Please use a number between 1 and {len(all_values) - 1}')
    except Exception as e:
        await ctx.send(f'Error setting category: {str(e)}')
        print(f"Error in set_category_prefix: {e}")
        traceback.print_exc()

@bot.command(name='balance')
async def balance_prefix(ctx, period: str = 'all'):
    """View your current balance (prefix command)"""
    if worksheet is None:
        await ctx.send("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Check if there's data
        if df.empty:
            await ctx.send("No transactions found.")
            return
        
        # Filter by user
        df = df[df['User'] == str(ctx.author)]
        
        if df.empty:
            await ctx.send("You have no recorded transactions.")
            return

        # Filter by period
        if period.lower() == 'month':
            current_month = datetime.now().strftime('%Y-%m')
            df = df[df['Date'].dt.strftime('%Y-%m') == current_month]
            period_text = 'this month'
        elif period.lower() == 'week':
            current_week = datetime.now().isocalendar()[1]
            df = df[df['Date'].dt.isocalendar().week == current_week]
            period_text = 'this week'
        else:
            period_text = 'all time'

        # Calculate income and expenses
        income = df[df['Type'] == 'Income']['Amount'].sum()
        expenses = df[df['Type'] == 'Expense']['Amount'].sum()
        balance = income - expenses
        
        message = f"**Balance Summary for {period_text}:**\n"
        message += f"Total Income: ${income:.2f}\n"
        message += f"Total Expenses: ${expenses:.2f}\n"
        message += f"**Net Balance: ${balance:.2f}**"
        
        await ctx.send(message)
    except Exception as e:
        await ctx.send(f'Error calculating balance: {str(e)}')
        print(f"Error in balance_prefix: {e}")
        traceback.print_exc()

# Helper function to create visualizations
def generate_chart_image(df, chart_type, period_text):
    """Generate chart image from dataframe"""
    plt.figure(figsize=(10, 6))
    plt.style.use('dark_background')  # Discord dark theme friendly
    
    # Set default colors
    colors = {
        'Income': '#4CAF50',  # Green
        'Expense': '#F44336',  # Red
        'Balance': '#3F51B5',  # Blue
        'Background': '#2F3136',  # Discord dark theme
        'Text': '#FFFFFF'      # White text
    }
    
    # Customize figure
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(colors['Background'])
    ax.set_facecolor(colors['Background'])
    
    # Customize text color
    plt.rcParams['text.color'] = colors['Text']
    plt.rcParams['axes.labelcolor'] = colors['Text']
    plt.rcParams['xtick.color'] = colors['Text']
    plt.rcParams['ytick.color'] = colors['Text']
    
    # Title based on chart type
    title = f"{chart_type.title()} Overview for {period_text.title()}"
    
    # Financial charts based on type
    if chart_type == 'expense_by_category':
        if df.empty or 'Expense' not in df['Type'].values:
            plt.figtext(0.5, 0.5, "No expense data available", ha='center', color=colors['Text'], fontsize=14)
        else:
            expense_df = df[df['Type'] == 'Expense']
            expense_by_cat = expense_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
            
            # Create pie chart
            plt.pie(expense_by_cat, labels=expense_by_cat.index, autopct='%1.1f%%', 
                    startangle=140, colors=sns.color_palette("hls", len(expense_by_cat)))
            plt.axis('equal')
            plt.title(f"Expense Distribution by Category for {period_text.title()}", color=colors['Text'], pad=20)
    
    elif chart_type == 'income_by_category':
        if df.empty or 'Income' not in df['Type'].values:
            plt.figtext(0.5, 0.5, "No income data available", ha='center', color=colors['Text'], fontsize=14)
        else:
            income_df = df[df['Type'] == 'Income']
            income_by_cat = income_df.groupby('Category')['Amount'].sum().sort_values(ascending=False)
            
            # Create pie chart
            plt.pie(income_by_cat, labels=income_by_cat.index, autopct='%1.1f%%', 
                    startangle=140, colors=sns.color_palette("Greens", len(income_by_cat)))
            plt.axis('equal')
            plt.title(f"Income Distribution by Category for {period_text.title()}", color=colors['Text'], pad=20)
    
    elif chart_type == 'balance_over_time':
        if df.empty:
            plt.figtext(0.5, 0.5, "No data available", ha='center', color=colors['Text'], fontsize=14)
        else:
            # Create daily aggregation
            df['Day'] = df['Date'].dt.date
            
            # Get income and expense by day
            daily_income = df[df['Type'] == 'Income'].groupby('Day')['Amount'].sum().reset_index()
            daily_expense = df[df['Type'] == 'Expense'].groupby('Day')['Amount'].sum().reset_index()
            
            # Create date range for all days in the period
            if period_text == 'this month':
                now = datetime.now()
                _, last_day = monthrange(now.year, now.month)
                start_date = datetime(now.year, now.month, 1).date()
                end_date = datetime(now.year, now.month, last_day).date()
            elif period_text == 'this week':
                now = datetime.now()
                start_date = (now - timedelta(days=now.weekday())).date()
                end_date = now.date()
            else:
                if not df.empty:
                    start_date = df['Date'].min().date()
                    end_date = df['Date'].max().date()
                else:
                    start_date = datetime.now().date()
                    end_date = datetime.now().date()
            
            # Create full date range
            all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
            date_df = pd.DataFrame({'Day': all_dates.date})
            
            # Merge with income and expense data
            date_df = date_df.merge(daily_income, on='Day', how='left').rename(columns={'Amount': 'Income'})
            date_df = date_df.merge(daily_expense, on='Day', how='left').rename(columns={'Amount': 'Expense'})
            
            # Fill NaN with 0
            date_df['Income'] = date_df['Income'].fillna(0)
            date_df['Expense'] = date_df['Expense'].fillna(0)
            
            # Calculate running balance
            date_df['Balance'] = date_df['Income'] - date_df['Expense']
            date_df['Cumulative Balance'] = date_df['Balance'].cumsum()
            
            # Plot
            ax.bar(date_df['Day'], date_df['Income'], color=colors['Income'], alpha=0.7, label='Income')
            ax.bar(date_df['Day'], -date_df['Expense'], color=colors['Expense'], alpha=0.7, label='Expense')
            ax.plot(date_df['Day'], date_df['Cumulative Balance'], color=colors['Balance'], 
                    marker='o', linestyle='-', linewidth=2, label='Cumulative Balance')
            
            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            plt.xticks(rotation=45)
            
            # Format y-axis with dollar signs
            def currency_formatter(x, pos):
                return f'${abs(x):.0f}'
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(currency_formatter))
            
            # Add legend and grid
            ax.legend(loc='best', facecolor=colors['Background'])
            ax.grid(True, linestyle='--', alpha=0.3)
            ax.set_axisbelow(True)
            
            # Add title and labels
            ax.set_title(f"Income, Expenses and Balance for {period_text.title()}", 
                        color=colors['Text'], pad=20)
            ax.set_xlabel('Date', color=colors['Text'])
            ax.set_ylabel('Amount ($)', color=colors['Text'])
    
    elif chart_type == 'income_vs_expense':
        # Summary bar chart comparing income vs. expense
        if df.empty:
            plt.figtext(0.5, 0.5, "No data available", ha='center', color=colors['Text'], fontsize=14)
        else:
            # Calculate totals by type
            totals = df.groupby('Type')['Amount'].sum()
            
            # Default values if either category is missing
            income_total = totals.get('Income', 0)
            expense_total = totals.get('Expense', 0)
            balance = income_total - expense_total
            
            # Plot
            categories = ['Income', 'Expense', 'Balance']
            values = [income_total, expense_total, balance]
            bar_colors = [colors['Income'], colors['Expense'], 
                        colors['Balance'] if balance >= 0 else '#F44336']
            
            # Create bar chart
            bars = ax.bar(categories, values, color=bar_colors, width=0.6)
            
            # Add data labels on top of bars
            for bar in bars:
                height = bar.get_height()
                label_text = f'${abs(height):.2f}'
                ax.annotate(label_text,
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom',
                            color=colors['Text'])
            
            # Customize the plot
            ax.set_title(f"Financial Summary for {period_text.title()}", color=colors['Text'], pad=20)
            ax.set_ylabel('Amount ($)', color=colors['Text'])
            ax.grid(True, linestyle='--', alpha=0.3, axis='y')
            ax.set_axisbelow(True)
    
    # Save the chart to a buffer
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    
    return buf

async def filter_data_by_period(df, interaction, period='month'):
    """Filter data by period and user"""
    if df.empty:
        return df, "No data"
    
    # Filter by user
    df = df[df['User'] == str(interaction.user)]
    
    if df.empty:
        return df, "No user data"
    
    # Filter by period
    if period.lower() == 'month':
        current_month = datetime.now().strftime('%Y-%m')
        df = df[df['Date'].dt.strftime('%Y-%m') == current_month]
        period_text = 'this month'
    elif period.lower() == 'week':
        current_week = datetime.now().isocalendar()[1]
        df = df[df['Date'].dt.isocalendar().week == current_week]
        period_text = 'this week'
    else:
        period_text = 'all time'
    
    return df, period_text

@bot.tree.command(name="chart", description="Generate financial charts and visualizations")
@app_commands.describe(
    chart_type="Type of chart to generate",
    period="Time period for the chart (default: month)"
)
@app_commands.choices(chart_type=[
    app_commands.Choice(name="Expense By Category", value="expense_by_category"),
    app_commands.Choice(name="Income By Category", value="income_by_category"),
    app_commands.Choice(name="Income vs Expense", value="income_vs_expense"),
    app_commands.Choice(name="Balance Over Time", value="balance_over_time")
])
@app_commands.choices(period=[
    app_commands.Choice(name="All Time", value="all"),
    app_commands.Choice(name="This Month", value="month"),
    app_commands.Choice(name="This Week", value="week")
])
async def financial_chart(interaction: discord.Interaction, chart_type: str, period: str = 'month'):
    if worksheet is None:
        await interaction.response.send_message("Google Sheets connection is not available. Please check the bot logs.")
        return
    
    # Let the user know we're generating the chart
    await interaction.response.defer(thinking=True)
    
    try:
        # Ensure headers first
        ensure_headers()
        
        # Get processed records
        df = get_processed_records()
        
        # Filter data by period and user
        filtered_df, period_text = await filter_data_by_period(df, interaction, period)
        
        if filtered_df.empty:
            await interaction.followup.send(f"No data available for {period_text}.")
            return
        
        # Generate chart image
        chart_buffer = generate_chart_image(filtered_df, chart_type, period_text)
        
        # Create a discord file from the buffer
        chart_file = discord.File(fp=chart_buffer, filename="financial_chart.png")
        
        # Send the chart as an attachment
        chart_title = chart_type.replace('_', ' ').title()
        await interaction.followup.send(
            content=f"**{chart_title} for {period_text.title()}**",
            file=chart_file
        )
        
    except Exception as e:
        await interaction.followup.send(f'Error generating chart: {str(e)}')
        print(f"Error in financial_chart: {e}")
        traceback.print_exc()

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN')) 