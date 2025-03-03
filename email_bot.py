import imaplib
import email
import os
import time
import json
import telebot
import logging
import signal
import sys
import re
from email.header import decode_header
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='email_bot.log'
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG_FILE = 'config.json'

# Загрузка конфигурации
def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "email_accounts": [
                {
                    "name": "Account 1",
                    "server": "imap.example.com",
                    "port": 993,
                    "username": "your_email1@example.com",
                    "password": "your_password1",
                    "folder": "INBOX",
                    "last_checked_uid": 0
                },
                # Добавьте здесь другие аккаунты аналогично
            ],
            "telegram": {
                "bot_token": "your_telegram_bot_token",
                "chat_id": "your_chat_id"
            },
            "settings": {
                "check_interval": 60,  # в секундах
            },
            "blacklist": {
                "senders": ["spam@example.com", "newsletter@example.com"],
                "subjects": ["Специальное предложение", "Скидки"],
                "contains": ["Unsubscribe", "отписаться"],
                "domains": ["spam-domain.com"]
            }
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)
        logger.info(f"Создан новый файл конфигурации {CONFIG_FILE}")
        return default_config
    
    with open(CONFIG_FILE, 'r') as f:
        logger.info(f"Загружена конфигурация из {CONFIG_FILE}")
        return json.load(f)

# Сохранение последнего проверенного UID для конкретного аккаунта
def save_last_uid(account_index, uid):
    config = load_config()
    config['email_accounts'][account_index]['last_checked_uid'] = uid
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    logger.info(f"Сохранен последний проверенный UID: {uid} для аккаунта {config['email_accounts'][account_index]['name']}")

# Декодирование заголовков письма
def decode_email_header(header):
    if not header:
        return ""
    
    decoded_header = decode_header(header)
    header_str = ""
    for value, encoding in decoded_header:
        if isinstance(value, bytes):
            if encoding:
                try:
                    header_str += value.decode(encoding)
                except UnicodeDecodeError:
                    header_str += value.decode('latin-1')
            else:
                try:
                    header_str += value.decode('utf-8')
                except UnicodeDecodeError:
                    header_str += value.decode('latin-1')
        else:
            header_str += str(value)
    return header_str

# Получение текста письма
def get_email_body(msg):
    text_content = ""
    html_content = ""
    
    # Проверяем multipart сообщения
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Пропускаем вложения
            if "attachment" in content_disposition:
                continue
                
            # Получаем текстовую часть
            if content_type == "text/plain":
                try:
                    text_content = part.get_payload(decode=True).decode()
                except UnicodeDecodeError:
                    try:
                        text_content = part.get_payload(decode=True).decode('latin-1')
                    except:
                        text_content = "Ошибка декодирования текста"
            
            # Или HTML если текстовой нет
            elif content_type == "text/html" and not text_content:
                try:
                    html_content = part.get_payload(decode=True).decode()
                except UnicodeDecodeError:
                    try:
                        html_content = part.get_payload(decode=True).decode('latin-1')
                    except:
                        html_content = "Ошибка декодирования HTML"
    else:
        # Если сообщение не мультичастное
        content_type = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if not payload:
                return "Пустое сообщение"
                
            if content_type == "text/plain":
                text_content = payload.decode('utf-8', errors='replace')
            elif content_type == "text/html":
                html_content = payload.decode('utf-8', errors='replace')
        except:
            try:
                payload = msg.get_payload(decode=True)
                decoded = payload.decode('latin-1')
                if content_type == "text/plain":
                    text_content = decoded
                else:
                    html_content = decoded
            except:
                return "Не удалось декодировать сообщение"
    
    # Приоритет для текстового содержимого
    if text_content:
        return text_content
    
    # Если есть только HTML, можно добавить простейшую очистку HTML-тегов
    if html_content:
        html_content = re.sub(r'<[^>]+>', ' ', html_content)
        html_content = re.sub(r'\s+', ' ', html_content).strip()
        return html_content
    
    return "Не удалось получить текст письма"

# Проверка письма на наличие в черном списке
def is_blacklisted(from_addr, subject, body, blacklist):
    # Проверка отправителя
    for sender in blacklist.get('senders', []):
        if sender.lower() in from_addr.lower():
            logger.info(f"Письмо от {from_addr} в черном списке отправителей")
            return True
    
    # Проверка домена отправителя
    for domain in blacklist.get('domains', []):
        if '@' in from_addr and domain.lower() in from_addr.lower().split('@')[1]:
            logger.info(f"Домен {domain} в черном списке доменов")
            return True
    
    # Проверка темы
    for subj_pattern in blacklist.get('subjects', []):
        if subj_pattern.lower() in subject.lower():
            logger.info(f"Тема '{subject}' содержит паттерн из черного списка: {subj_pattern}")
            return True
    
    # Проверка содержимого
    for content_pattern in blacklist.get('contains', []):
        if content_pattern.lower() in body.lower():
            logger.info(f"Текст письма содержит паттерн из черного списка: {content_pattern}")
            return True
    
    return False

# Проверка наличия новых писем для конкретного аккаунта
def check_account_emails(account, account_index, bot, chat_id, blacklist):
    mail_server = account['server']
    mail_port = account['port']
    username = account['username']
    password = account['password']
    mail_folder = account['folder']
    last_uid = account['last_checked_uid']
    account_name = account['name']
    
    try:
        # Подключаемся к серверу
        mail = imaplib.IMAP4_SSL(mail_server, mail_port)
        mail.login(username, password)
        mail.select(mail_folder)
        
        # Получаем все UID писем
        result, data = mail.uid('search', None, "ALL")
        if not data or not data[0]:
            logger.info(f"Нет писем в почтовом ящике {account_name}")
            mail.logout()
            return
            
        email_uids = data[0].split()
        
        if not email_uids:
            logger.info(f"Нет писем в почтовом ящике {account_name}")
            mail.logout()
            return
        
        # Находим новые письма (UID больше последнего сохраненного)
        new_emails = [uid for uid in email_uids if int(uid) > last_uid]
        
        if not new_emails:
            logger.info(f"Нет новых писем в {account_name}")
            mail.logout()
            return
        
        logger.info(f"Найдено {len(new_emails)} новых писем в {account_name}")
        
        # Обрабатываем новые письма в обратном порядке (от старых к новым)
        for uid in sorted(new_emails):
            try:
                result, data = mail.uid('fetch', uid, '(RFC822)')
                if not data or not data[0]:
                    continue
                    
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Получаем данные письма
                from_addr = decode_email_header(msg.get('From', 'Unknown'))
                subject = decode_email_header(msg.get('Subject', 'No Subject'))
                date_str = msg.get('Date', datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z"))
                
                # Получаем текст письма
                body = get_email_body(msg)
                
                # Проверяем черный список
                if is_blacklisted(from_addr, subject, body, blacklist):
                    logger.info(f"Письмо от {from_addr} с темой '{subject}' пропущено (в черном списке)")
                    save_last_uid(account_index, int(uid))
                    continue
                
                # Формируем сообщение для отправки
                message = f"📧 *Новое письмо* ({account_name})\n\n" \
                          f"*От:* {from_addr}\n" \
                          f"*Тема:* {subject}\n" \
                          f"*Дата:* {date_str}\n\n"
                
                # Отправляем заголовок в Telegram
                bot.send_message(chat_id, message, parse_mode='Markdown')
                
                # Отправляем текст письма отдельным сообщением с форматированием кода
                if body:
                    # Ограничиваем длину текста
                    body_text = body[:4000] + ('...' if len(body) > 4000 else '')
                    # Отправляем как блок кода для сохранения форматирования
                    bot.send_message(chat_id, f"```\n{body_text}\n```", parse_mode='Markdown')
                
                logger.info(f"Письмо с UID {uid} от {account_name} отправлено в Telegram")
                
                # Обновляем последний проверенный UID
                save_last_uid(account_index, int(uid))
                
            except Exception as e:
                logger.error(f"Ошибка при обработке письма с UID {uid} из {account_name}: {str(e)}")
        
        mail.logout()
        
    except Exception as e:
        logger.error(f"Ошибка при проверке почты {account_name}: {str(e)}")

# Проверка наличия новых писем для всех аккаунтов
def check_emails():
    config = load_config()
    accounts = config['email_accounts']
    
    # Настройки Telegram
    bot_token = config['telegram']['bot_token']
    chat_id = config['telegram']['chat_id']
    
    # Получаем черный список
    blacklist = config.get('blacklist', {})
    
    # Создаем бота
    bot = telebot.TeleBot(bot_token)
    
    # Проверяем каждый аккаунт
    for i, account in enumerate(accounts):
        check_account_emails(account, i, bot, chat_id, blacklist)

# Обработка сигналов для корректного завершения
def signal_handler(sig, frame):
    logger.info("Получен сигнал завершения. Закрываем бота...")
    sys.exit(0)

# Основной цикл
def main():
    config = load_config()
    check_interval = config['settings']['check_interval']
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Бот для пересылки писем в Telegram запущен")
    
    while True:
        try:
            check_emails()
            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {str(e)}")
            time.sleep(check_interval)

if __name__ == "__main__":
    main()