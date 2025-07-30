import argparse
import logging
import json
from datetime import datetime
from data_manager import DataManager
from email_engine import EmailEngine
from template_manager import TemplateManager
import os
import time
import signal
import sys
from typing import Dict, Any
import sqlite3
import random
import csv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('campaign.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_config() -> Dict[str, Any]:
    """Load configuration from config.json."""
    try:
        config_path = 'config.json'
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")
            
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        # Validate required email settings
        if 'email' not in config:
            raise ValueError("Missing 'email' section in configuration")
            
        email_config = config['email']
        
        required_fields = ['smtp_server', 'smtp_port', 'use_tls', 'batch_delay', 'max_retries']
        missing_fields = [field for field in required_fields if field not in email_config]
        
        if missing_fields:
            raise ValueError(f"Missing required email configuration fields: {', '.join(missing_fields)}")
            
        return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        raise

def save_progress(last_processed_id: int):
    """Save the last processed company ID to a progress file."""
    try:
        with open('campaign_progress.json', 'w') as f:
            json.dump({'last_processed_id': last_processed_id}, f)
    except Exception as e:
        logger.error(f"Error saving progress: {str(e)}")

def load_progress() -> int:
    """Load the last processed company ID from the progress file."""
    try:
        if os.path.exists('campaign_progress.json'):
            with open('campaign_progress.json', 'r') as f:
                return json.load(f).get('last_processed_id', 0)
    except Exception as e:
        logger.error(f"Error loading progress: {str(e)}")
    return 0

def signal_handler(signum, frame):
    """Handle signals to gracefully stop the campaign."""
    logger.info("\nReceived signal to stop. Saving progress...")
    sys.exit(0)

def run_campaign(resume_path: str, batch_size: int = 50, daily_limit: int = 500, background: bool = False):
    """Run the email campaign with round-robin sender accounts, skipping exhausted accounts and resetting every 24 hours."""
    data_manager = None
    try:
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize managers
        data_manager = DataManager()
        config = load_config()
        template_manager = TemplateManager()
        
        # Load all sender accounts (now under 'email_accounts' key)
        accounts_path = os.path.join(os.path.dirname(__file__), 'email_accounts.json')
        with open(accounts_path, 'r') as f:
            accounts_json = json.load(f)
            sender_accounts = [acc for acc in accounts_json['email_accounts'] if acc.get('enabled', True)]

        # Track exhausted accounts and last reset time
        exhausted_accounts = set()
        exhausted_accounts_path = os.path.join(os.path.dirname(__file__), '../data/exhausted_accounts.json')
        # Load exhausted accounts from file if exists
        if os.path.exists(exhausted_accounts_path):
            try:
                with open(exhausted_accounts_path, 'r') as f:
                    exhausted_accounts = set(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load exhausted accounts: {e}")
        last_reset = time.time()
        RESET_INTERVAL = 24 * 60 * 60  # 24 hours in seconds

        # Verify resume exists
        if not os.path.exists(resume_path):
            raise FileNotFoundError(f"Resume not found at {resume_path}")
        
        # Load template
        template = template_manager.get_template('job_inquiry')
        # Add resume to template attachments
        template['attachments'] = [resume_path]
        
        # Get companies to process
        companies = data_manager.get_unsent_companies(limit=daily_limit)
        total_companies = len(companies)
        logger.info(f"Starting campaign for {total_companies} companies")

        # Check daily limit - only process up to the daily limit
        emails_sent_today = data_manager.get_emails_sent_today()
        logger.info(f"Emails sent today: {emails_sent_today}")
        logger.info(f"Daily limit: {daily_limit}")

        # Clear progress file if it's a new day (no emails sent today)
        if emails_sent_today == 0:
            try:
                if os.path.exists('campaign_progress.json'):
                    os.remove('campaign_progress.json')
                    logger.info("Cleared progress file for new day")
            except Exception as e:
                logger.warning(f"Could not clear progress file: {e}")

        if emails_sent_today >= daily_limit:
            logger.info(f"Daily limit of {daily_limit} emails already reached. No more emails will be sent today.")
            sys.exit(0)

        # Calculate how many emails we can still send today
        remaining_daily_limit = daily_limit - emails_sent_today
        logger.info(f"Remaining emails for today: {remaining_daily_limit}")

        # Limit companies to process based on remaining daily limit
        if len(companies) > remaining_daily_limit:
            companies = companies[:remaining_daily_limit]
            logger.info(f"Limited to {remaining_daily_limit} companies due to daily limit")

        total_companies = len(companies)
        logger.info(f"Will process {total_companies} companies")
        
        # Load progress
        last_processed_id = load_progress()
        if last_processed_id > 0:
            logger.info(f"Resuming from company ID {last_processed_id}")
            companies = [c for c in companies if c['id'] > last_processed_id]
            logger.info(f"Remaining companies to process: {len(companies)}")
        
        processed_count = 0
        send_log_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../data/send_log.csv'))
        if not os.path.exists(send_log_path):
            with open(send_log_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['sender_email', 'recipient_email', 'date_sent', 'status', 'company_name'])
        
        # Round-robin send logic
        num_accounts = len(sender_accounts)
        idx = 0
        for company in companies:
            # Reset exhausted accounts every 24 hours
            if time.time() - last_reset > RESET_INTERVAL:
                exhausted_accounts.clear()
                last_reset = time.time()
                # Clear the exhausted accounts file
                try:
                    with open(exhausted_accounts_path, 'w') as f:
                        json.dump([], f)
                except Exception as e:
                    logger.warning(f"Could not clear exhausted accounts file: {e}")

            # Find next available (not exhausted) account
            attempts = 0
            while attempts < num_accounts:
                account = sender_accounts[idx % num_accounts]
                if account['sender_email'] not in exhausted_accounts:
                    break
                idx += 1
                attempts += 1
            else:
                logger.error("All accounts are exhausted. Skipping this batch.")
                time.sleep(60)  # Wait a minute before retrying
                continue

            logger.info(f"Sending email to {company['company_name']} ({company['hr_email']}) from {account['sender_email']}")
            try:
                email_body = template_manager.format_template(
                    template,
                    company_name=company['company_name'],
                    hr_email=company['hr_email'],
                    hr_name="HR Manager",
                    position="Software Developer"
                )
                email = {
                    'to_email': company['hr_email'],
                    'subject': f"Application for Software Engineer | Developer at {company['company_name']}",
                    'content': email_body,
                    'company_id': company['id'],
                    'company_name': company['company_name'],
                    'hr_email': company['hr_email'],
                    'position': 'Software Engineer'
                }
                # Build config for this account
                account_config = config['email'].copy()
                account_config.update({
                    'sender_email': account['sender_email'],
                    'sender_password': account['sender_password'],
                    'smtp_server': account.get('smtp_server', account_config.get('smtp_server', 'smtp.gmail.com')),
                    'smtp_port': account.get('smtp_port', account_config.get('smtp_port', 587)),
                    'use_tls': account.get('use_tls', account_config.get('use_tls', True)),
                    'batch_delay': account.get('batch_delay', account_config.get('batch_delay', 20)),
                    'max_retries': account.get('max_retries', account_config.get('max_retries', 2)),
                })
                email_engine = EmailEngine(account_config)
                # Send single email
                result = email_engine.send_batch([email], template)[0]
                company_id = result['company_id']
                success = result['success']
                error = result.get('error')
                exhausted = result.get('exhausted', False)
                if exhausted:
                    exhausted_accounts.add(account['sender_email'])
                    # Persist exhausted accounts to file
                    try:
                        with open(exhausted_accounts_path, 'w') as f:
                            json.dump(list(exhausted_accounts), f)
                    except Exception as e:
                        logger.warning(f"Could not save exhausted accounts: {e}")
                    logger.warning(f"Account {account['sender_email']} marked as exhausted due to SMTP error. Skipping for 24 hours.")
                    idx += 1  # Move to next account for next email
                    continue  # Try next account for this company
                data_manager.mark_email_sent(
                    company_id,
                    status='sent' if success else 'failed',
                    error_message=None if success else error
                )
                save_progress(company_id)
                processed_count += 1
                logger.info(f"Progress: {processed_count}/{total_companies} companies processed")
                # Log to send_log.csv
                with open(send_log_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        account['sender_email'],
                        email['to_email'],
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'success' if success else 'failed',
                        email['company_name']
                    ])
                    f.flush()
                    os.fsync(f.fileno())
                # Optional: add a small delay between emails if needed
                time.sleep(account_config.get('batch_delay', 1))
                idx += 1  # Move to next account for next email
            except Exception as e:
                logger.error(f"Error sending email for company {company['company_name']}: {e}")
                data_manager.mark_email_sent(company['id'], status='failed', error_message=str(e))
                save_progress(company['id'])
                processed_count += 1
                idx += 1  # Move to next account for next email
        
        logger.info(f"Campaign completed. Sent {processed_count} emails.")

        # Verify database consistency
        logger.info("Verifying database consistency...")
        consistency_stats = data_manager.verify_database_consistency()
        if consistency_stats.get('companies_tracking_match') and consistency_stats.get('today_match'):
            logger.info("✅ Database consistency verified - all updates successful")
        else:
            logger.warning("⚠️ Database consistency issues detected:")
            logger.warning(f"Companies vs Tracking records: {consistency_stats.get('companies_tracking_match')}")
            logger.warning(f"Today's records match: {consistency_stats.get('today_match')}")

        # Save final progress and exit
        if processed_count > 0:
            save_progress(companies[-1]['id'] if companies else last_processed_id)
            # Final verification of database updates
            logger.info("Verifying database updates...")
            for company in companies:
                if company['id'] > last_processed_id:
                    # Verify in companies.db
                    with sqlite3.connect('data/companies.db') as conn:
                        cursor = conn.execute("""
                            SELECT status, sent_timestamp 
                            FROM companies 
                            WHERE id = ?
                        """, (company['id'],))
                        result = cursor.fetchone()
                        if result:
                            logger.info(f"Companies DB - ID {company['id']}: status={result[0]}, sent={result[1]}")
                    # Verify in email_tracking.db
                    with sqlite3.connect('data/email_tracking.db') as conn:
                        cursor = conn.execute("""
                            SELECT status, sent_date 
                            FROM sent_emails 
                            WHERE company_id = ?
                        """, (company['id'],))
                        result = cursor.fetchone()
                        if result:
                            logger.info(f"Tracking DB - ID {company['id']}: status={result[0]}, sent={result[1]}")
        logger.info("Campaign completed successfully. Exiting...")
        if data_manager:
            data_manager.close()
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("\nCampaign interrupted by user. Cleaning up...")
        if data_manager:
            data_manager.close()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error running campaign: {str(e)}")
        if data_manager:
            data_manager.close()
        sys.exit(1)

if __name__ == '__main__':
    import traceback
    try:
        parser = argparse.ArgumentParser(description='Run email campaign')
        parser.add_argument('--resume', required=True, help='Path to resume file')
        parser.add_argument('--batch-size', type=int, default=50, help='Number of emails to send in each batch')
        parser.add_argument('--daily-limit', type=int, default=500, help='Maximum number of emails to send per day')
        parser.add_argument('--background', action='store_true', help='Run in background mode')
        args = parser.parse_args()
        if args.background:
            # Detach from terminal
            pid = os.fork()
            if pid > 0:
                print(f"Campaign started in background with PID {pid}")
                sys.exit(0)
        run_campaign(args.resume, args.batch_size, args.daily_limit, args.background)
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        logger.error(traceback.format_exc())
        print(f"Fatal error in main: {e}")
        print(traceback.format_exc())
        sys.exit(2) 