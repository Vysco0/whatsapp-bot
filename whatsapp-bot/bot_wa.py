#!/usr/bin/env python3
"""
WHATSAPP MASS CHECKER BOT - NO DELAY, NO LIMITS
Optimized for 5k+ numbers checking
Deploy to Free Server (Oracle Cloud Forever Free)
"""

import asyncio
import logging
import re
import sqlite3
import pickle
import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Selenium - HEADLESS MODE
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ========== CONFIGURATION ==========
TOKEN_BOT = "8389315749:AAEBKEmCP90tPriK_pNG5yDzahXKtiJglgw"  # REPLACE WITH YOUR TOKEN
SESSION_FILE = "/tmp/wa_session.pkl"  # Server path
DATABASE_FILE = "/tmp/wa_mass_check.db"
MAX_WORKERS = 10  # Parallel checking
CHECK_TIMEOUT = 10  # Seconds per check

# Setup aggressive logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

# ========== WHATSAPP MASS CHECKER ==========
class WhatsAppMassChecker:
    def __init__(self):
        self.driver_pool = []
        self.is_connected = False
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.init_database()
        self.init_drivers()
    
    def init_database(self):
        """Initialize high-performance database"""
        self.conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        self.conn.execute('PRAGMA journal_mode = WAL')
        self.conn.execute('PRAGMA synchronous = NORMAL')
        self.conn.execute('PRAGMA cache_size = 10000')
        
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS mass_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                registered INTEGER DEFAULT 0,
                name TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                has_photo INTEGER DEFAULT 0,
                is_business INTEGER DEFAULT 0,
                business_tier TEXT DEFAULT 'none',
                check_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_phone (phone),
                INDEX idx_registered (registered)
            )
        ''')
        self.conn.commit()
    
    def init_drivers(self):
        """Initialize multiple Chrome drivers for parallel processing"""
        print("🚀 Initializing Chrome drivers for mass checking...")
        
        for i in range(MAX_WORKERS):
            try:
                options = Options()
                options.add_argument("--headless")  # NO GUI
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument(f"--user-data-dir=/tmp/chrome_profile_{i}")
                options.add_argument("--window-size=1920,1080")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                
                # Disable images for speed
                prefs = {"profile.managed_default_content_settings.images": 2}
                options.add_experimental_option("prefs", prefs)
                
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                
                # Load WhatsApp with existing session
                driver.get("https://web.whatsapp.com")
                time.sleep(3)
                
                # Try to load saved cookies
                if os.path.exists(SESSION_FILE):
                    with open(SESSION_FILE, "rb") as f:
                        cookies = pickle.load(f)
                    for cookie in cookies:
                        try:
                            driver.add_cookie(cookie)
                        except:
                            pass
                    driver.refresh()
                    time.sleep(2)
                
                self.driver_pool.append({
                    'driver': driver,
                    'busy': False,
                    'last_used': time.time()
                })
                
            except Exception as e:
                print(f"⚠️ Driver {i} init failed: {e}")
        
        print(f"✅ {len(self.driver_pool)} drivers ready")
    
    def get_available_driver(self):
        """Get an available driver from pool"""
        for driver_info in self.driver_pool:
            if not driver_info['busy']:
                driver_info['busy'] = True
                driver_info['last_used'] = time.time()
                return driver_info['driver']
        
        # If all busy, use the least recently used
        self.driver_pool.sort(key=lambda x: x['last_used'])
        driver_info = self.driver_pool[0]
        driver_info['busy'] = True
        driver_info['last_used'] = time.time()
        return driver_info['driver']
    
    def release_driver(self, driver):
        """Release driver back to pool"""
        for driver_info in self.driver_pool:
            if driver_info['driver'] == driver:
                driver_info['busy'] = False
                break
    
    def check_single_number_fast(self, phone):
        """Ultra-fast check for single number - NO DELAY"""
        driver = self.get_available_driver()
        
        try:
            # Format phone
            if phone.startswith('0'):
                phone = '62' + phone[1:]
            
            result = {
                'phone': phone,
                'registered': 0,
                'name': '',
                'bio': '',
                'has_photo': 0,
                'is_business': 0,
                'business_tier': 'none'
            }
            
            # Direct check without opening chat
            driver.get(f"https://web.whatsapp.com/send?phone={phone}&text=.")
            
            # Fast timeout check
            start_time = time.time()
            while time.time() - start_time < CHECK_TIMEOUT:
                page_source = driver.page_source.lower()
                
                # Check if invalid
                if any(text in page_source for text in [
                    'nomor telepon tidak valid',
                    'phone number shared via url is invalid',
                    'invalid phone number'
                ]):
                    break  # Not registered
                
                # Check if registered (has send button)
                if 'send' in page_source and 'keyboard' in page_source:
                    result['registered'] = 1
                    
                    # Try quick name extraction
                    try:
                        name_elem = driver.find_elements(By.CSS_SELECTOR, "header span[dir='auto']")
                        if name_elem:
                            result['name'] = name_elem[0].text[:50]
                    except:
                        pass
                    
                    # Quick business check
                    if 'business' in page_source or 'bisnis' in page_source:
                        result['is_business'] = 1
                        if 'verified' in page_source:
                            result['business_tier'] = 'exclusive'
                    
                    break
                
                time.sleep(0.5)  # Micro sleep
            
            # Save to database
            self.save_result_fast(result)
            
            return result
            
        except Exception as e:
            return {'phone': phone, 'error': str(e)[:100]}
        finally:
            self.release_driver(driver)
    
    def check_multiple_numbers(self, phones):
        """Mass check numbers in parallel"""
        print(f"🔍 Starting mass check for {len(phones)} numbers...")
        
        # Submit all checks to thread pool
        futures = {}
        for phone in phones:
            future = self.executor.submit(self.check_single_number_fast, phone)
            futures[future] = phone
        
        # Collect results as they complete
        results = []
        completed = 0
        start_time = time.time()
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=CHECK_TIMEOUT + 5)
                results.append(result)
                completed += 1
                
                # Progress update every 100 numbers
                if completed % 100 == 0:
                    elapsed = time.time() - start_time
                    speed = completed / elapsed if elapsed > 0 else 0
                    print(f"📊 Progress: {completed}/{len(phones)} "
                          f"({speed:.1f} checks/sec)")
                    
            except Exception as e:
                results.append({'phone': futures[future], 'error': str(e)})
        
        print(f"✅ Mass check completed in {time.time() - start_time:.1f} seconds")
        return results
    
    def save_result_fast(self, result):
        """Fast batch insert"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO mass_checks 
                (phone, registered, name, bio, has_photo, is_business, business_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                result['phone'],
                result.get('registered', 0),
                result.get('name', ''),
                result.get('bio', ''),
                result.get('has_photo', 0),
                result.get('is_business', 0),
                result.get('business_tier', 'none')
            ))
        except Exception as e:
            print(f"⚠️ DB save error: {e}")
    
    def generate_mass_report(self, results):
        """Generate statistics report for mass checking"""
        total = len(results)
        registered = sum(1 for r in results if r.get('registered') == 1)
        not_registered = total - registered
        
        business = sum(1 for r in results if r.get('is_business') == 1)
        exclusive = sum(1 for r in results if r.get('business_tier') == 'exclusive')
        
        # Batch stats from database
        self.cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(registered) as registered,
                SUM(is_business) as business,
                SUM(CASE WHEN business_tier='exclusive' THEN 1 ELSE 0 END) as exclusive
            FROM mass_checks 
            WHERE phone IN ({})
        '''.format(','.join(['?']*len(results[:100]))), 
        [r['phone'] for r in results[:100]])
        
        stats = self.cursor.fetchone()
        
        report = f"""🚀 MASS CHECK REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 QUICK STATISTICS:
├ Total Processed: {total:,}
├ Registered: {registered:,}
├ Not Registered: {not_registered:,}
├ Business Accounts: {business:,}
└ Exclusive Tier: {exclusive:,}

⚡ PERFORMANCE:
• Start Time: {datetime.fromtimestamp(time.time() - total*0.5).strftime('%H:%M:%S')}
• End Time: {datetime.now().strftime('%H:%M:%S')}
• Estimated Speed: {total/max(1, len(results)/10):.0f} numbers/minute

📈 SUCCESS RATE: {(registered/total*100 if total>0 else 0):.1f}%"""
        
        return report
    
    def export_to_csv(self, filename="mass_results.csv"):
        """Export all results to CSV"""
        self.cursor.execute('''
            SELECT phone, registered, name, 
                   is_business, business_tier, check_time
            FROM mass_checks 
            ORDER BY check_time DESC
        ''')
        
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Phone', 'Registered', 'Name', 
                           'Business', 'Tier', 'Check Time'])
            
            for row in self.cursor.fetchall():
                writer.writerow(row)
        
        return filename
    
    def close(self):
        """Cleanup"""
        self.executor.shutdown(wait=False)
        for driver_info in self.driver_pool:
            try:
                driver_info['driver'].quit()
            except:
                pass
        self.conn.close()

# ========== TELEGRAM BOT ==========
checker = WhatsAppMassChecker()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *WHATSAPP MASS CHECKER BOT*\n\n"
        "⚡ *Optimized for 5,000+ numbers*\n"
        "✅ No delays between checks\n"
        "✅ Parallel processing (10 threads)\n"
        "✅ Headless mode (no browser display)\n\n"
        "📋 *Usage:*\n"
        "• Send phone numbers (one per line)\n"
        "• Or upload .txt file with numbers\n"
        "• Example:\n"
        "081234567890\n"
        "081298765432\n\n"
        "⚡ *Commands:*\n"
        "/start - Start bot\n"
        "/stats - Show statistics\n"
        "/export - Export all results\n"
        "/speedtest - Test checking speed",
        parse_mode='Markdown'
    )

async def handle_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mass number checking"""
    user_input = update.message.text.strip()
    
    # Extract all phone numbers
    numbers = re.findall(r'[0-9]{10,13}', user_input)
    
    if not numbers:
        # Check for file upload
        if update.message.document:
            file = await update.message.document.get_file()
            temp_file = f"/tmp/{update.effective_user.id}.txt"
            await file.download_to_drive(temp_file)
            
            with open(temp_file, 'r') as f:
                content = f.read()
            numbers = re.findall(r'[0-9]{10,13}', content)
            os.remove(temp_file)
    
    if not numbers:
        await update.message.reply_text("❌ No valid phone numbers found")
        return
    
    # Limit to 5000 per request
    if len(numbers) > 5000:
        numbers = numbers[:5000]
        await update.message.reply_text(f"⚠️ Limited to first 5,000 numbers")
    
    status_msg = await update.message.reply_text(
        f"⚡ *STARTING MASS CHECK*\n\n"
        f"• Numbers: {len(numbers):,}\n"
        f"• Workers: {MAX_WORKERS}\n"
        f"• Estimated time: {len(numbers)/50:.0f} seconds\n\n"
        f"🔄 Processing...",
        parse_mode='Markdown'
    )
    
    try:
        # Start mass check
        results = checker.check_multiple_numbers(numbers)
        
        # Generate report
        report = checker.generate_mass_report(results)
        
        # Send report
        await update.message.reply_text(
            f"✅ *MASS CHECK COMPLETE*\n\n{report}",
            parse_mode='Markdown'
        )
        
        # Export and send file
        csv_file = checker.export_to_csv()
        with open(csv_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=f"mass_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                caption="📁 Complete results in CSV format"
            )
        
        os.remove(csv_file)
        await status_msg.delete()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show database statistics"""
    cursor = checker.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM mass_checks")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mass_checks WHERE registered = 1")
    registered = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mass_checks WHERE is_business = 1")
    business = cursor.fetchone()[0]
    
    cursor.execute("SELECT MAX(check_time) FROM mass_checks")
    last_check = cursor.fetchone()[0] or "Never"
    
    await update.message.reply_text(
        f"📊 *DATABASE STATISTICS*\n\n"
        f"• Total checks: {total:,}\n"
        f"• Registered: {registered:,}\n"
        f"• Business accounts: {business:,}\n"
        f"• Last check: {last_check[:19]}\n"
        f"• Success rate: {(registered/total*100 if total>0 else 0):.1f}%\n\n"
        f"⚡ *System Status*\n"
        f"• Active workers: {MAX_WORKERS}\n"
        f"• Drivers ready: {len(checker.driver_pool)}\n"
        f"• Headless mode: ✅",
        parse_mode='Markdown'
    )

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all data"""
    csv_file = checker.export_to_csv()
    
    with open(csv_file, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename="whatsapp_mass_check_export.csv",
            caption="📁 Complete database export"
        )
    
    os.remove(csv_file)

async def speed_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Speed test command"""
    test_numbers = [f"08123{i:07d}" for i in range(100)]  # 100 test numbers
    
    start_time = time.time()
    results = checker.check_multiple_numbers(test_numbers[:10])  # Test 10 numbers
    elapsed = time.time() - start_time
    
    speed = 10 / elapsed if elapsed > 0 else 0
    
    await update.message.reply_text(
        f"⚡ *SPEED TEST RESULTS*\n\n"
        f"• Numbers tested: 10\n"
        f"• Time taken: {elapsed:.2f} seconds\n"
        f"• Speed: {speed:.1f} numbers/second\n"
        f"• Estimated 5k numbers: {5000/speed/60:.1f} minutes\n\n"
        f"✅ System ready for mass checking!",
        parse_mode='Markdown'
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text(f"⚠️ Error: {str(context.error)[:100]}")

# ========== MAIN & DEPLOYMENT ==========
def deploy_to_server():
    """Auto-deployment script for Oracle Cloud Free Tier"""
    deploy_script = '''#!/bin/bash
# WhatsApp Mass Checker - Auto Deploy Script
# For Oracle Cloud Always Free Tier

echo "🚀 Deploying WhatsApp Mass Checker to Oracle Cloud..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# Install ChromeDriver
CHROME_VERSION=$(google-chrome --version | grep -o '[0-9.]\+' | head -1)
CHROME_MAJOR=${CHROME_VERSION%%.*}
wget -q "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR}" -O /tmp/chromedriver_version
CHROMEDRIVER_VERSION=$(cat /tmp/chromedriver_version)
wget -q "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip" -O /tmp/chromedriver.zip
unzip /tmp/chromedriver.zip -d /tmp/
sudo mv /tmp/chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver

# Install Python
sudo apt install -y python3-pip python3-venv git

# Create bot directory
mkdir -p ~/whatsapp-bot && cd ~/whatsapp-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install python-telegram-bot selenium webdriver-manager

# Download bot script
wget -O bot_mass_checker.py "YOUR_RAW_SCRIPT_URL_HERE"

# Create systemd service
sudo tee /etc/systemd/system/whatsapp-bot.service > /dev/null <<EOF
[Unit]
Description=WhatsApp Mass Checker Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/whatsapp-bot
Environment="PATH=/home/$USER/whatsapp-bot/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/$USER/whatsapp-bot/venv/bin/python3 bot_mass_checker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-bot
sudo systemctl start whatsapp-bot

echo "✅ Deployment complete!"
echo "📱 Bot is running 24/7 on Oracle Cloud"
echo "🔧 Check status: sudo systemctl status whatsapp-bot"
echo "📊 View logs: sudo journalctl -u whatsapp-bot -f"
'''
    
    with open("deploy_oracle.sh", "w") as f:
        f.write(deploy_script)
    
    print("📁 Deployment script created: deploy_oracle.sh")
    print("📋 How to deploy:")
    print("1. Get Oracle Cloud Always Free account")
    print("2. Create Ubuntu 22.04 VM (4 core, 24GB RAM FREE)")
    print("3. SSH to server")
    print("4. Upload this script")
    print("5. Run: bash deploy_oracle.sh")
    print("6. Edit bot_mass_checker.py with your bot token")
    print("7. Scan QR code when prompted")
    print("8. Bot runs 24/7 FOREVER FREE!")

def main():
    """Main function"""
    if TOKEN_BOT == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Replace TOKEN_BOT with your actual token!")
        print("\n📱 How to get token:")
        print("1. Open Telegram, search @BotFather")
        print("2. Send /newbot")
        print("3. Follow instructions")
        print("4. Copy token and paste in line 24")
        print("\n☁️ Want to deploy to free server?")
        deploy_choice = input("Create deployment script? (y/n): ")
        if deploy_choice.lower() == 'y':
            deploy_to_server()
        return
    
    # Create bot application
    app = Application.builder().token(TOKEN_BOT).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("speedtest", speed_test))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_numbers))
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_numbers))
    app.add_error_handler(error_handler)
    
    print("\n" + "="*60)
    print("🚀 WHATSAPP MASS CHECKER BOT - 5K+ NUMBERS")
    print("="*60)
    print(f"• Token: {TOKEN_BOT[:15]}...")
    print(f"• Max Workers: {MAX_WORKERS}")
    print(f"• Headless Mode: ✅")
    print(f"• No Delays: ✅")
    print("="*60)
    print("\n⚡ Bot is running!")
    print("📱 Send /start in Telegram to begin")
    print("💾 Results saved to: /tmp/wa_mass_check.db")
    print("\n☁️ Deploy to Oracle Cloud Free (24/7):")
    print("Run: python this_script.py and choose deploy option")
    
    # Run bot
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
        checker.close()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        checker.close()