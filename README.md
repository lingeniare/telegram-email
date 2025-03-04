# Email to Telegram Bot

## Summary
Forwards the email to your chat or telegram group.
Benefits:
1. Autorun
2. Blacklist
3. Clean-text
4. Multi-accounts

---
## Getting an API Token in Telegram via @BotFather

To create a new bot and obtain an API token, follow these steps:

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather).  
2. Send the command:  
   ```
   /newbot
   ```
3. Enter a name for your bot.  
4. Choose a unique username ending with `_bot` (e.g., `myawesomebot_bot`).  
5. Copy the provided API token.  

## Bot Permissions  

The bot can send messages to you in private chats. However, to send messages in a group or chat, you must add it as an admin.  

## Getting a User or Group ID  

To retrieve your personal ID or a group's ID, use [@getmyid_bot](https://t.me/getmyid_bot).  
```  
## Installation on Windows

### Install Python:
- Download Python from the [official website](https://www.python.org/downloads/)
- During installation, check the box "Add Python to PATH"
- Complete the installation

### Install Dependencies:
- Open Command Prompt (cmd) as Administrator
- Run the command:
  ```sh
  pip install pyTelegramBotAPI python-dotenv
  pip install pyTelegramBotAPI schedule
  ```

### Create Project Folder:
- Create a folder for the bot, e.g., `C:\email-bot`
- Save the bot script in `email_bot.py` inside this folder

### Configure Settings:
- Run the script once to create the configuration template:
  ```sh
  python C:\email-bot\email_bot.py
  ```
- Open the generated `config.json` file and enter your details (email, Telegram bot token, chat ID)
- Save the changes

### Set Up Auto-Start:
- Create a file `start_bot.bat` inside the bot folder with the following content:
  ```sh
  @echo off
  cd C:\email-bot
  python email_bot.py
  ```
- Press Win+R, type `shell:startup`, and hit Enter
- Copy the shortcut of `start_bot.bat` to the startup folder

---

## Installation on Ubuntu

### Install Python and Required Packages:
```sh
sudo apt update
sudo apt install python3 python3-pip git
```

### Create Project Folder:
```sh
mkdir ~/email-bot
cd ~/email-bot
```

### Configure Settings:
```sh
python3 ~/email-bot/email_bot.py
```
- Stop the script after configuration creation (Ctrl+C)
- Open the generated `config.json` file:
  ```sh
  nano ~/email-bot/config.json
  ```
- Enter your details (email, Telegram bot token, chat ID)
- Save the changes (Ctrl+O, then Enter, then Ctrl+X)

### Set Up Virtual Environment:
```sh
python3 -m venv myenv
source myenv/bin/activate
```

### Install Dependencies:
```sh
pip3 install pyTelegramBotAPI python-dotenv
pip3 install pyTelegramBotAPI schedule
```

### First Run Configuration:
- The `config.json` file will be created automatically when running `email_bot.py` for the first time.
- Steps:
  1. Save the script as `email_bot.py`
  2. Run:
     - On Windows: `python email_bot.py`
     - On Ubuntu: `python3 email_bot.py`
  3. The script will detect the missing config file and generate `config.json`
  4. Stop the script (Ctrl+C), edit `config.json` with your details, and restart the script

Without editing the configuration, the script won't function properly since it contains placeholder values (`your_email@example.com`, `your_password`, `your_telegram_bot_token`).

---

## Set Up Auto-Start with systemd on Ubuntu

### Create a systemd Service File:
```sh
sudo nano /etc/systemd/system/email-bot.service
```

### Add the following content (replace `your_username` with your actual username):
```ini
[Unit]
Description=Email to Telegram Bot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/your_username/email-bot/email_bot.py
WorkingDirectory=/home/your_username/email-bot
Restart=always
User=your_username

[Install]
WantedBy=multi-user.target
```

### Enable and Start the Service:
```sh
sudo systemctl daemon-reload
sudo systemctl enable email-bot.service
sudo systemctl start email-bot.service
```

### Check Service Status:
```sh
sudo systemctl status email-bot.service
```

The bot should now run automatically and restart on system boot.
