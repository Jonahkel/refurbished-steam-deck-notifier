# refurbished steam deck notifier - notifies when refurbished steam deck is in stock
#  Copyright (C) <2025>  <Oliver Blass>
# 
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

from time import gmtime, strftime
import requests
from discord_webhook import DiscordWebhook
import os
import csv
from datetime import datetime
import argparse
import json
from dotenv import load_dotenv

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


load_dotenv()

DEFAULT_WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
# Default values
DEFAULT_COUNTRY_CODE = 'US'
DEFAULT_ROLE_MAPPING = "roles.json"
DEFAULT_SENDER_EMAIL = os.getenv("SENDER_EMAIL", '')
DEFAULT_RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", '')


class SteamDeckModel:
    def __init__(self, version: str, package_id: str, is_oled: bool, is_new: bool = False):
        self.version = version
        self.package_id = package_id
        self.is_oled = is_oled
        self.is_new = is_new

def send_email_notification(model_name, package_id, high_pending, receiver_email):
    """Sends an email notification."""
    if not DEFAULT_SENDER_EMAIL or not receiver_email: return

    if high_pending:
        subject = f"🚨 STEAM DECK RESTOCK: {model_name} in stock!"
        body = (
            f"The Certified Refurbished {model_name} (Package ID: {package_id}) "
            f"is currently IN STOCK!\n\n"
            f"Buy it immediately before it sells out here:\n"
            f"https://store.steampowered.com/sale/steamdeckrefurbished"
        )
    else:
        subject = f"🚨🚨🚨 STEAM DECK RESTOCK: No high pending orders for {model_name}!"
        body = (
            f"The Certified Refurbished {model_name} (Package ID: {package_id}) "
            f"is currently IN STOCK!\n\n"
            f"Plus, there aren't high pending orders!\n"
            f"Buy it immediately before it sells out here:\n"
            f"https://store.steampowered.com/sale/steamdeckrefurbished"
        )

    msg = MIMEMultipart()
    msg['From'] = DEFAULT_SENDER_EMAIL
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to Alwaysdata's local SMTP server on port 25 (no auth required)
        with smtplib.SMTP('localhost', 25) as server:
            server.sendmail(DEFAULT_SENDER_EMAIL, receiver_email, msg.as_string())
        print(f"[{datetime.now()}] Email notification sent to {receiver_email}!")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send email: {e}")

def get_daily_csv_path(csv_dir: str, country_code: str) -> str:
    """Generate the CSV file path for today's date and country"""
    if not csv_dir:
        return ""
    
    # Create directory if it doesn't exist
    os.makedirs(csv_dir, exist_ok=True)
    
    # Generate filename with today's date and country code
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{country_code}_{today}.csv"
    return os.path.join(csv_dir, filename)

def initialize_logs(csv_dir: str, country_code: str):
    """Initialize CSV log file if it doesn't exist"""
    if not csv_dir:
        return
        
    log_file = get_daily_csv_path(csv_dir, country_code)
    if not os.path.exists(log_file):
        with open(log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['unix_timestamp', 'storage_gb', 
                        'display_type', 'package_id', 'available'])

def log_availability_data(version, package_id, available, is_oled, csv_dir: str, country_code: str):
    """Log availability data in CSV format"""
    if not csv_dir:
        return
        
    log_file = get_daily_csv_path(csv_dir, country_code)
    timestamp = datetime.now()
    unix_timestamp = int(timestamp.timestamp())
    display_type = "OLED" if is_oled else "LCD"
    
    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([unix_timestamp, version, display_type, package_id, available])

def superduperscraper(model: SteamDeckModel, csv_dir: str, country_code: str, webhook_url: str, role_ids: dict, receiver_email: str):
    # Build Steam API URL with country code
    url = f'https://api.steampowered.com/IPhysicalGoodsService/CheckInventoryAvailableByPackage/v1?origin=https:%2F%2Fstore.steampowered.com&country_code={country_code}&packageid='
    
    # Create Discord webhook
    webhook = DiscordWebhook(url=webhook_url, content="error")
    
    roleIdWithCountry = role_ids.get(model.package_id, "") if role_ids else ""
    
    old_state = None
    state_dir = "logs"
    os.makedirs(state_dir, exist_ok=True)
    state_file = os.path.join(state_dir, f"{model.package_id}_{country_code}.json")
    # Get previous state from JSON file
    if os.path.isfile(state_file):
        with open(state_file, "r", encoding="utf-8") as file_read:
            try:
                old_state = json.load(file_read)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse existing state file {state_file}; ignoring previous state")

    print(f"====== {model.version}GB {'OLED' if model.is_oled else 'LCD'} =======")
    print("Previous value: " + (json.dumps(old_state) if old_state is not None else ""))

    try:
        # Make request to Steam API
        response = requests.get(url+model.package_id, timeout=10)
        response.raise_for_status()
        
        # Get availability status
        response_data = response.json()["response"]
        availability = bool(response_data["inventory_available"])
        high_pending = bool(response_data["high_pending_orders"])
        current_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        
        print(f"{current_time} >> Result: {availability}")
        print(f"High pending orders: {high_pending}\n")
        
        current_state = {"available": availability, "high_pending": high_pending}

        # Save new availability to file
        with open(state_file, "w", encoding="utf-8") as file:
            json.dump(current_state, file)
        
        # Check if status changed
        status_changed = old_state != current_state
        
        # Log data
        log_availability_data(model.version, model.package_id, availability, model.is_oled, csv_dir, country_code)
        
        # Send Discord notification only on status change
        if status_changed:
            display_type = "OLED" if model.is_oled else "LCD"
            condition_type = "new" if model.is_new else "refurbished"
            role_ping = f" <@&{roleIdWithCountry}>" if roleIdWithCountry else ""
            if availability:
                # Include role ping only if role ID exists
                webhook.content = f"{condition_type} {model.version}GB {display_type} steam deck available{role_ping}"
                if not high_pending:
                    webhook.content += f"\nNOT HIGH PENDING ORDERS!"
            else:
                webhook.content = f"{condition_type} {model.version}GB {display_type} steam deck not available{role_ping}"
            webhook.execute()
            send_email_notification(model.version, model.package_id, high_pending, receiver_email)
            
    except requests.RequestException as e:
        print(f"Error fetching data for {model.version}GB: {e}")
        log_availability_data(model.version, model.package_id, False, model.is_oled, csv_dir, country_code)
    except Exception as e:
        print(f"Unexpected error for {model.version}GB: {e}")

def load_role_mapping(role_file: str) -> dict:
    """Load role mapping from JSON file"""
    if not role_file or not os.path.exists(role_file):
        return {}
    
    try:
        with open(role_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load role mapping from {role_file}: {e}")
        return {}

def main():
    """Main function to check all Steam Deck models"""

    parser = argparse.ArgumentParser(description='Check Steam Deck availability and optionally log to CSV')
    parser.add_argument('--include-new-models', action='store_true', help='Include request for new steam decks (not just refurbs)')
    parser.add_argument('--csv-dir', help='Directory path for daily CSV log files')
    parser.add_argument('--webhook-url', default=DEFAULT_WEBHOOK_URL,
                       help='Discord webhook URL for notifications (default: WEBHOOK_URL from .env)')
    parser.add_argument('--webhook-url-new', default=DEFAULT_WEBHOOK_URL,
                       help='Discord webhook URL for new-model notifications (default: WEBHOOK_URL_NEW from .env, or WEBHOOK_URL if unset)')
    parser.add_argument('--receiver-email', default=DEFAULT_RECEIVER_EMAIL,
                       help='Email address to send notifications to (default: RECEIVER_EMAIL from .env)')
    parser.add_argument('--country-code', default=DEFAULT_COUNTRY_CODE, 
                       help=f'Country code for Steam API (default: {DEFAULT_COUNTRY_CODE})')
    parser.add_argument('--role-mapping', default=DEFAULT_ROLE_MAPPING,
                       help=f'JSON file containing package_id to role_id mapping (default: {DEFAULT_ROLE_MAPPING})')
    parser.add_argument('--csv-log', help='Deprecated: This option is no longer supported (last supported version v2.0.0).')
    
    args = parser.parse_args()

    if args.csv_log:
        print("w: Deprecated: This option is no longer supported (last supported version v2.0.0).")

    receiver_email = args.receiver_email

    if not args.webhook_url:
        raise SystemExit('Missing WEBHOOK_URL in .env or --webhook-url')
    
    csv_dir = args.csv_dir if args.csv_dir else ""
    initialize_logs(csv_dir, args.country_code)
    
    # Load role mapping
    role_ids = load_role_mapping(args.role_mapping)
    
    if csv_dir:
        today_file = get_daily_csv_path(csv_dir, args.country_code)
        print(f"Logging enabled to: {today_file}")
    else:
        print("Logging disabled")
    
    print(f"Country code: {args.country_code}")
    print("Webhook URL loaded from .env")
    
    # Steam Deck models
    refurbModels = [
        #REFURBISHED
        SteamDeckModel("64", "903905", False),    # 64gb lcd
        SteamDeckModel("256", "903906", False),   # 256gb lcd  
        SteamDeckModel("512", "903907", False),   # 512gb lcd
        SteamDeckModel("512", "1202542", True),   # 512gb oled
        SteamDeckModel("1024", "1202547", True),  # 1tb oled
    ]   

    newModels = [
        #NEW
        SteamDeckModel("512", "946113", True, is_new=True),    # 512gb oled
        SteamDeckModel("1024", "946114", True, is_new=True),   # 1tb oled
        # Optional: Phasing out LCD models
        SteamDeckModel("256", "595604", False, is_new=True),   # 256gb lcd

        #64gb and 512gb lcd aren't being sold as new anymore
        #SteamDeckModel("64", "595603", False, is_new=True),    # 64gb lcd
        #SteamDeckModel("512", "595605", False, is_new=True),   # 512gb lcd
    ]

    if args.include_new_models:
        models = refurbModels + newModels
    else:
        models = refurbModels

    if role_ids:
        print(f"Role mapping loaded: {len(role_ids)} entries")
        if not len(role_ids) == len(models):
            print("Warning..............Role mapping doesn't match models. Pinging roles won't work as expected.")
    else:
        print("No role mapping - notifications will not ping roles")
    
    for model in models:
        superduperscraper(model, csv_dir, 
                         args.country_code, args.webhook_url if not model.is_new or args.webhook_url_new == "" else args.webhook_url_new, role_ids, receiver_email)

if __name__ == "__main__":
    main()