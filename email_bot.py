import imaplib
import email
import os
import time
import json
import telebot
import logging
import signal
import sys
import socket
from email.header import decode_header
from datetime import datetime
import functools
import argparse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_bot.log'),
        logging.StreamHandler()  # Добавляем вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
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


# Загрузка конфигурации
def load_config(config_file: str) -> dict:
    """Loads the configuration from the given JSON file.

    Args:
        config_file: The path to the configuration file.

    Returns:
        A dictionary containing the configuration.
    """
    try:
        with open(config_file, 'r') as f:
            logger.info(f"Загружена конфигурация из {config_file}")
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Файл конфигурации {config_file} не найден. Создаем файл с конфигурацией по умолчанию.")
        save_config(DEFAULT_CONFIG, config_file)
        return DEFAULT_CONFIG
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка при чтении файла конфигурации {config_file}: {e}. Используется конфигурация по умолчанию.")
        return DEFAULT_CONFIG


def save_config(config: dict, config_file: str) -> None:
    """Saves the configuration to the given JSON file."""
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"Конфигурация сохранена в {config_file}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении конфигурации в {config_file}: {e}")


# Сохранение последнего проверенного UID для конкретного аккаунта
def save_last_uid(config: dict, account_index: int, uid: int, config_file: str) -> None:
    """Saves the last checked UID for a specific account.

    Args:
        config: The configuration dictionary.
        account_index: The index of the account.
        uid: The last checked UID.
    """
    config['email_accounts'][account_index]['last_checked_uid'] = uid
    save_config(config, config_file)
    logger.info(f"Сохранен последний проверенный UID: {uid} для аккаунта {config['email_accounts'][account_index]['name']}")


# Декодирование заголовков письма
def decode_email_header(header: str) -> str:
    """Decodes an email header.

    Args:
        header: The email header to decode.

    Returns:
        The decoded header as a string.
    """
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
                    logger.warning(f"UnicodeDecodeError при декодировании заголовка с кодировкой {encoding}.  Используется 'latin-1'")
                    header_str += value.decode('latin-1', errors='ignore')  # 'ignore' skips problematic characters
            else:
                try:
                    header_str += value.decode('utf-8')
                except UnicodeDecodeError:
                    logger.warning("UnicodeDecodeError при декодировании заголовка без указанной кодировки. Используется 'latin-1'")
                    header_str += value.decode('latin-1', errors='ignore')
        else:
            header_str += str(value)
    return header_str


# Проверка письма на наличие в черном списке
def is_blacklisted(from_addr: str, subject: str, blacklist: dict) -> bool:
    """Checks if an email is blacklisted.

    Args:
        from_addr: The sender's email address.
        subject: The email subject.
        blacklist: The blacklist configuration.

    Returns:
        True if the email is blacklisted, False otherwise.
    """
    from_addr_lower = from_addr.lower()
    subject_lower = subject.lower()

    if any(sender.lower() in from_addr_lower for sender in blacklist.get('senders', [])):
        logger.info(f"Письмо от {from_addr} в черном списке отправителей")
        return True

    if any(domain.lower() in from_addr_lower.split('@')[1] for domain in blacklist.get('domains', []) if '@' in from_addr):
        logger.info(f"Домен {domain} в черном списке доменов")
        return True

    if any(subj_pattern.lower() in subject_lower for subj_pattern in blacklist.get('subjects', [])):
        logger.info(f"Тема '{subject}' содержит паттерн из черного списка: {subj_pattern}")
        return True

    return False


def send_telegram_notification(bot: telebot.TeleBot, chat_id: str, message: str, is_error: bool = False) -> None:
    """Sends a notification to Telegram.
    
    Args:
        bot: The Telegram bot instance
        chat_id: The chat ID to send the message to
        message: The message to send
        is_error: Whether this is an error message
    """
    try:
        prefix = "⚠️ ОШИБКА: " if is_error else "ℹ️ "
        bot.send_message(chat_id, f"{prefix}{message}", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


# Проверка наличия новых писем для конкретного аккаунта
def check_account_emails(config: dict, account: dict, account_index: int, bot: telebot.TeleBot, chat_id: str, blacklist: dict, config_file: str) -> None:
    """Checks for new emails in a specific account."""
    mail_server = account['server']
    mail_port = account['port']
    username = account['username']
    password = account['password']
    mail_folder = account['folder']
    last_uid = account['last_checked_uid']
    account_name = account['name']

    try:
        with imaplib.IMAP4_SSL(mail_server, mail_port) as mail:
            try:
                mail.login(username, password)
                mail.select(mail_folder)

                result, data = mail.uid('search', None, "ALL")
                if not data or not data[0]:
                    logger.info(f"Нет писем в почтовом ящике {account_name}")
                    return

                email_uids = data[0].split()

                if not email_uids:
                    logger.info(f"Нет писем в почтовом ящике {account_name}")
                    return

                new_emails = [uid for uid in email_uids if int(uid) > last_uid]

                if not new_emails:
                    logger.info(f"Нет новых писем в {account_name}")
                    return

                logger.info(f"Найдено {len(new_emails)} новых писем в {account_name}")
                send_telegram_notification(bot, chat_id, f"Найдено {len(new_emails)} новых писем в {account_name}")

                # Собираем все новые письма с их датами
                emails_to_process = []
                for uid in new_emails:
                    try:
                        result, data = mail.uid('fetch', uid, '(RFC822)')
                        if not data or not data[0]:
                            continue

                        raw_email = data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        date_str = msg.get('Date', '')
                        try:
                            date = email.utils.parsedate_to_datetime(date_str)
                        except:
                            date = datetime.now()
                        
                        emails_to_process.append((uid, msg, date))
                    except Exception as e:
                        error_msg = f"Ошибка при получении письма с UID {uid} из {account_name}: {e}"
                        logger.error(error_msg)
                        send_telegram_notification(bot, chat_id, error_msg, is_error=True)

                # Сортируем письма по дате (от старых к новым)
                emails_to_process.sort(key=lambda x: x[2])

                # Обрабатываем отсортированные письма
                for uid, msg, date in emails_to_process:
                    try:
                        from_addr = decode_email_header(msg.get('From', 'Unknown'))
                        subject = decode_email_header(msg.get('Subject', 'No Subject'))
                        date_str = msg.get('Date', date.strftime("%a, %d %b %Y %H:%M:%S %z"))

                        if is_blacklisted(from_addr, subject, blacklist):
                            logger.info(f"Письмо от {from_addr} с темой '{subject}' пропущено (в черном списке)")
                            save_last_uid(config, account_index, int(uid), config_file)
                            continue

                        message = f"📧 *Новое письмо* ({account_name})\n\n" \
                                f"*От:* {from_addr}\n" \
                                f"*Тема:* {subject}\n" \
                                f"*Дата:* {date_str}\n"

                        bot.send_message(chat_id, message, parse_mode='Markdown')
                        logger.info(f"Письмо с UID {uid} от {account_name} отправлено в Telegram")
                        save_last_uid(config, account_index, int(uid), config_file)

                    except Exception as e:
                        error_msg = f"Ошибка при обработке письма с UID {uid} из {account_name}: {e}"
                        logger.error(error_msg)
                        send_telegram_notification(bot, chat_id, error_msg, is_error=True)

            except imaplib.IMAP4.error as e:
                error_msg = f"Ошибка при логине или выборе папки для {account_name}: {e}"
                logger.error(error_msg)
                send_telegram_notification(bot, chat_id, error_msg, is_error=True)
            except Exception as e:
                error_msg = f"Произошла ошибка в процессе работы с почтой {account_name}: {e}"
                logger.error(error_msg)
                send_telegram_notification(bot, chat_id, error_msg, is_error=True)

    except socket.gaierror as e:
        error_msg = f"Ошибка при подключении к серверу {mail_server} для {account_name}: {e}"
        logger.error(error_msg)
        send_telegram_notification(bot, chat_id, error_msg, is_error=True)
    except Exception as e:
        error_msg = f"Не удалось установить соединение с сервером {mail_server} для {account_name}: {e}"
        logger.error(error_msg)
        send_telegram_notification(bot, chat_id, error_msg, is_error=True)


# Проверка наличия новых писем для всех аккаунтов
def check_emails(config: dict, bot: telebot.TeleBot, chat_id: str, config_file: str) -> None:
    """Checks for new emails in all configured accounts."""
    accounts = config['email_accounts']

    # Получаем черный список
    blacklist = config.get('blacklist', {})

    # Проверяем каждый аккаунт
    for i, account in enumerate(accounts):
        check_account_emails(config, account, i, bot, chat_id, blacklist, config_file)


# Обработка сигналов для корректного завершения
def signal_handler(sig: int, frame: object) -> None:
    """Handles signals for graceful shutdown."""
    logger.info("Получен сигнал завершения. Закрываем бота...")
    sys.exit(0)


# Основной цикл
def main() -> None:
    """Main function of the email bot."""
    parser = argparse.ArgumentParser(description="Telegram bot for forwarding emails.")
    parser.add_argument('--config', type=str, default=CONFIG_FILE, help='Path to the configuration file.')
    args = parser.parse_args()

    config_file = args.config
    config = load_config(config_file)

    # Настройки Telegram
    bot_token = config['telegram']['bot_token']
    chat_id = config['telegram']['chat_id']

    check_interval = config['settings']['check_interval']

    # Создаем бота
    bot = telebot.TeleBot(bot_token)

    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Бот для пересылки писем в Telegram запущен")

    while True:
        try:
            check_emails(config, bot, chat_id, config_file)
            time.sleep(check_interval)
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
            time.sleep(check_interval)


if __name__ == "__main__":
    main()
