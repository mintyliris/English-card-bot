import os
import random
import time
from typing import List, Tuple, Dict, Set, Optional

import psycopg2
from dotenv import load_dotenv
from psycopg2 import Error
import telebot
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup

# Глобальные переменные
known_users: Set[int] = set()
user_step: Dict[int, int] = {}
buttons: List[types.KeyboardButton] = []
current_word_data: Dict[int, Dict[str, str | int]] = {}

# Константы
CONNECT_TIMEOUT: int = 60
READ_TIMEOUT: int = 60
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5
ADMIN_IDS: List[int] = [123456789]  # Замените на ваш ID в Telegram

load_dotenv()

print('Start telegram bot...')

state_storage = StateMemoryStorage()
token_bot = os.getenv('TOKEN')

# Настройка таймаутов
telebot.apihelper.CONNECT_TIMEOUT = CONNECT_TIMEOUT
telebot.apihelper.READ_TIMEOUT = READ_TIMEOUT

bot = TeleBot(token_bot, state_storage=state_storage, parse_mode=None)

def get_connection():
    """Получение соединения с базой данных."""
    try:
        conn = psycopg2.connect(
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port="5432",
            database=os.getenv('DB_NAME'),
            client_encoding='utf8'
        )
        print("Успешное подключение к базе данных")
        return conn
    except psycopg2.Error as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        return None

def show_hint(*lines: str) -> str:
    """Форматирование подсказки.
    
    Args:
        *lines: Строки для объединения
        
    Returns:
        str: Объединенные строки через перенос строки
    """
    return '\n'.join(lines)


def show_target(data: Dict[str, str]) -> str:
    """Форматирование целевого слова и перевода.
    
    Args:
        data: Словарь с ключами 'target_word' и 'translate_word'
        
    Returns:
        str: Отформатированная строка с переводом
    """
    return f"{data['target_word']} -> {data['translate_word']}"


class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'
    RESTART = 'Перезапустить бота 🔄'
    ADMIN_DELETE_WORD = 'Удалить слово из базы 🗑'


class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    another_words = State()
    add_word = State()


def get_user_step(uid: int) -> int:
    """Получение текущего шага пользователя.
    
    Args:
        uid: ID пользователя в Telegram
        
    Returns:
        int: Текущий шаг пользователя (0 по умолчанию)
    """
    if uid in user_step:
        return user_step[uid]
    else:
        known_users.add(uid)  # Используем set вместо list
        user_step[uid] = 0
        print(f"Новый пользователь {uid} обнаружен")
        return 0


def reset_user_progress(user_id):
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM user_words 
                        WHERE user_id = %s
                    """, (user_id,))
                    conn.commit()
                    print(f"Прогресс пользователя {user_id} сброшен")
        finally:
            conn.close()
    except (Exception, Error) as error:
        print(f"Ошибка при сбросе прогресса пользователя: {error}")
        if 'conn' in locals():
            conn.rollback()  # Откатываем транзакцию при ошибке


# SQL запросы
SQL_GET_RANDOM_WORD: str = """
    SELECT w.word_id, w.word, w.translation 
    FROM words w 
    WHERE w.word_id NOT IN (
        SELECT word_id FROM user_words WHERE user_id = %s
    ) 
    ORDER BY RANDOM() 
    LIMIT 1
"""

SQL_GET_RANDOM_WORD_ALL: str = """
    SELECT w.word_id, w.word, w.translation 
    FROM words w 
    LEFT JOIN user_words uw ON w.word_id = uw.word_id 
    AND uw.user_id = %s 
    WHERE uw.user_id IS NULL 
    ORDER BY RANDOM() 
    LIMIT 1
"""

SQL_GET_OTHER_WORDS: str = """
    SELECT word 
    FROM words 
    WHERE word_id != %s 
    ORDER BY RANDOM() 
    LIMIT %s
"""

SQL_CHECK_USER_WORD: str = """
    SELECT 1 
    FROM user_words 
    WHERE user_id = %s AND word_id = %s
"""

SQL_INSERT_USER_WORD: str = """
    INSERT INTO user_words (user_id, word_id) 
    VALUES (%s, %s)
"""

SQL_INITIAL_WORDS: str = """
    INSERT INTO words (word, translation) VALUES
    ('red', 'красный'),
    ('blue', 'синий'),
    ('green', 'зеленый'),
    ('yellow', 'желтый'),
    ('black', 'черный'),
    ('white', 'белый'),
    ('I', 'я'),
    ('you', 'ты'),
    ('he', 'он'),
    ('she', 'она')
    ON CONFLICT DO NOTHING;
"""

def initialize_database() -> None:
    """Инициализация базы данных начальными данными."""
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(SQL_INITIAL_WORDS)
                    conn.commit()
                    print("База данных успешно инициализирована")
        finally:
            conn.close()
    except (Exception, Error) as error:
        print(f"Ошибка при инициализации базы данных: {error}")
        if 'conn' in locals():
            conn.rollback()

def get_random_word(user_id: int, show_all: bool = False) -> Tuple[int, str, str] | None:
    """Получение случайного слова для пользователя."""
    try:
        print(f"Получаем случайное слово для пользователя {user_id}")
        conn = get_connection()
        if not conn:
            return None

        try:
            with conn:
                with conn.cursor() as cur:
                    if show_all:
                        cur.execute(SQL_GET_RANDOM_WORD_ALL, (user_id,))
                    else:
                        cur.execute(SQL_GET_RANDOM_WORD, (user_id,))
                    result = cur.fetchone()
                    if result:
                        print(f"Найдено слово: {result}")
                    else:
                        print("Слов не найдено")
                    return result
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при получении слова: {e}")
        return None


def get_random_other_words(word_id: int, count: int = 3) -> List[Tuple[str]]:
    """Получение случайных слов для вариантов ответа."""
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return []

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(SQL_GET_OTHER_WORDS, (word_id, count))
                    return cur.fetchall()
        finally:
            conn.close()
    except (Exception, Error) as error:
        print("Ошибка при получении других слов:", error)
        return []


def add_user_word(user_id: int, word_id: int) -> bool:
    """Добавление слова пользователю."""
    try:
        print(f"Добавляем слово {word_id} пользователю {user_id}")
        conn = get_connection()
        if not conn:
            return False

        try:
            with conn:
                with conn.cursor() as cur:
                    # Проверяем, не существует ли уже такая запись
                    cur.execute(SQL_CHECK_USER_WORD, (user_id, word_id))
                    if not cur.fetchone():
                        cur.execute(SQL_INSERT_USER_WORD, (user_id, word_id))
                        print("Слово успешно добавлено пользователю")
                        return True
                    print("Слово уже существует у пользователя")
                    return False
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при добавлении слова пользователю: {e}")
        return False


def delete_user_word(user_id: int, word_id: int) -> None:
    """Удаление слова у пользователя."""
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM user_words 
                        WHERE user_id = %s AND word_id = %s
                    """, (user_id, word_id))
                    conn.commit()
        finally:
            conn.close()
    except (Exception, Error) as error:
        print("Ошибка при удалении слова у пользователя:", error)
        if 'conn' in locals():
            conn.rollback()


def add_new_word(message):
    try:
        cid = message.chat.id
        user_id = message.from_user.id

        # Проверяем существование пользователя
        if not ensure_user_exists(user_id, message.from_user.username):
            bot.send_message(cid, "Ошибка: пользователь не найден")
            return

        # Запрашиваем английское слово
        bot.send_message(cid, "Введите английское слово:")
        bot.register_next_step_handler(message, lambda m: process_english_word(m, user_id))
    except Exception as e:
        print(f"Ошибка при добавлении слова: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def process_english_word(message: types.Message, user_id: int) -> None:
    """Обработка введенного английского слова.
    
    Args:
        message: Сообщение от пользователя
        user_id: ID пользователя в Telegram
    """
    try:
        cid = message.chat.id
        english_word = message.text.strip().lower()

        if not english_word:
            bot.send_message(cid, "Слово не может быть пустым. Попробуйте еще раз.")
            return

        # Проверяем, существует ли уже такое слово
        conn = get_connection()
        if not conn:
            bot.send_message(cid, "Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT word_id FROM words WHERE LOWER(word) = %s",
                        (english_word,)
                    )
                    if cur.fetchone():
                        bot.send_message(
                            cid,
                            "Такое слово уже существует в базе данных."
                        )
                        return

            # Запрашиваем перевод
            bot.send_message(cid, "Введите перевод слова:")
            bot.register_next_step_handler(
                message,
                lambda m: process_translation(m, english_word, user_id)
            )
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при обработке английского слова: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def get_user_words_count(user_id: int) -> int:
    """Получение количества слов пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        int: Количество слов пользователя
    """
    try:
        conn = get_connection()
        if not conn:
            return 0

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM user_words WHERE user_id = %s",
                        (user_id,)
                    )
                    count = cur.fetchone()[0]
                    return count
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при подсчете слов пользователя: {e}")
        return 0


@bot.message_handler(state=MyStates.translate_word)
def process_translate_word(message):
    try:
        cid = message.chat.id
        user_id = message.from_user.id
        translation = message.text.strip()

        if not translation:
            bot.send_message(cid, "Перевод не может быть пустым. Попробуйте еще раз.")
            return

        # Получаем сохраненное английское слово
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            if 'new_word' not in data:
                bot.send_message(cid, "Произошла ошибка. Начните добавление слова заново.")
                bot.delete_state(message.from_user.id, message.chat.id)
                create_cards(message)
                return

            english_word = data['new_word']

        # Добавляем слово в базу данных
        conn = get_connection()
        if not conn:
            bot.send_message(cid, "Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    # Добавляем слово
                    cur.execute(
                        "INSERT INTO words (word, translation) "
                        "VALUES (%s, %s) RETURNING word_id",
                        (english_word, translation)
                    )
                    word_id = cur.fetchone()[0]

                    # Сразу добавляем слово пользователю
                    cur.execute(
                        "INSERT INTO user_words (user_id, word_id) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (user_id, word_id)
                    )

            # Получаем количество слов пользователя
            words_count = get_user_words_count(user_id)
            
            bot.send_message(
                cid,
                f"Слово '{english_word}' с переводом '{translation}' "
                f"успешно добавлено в ваш словарь!\n"
                f"Всего слов в вашем словаре: {words_count}"
            )
        finally:
            conn.close()

        # Сбрасываем состояние и показываем новую карточку
        bot.delete_state(message.from_user.id, message.chat.id)
        create_cards(message)
    except Exception as e:
        print(f"Ошибка при обработке перевода: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
            bot.delete_state(message.from_user.id, message.chat.id)
            create_cards(message)
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def ensure_user_exists(user_id: int, username: str | None) -> bool:
    """Проверка и создание пользователя в базе данных.
    
    Args:
        user_id: ID пользователя в Telegram
        username: Имя пользователя в Telegram
        
    Returns:
        bool: True если пользователь существует или был создан, False в случае ошибки
    """
    try:
        print(f"Проверяем существование пользователя {user_id}")
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return False

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT user_id FROM users WHERE user_id = %s
                    """, (user_id,))
                    if not cur.fetchone():
                        print(f"Создаем нового пользователя {user_id}")
                        cur.execute("""
                            INSERT INTO users (user_id, username) 
                            VALUES (%s, %s)
                        """, (user_id, username))
                        conn.commit()
                        print("Пользователь успешно создан")
                        return True
                    return True
        finally:
            conn.close()
    except (Exception, Error) as error:
        print(f"Ошибка при проверке/создании пользователя: {error}")
        return False


@bot.message_handler(commands=['cards', 'start'])
def create_cards(message: types.Message) -> None:
    """Создание новой карточки со словом.
    
    Args:
        message: Сообщение от пользователя
    """
    try:
        cid = message.chat.id
        if cid not in known_users:
            known_users.add(cid)
            user_step[cid] = 0
            bot.send_message(cid, "Привет! Давайте изучать английский язык вместе! 🇬🇧")
            ensure_user_exists(cid, message.from_user.username)
        
        word_data = get_random_word(cid, show_all=True)  # Показываем все слова
        if not word_data:
            bot.send_message(cid, "Поздравляем! Вы выучили все слова! 🎉")
            return

        word_id, target_word, translate = word_data
        other_words = get_random_other_words(word_id)
        
        markup = types.ReplyKeyboardMarkup(row_width=2)
        global buttons
        buttons = []
        
        # Добавляем кнопки с вариантами ответов
        target_word_btn = types.KeyboardButton(target_word)
        buttons.append(target_word_btn)
        other_words_btns = [types.KeyboardButton(word[0]) for word in other_words]
        buttons.extend(other_words_btns)
        
        # Перемешиваем кнопки с вариантами ответов
        random.shuffle(buttons)
        
        # Добавляем кнопки управления
        next_btn = types.KeyboardButton(Command.NEXT)
        add_word_btn = types.KeyboardButton(Command.ADD_WORD)
        delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
        restart_btn = types.KeyboardButton(Command.RESTART)
        admin_delete_btn = types.KeyboardButton(Command.ADMIN_DELETE_WORD)
        buttons.extend([next_btn, add_word_btn, delete_word_btn, restart_btn, admin_delete_btn])
        
        markup.add(*buttons)
        
        greeting = f"Выбери перевод слова:\n🇷🇺 {translate}"
        bot.send_message(message.chat.id, greeting, reply_markup=markup)
        
        # Обновляем глобальную переменную
        current_word_data[cid] = {
            'target_word': target_word,
            'translate_word': translate,
            'word_id': word_id
        }
        print(f"Обновлено текущее слово: {current_word_data[cid]}")
    except Exception as e:
        print(f"Ошибка при создании карточки: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    try:
        cid = message.chat.id
        # Сбрасываем состояние перед показом новой карточки
        bot.delete_state(message.from_user.id, message.chat.id)
        create_cards(message)
    except Exception as e:
        print(f"Ошибка при переходе к следующей карточке: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
            create_cards(message)
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def delete_word(message):
    try:
        cid = message.chat.id
        user_id = message.from_user.id

        # Проверяем наличие текущего слова
        if cid not in current_word_data:
            bot.send_message(cid, "Нет активного слова для удаления")
            return

        current_data = current_word_data[cid]
        word_id = current_data['word_id']

        # Удаляем слово из словаря пользователя
        conn = get_connection()
        if not conn:
            bot.send_message(cid, "Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    # Удаляем связь между пользователем и словом
                    cur.execute(
                        "DELETE FROM user_words WHERE user_id = %s AND word_id = %s",
                        (user_id, word_id)
                    )
                    if cur.rowcount > 0:
                        bot.send_message(
                            cid,
                            f"Слово '{current_data['target_word']}' "
                            "успешно удалено из вашего словаря!"
                        )
                    else:
                        bot.send_message(
                            cid,
                            "Это слово уже отсутствует в вашем словаре"
                        )
        finally:
            conn.close()

        # Показываем новую карточку
        create_cards(message)
    except Exception as e:
        print(f"Ошибка при удалении слова: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка при удалении слова")
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message):
    cid = message.chat.id
    bot.send_message(cid, "Введите слово на английском:")
    bot.set_state(message.from_user.id, MyStates.add_word, message.chat.id)


@bot.message_handler(state=MyStates.add_word)
def process_add_word(message):
    try:
        cid = message.chat.id
        user_id = message.from_user.id
        english_word = message.text.strip().lower()

        if not english_word:
            bot.send_message(cid, "Слово не может быть пустым. Попробуйте еще раз.")
            return

        # Проверяем, существует ли уже такое слово
        conn = get_connection()
        if not conn:
            bot.send_message(cid, "Ошибка подключения к базе данных")
            return

        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT word_id FROM words WHERE LOWER(word) = %s",
                        (english_word,)
                    )
                    if cur.fetchone():
                        bot.send_message(
                            cid,
                            "Такое слово уже существует в базе данных."
                        )
                        bot.delete_state(message.from_user.id, message.chat.id)
                        create_cards(message)
                        return

            # Сохраняем слово и запрашиваем перевод
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['new_word'] = english_word
                bot.send_message(cid, "Теперь введите перевод:")
                bot.set_state(message.from_user.id, MyStates.translate_word, message.chat.id)
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при обработке английского слова: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
            bot.delete_state(message.from_user.id, message.chat.id)
            create_cards(message)
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


@bot.message_handler(func=lambda message: message.text == Command.RESTART)
def restart_bot(message):
    cid = message.chat.id
    bot.send_message(cid, "Бот перезапускается...")
    reset_user_progress(cid)  # Сброс прогресса
    create_cards(message)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message):
    try:
        cid = message.chat.id
        text = message.text
        
        # Проверяем команды
        if text == Command.RESTART:
            restart_bot(message)
            return
        elif text == Command.ADD_WORD:
            add_word(message)
            return
        elif text == Command.DELETE_WORD:
            delete_word(message)
            return
        elif text == Command.NEXT:
            next_cards(message)
            return
        elif text == Command.ADMIN_DELETE_WORD:
            admin_delete_word(message)
            return
        
        # Проверяем наличие текущего слова
        if cid not in current_word_data:
            print("Нет текущего слова, создаем новую карточку")
            create_cards(message)
            return
        
        current_data = current_word_data[cid]
        current_word = current_data['target_word']
        current_translation = current_data['translate_word']
        current_word_id = current_data['word_id']
        
        print(f"Текущее слово: '{current_word}', перевод '{current_translation}', ID {current_word_id}")
        print(f"Сравниваем ответы: '{text}' и '{current_word}'")
        
        if text.strip().lower() == current_word.strip().lower():
            # Правильный ответ
            print(f"Ответ верный! Добавляем слово {current_word_id} пользователю {cid}")
            if add_user_word(cid, current_word_id):
                hint = show_target(current_data)
                hint_text = ["Отлично!❤", hint]
                hint = show_hint(*hint_text)
                markup = types.ReplyKeyboardMarkup(row_width=2)
                markup.add(*buttons)
                bot.send_message(cid, hint, reply_markup=markup)
                # Показываем новую карточку
                create_cards(message)
            else:
                # Если слово уже существует, просто показываем новую карточку
                create_cards(message)
        else:
            # Неправильный ответ
            print(f"Ответ неверный! Ожидалось: '{current_word}', получено: '{text}'")
            hint = show_hint("Допущена ошибка!",
                           f"Попробуй ещё раз вспомнить слово 🇷🇺{current_translation}")
            
            # Обновляем клавиатуру
            markup = types.ReplyKeyboardMarkup(row_width=2)
            current_buttons = []
            
            # Добавляем правильный ответ
            target_word_btn = types.KeyboardButton(current_word)
            current_buttons.append(target_word_btn)
            
            # Получаем другие слова для вариантов ответа
            other_words = get_random_other_words(current_word_id)
            other_words_btns = [types.KeyboardButton(word[0]) for word in other_words]
            current_buttons.extend(other_words_btns)
            random.shuffle(current_buttons)
            
            # Добавляем кнопки управления
            next_btn = types.KeyboardButton(Command.NEXT)
            add_word_btn = types.KeyboardButton(Command.ADD_WORD)
            delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
            restart_btn = types.KeyboardButton(Command.RESTART)
            admin_delete_btn = types.KeyboardButton(Command.ADMIN_DELETE_WORD)
            current_buttons.extend([next_btn, add_word_btn, delete_word_btn, restart_btn, admin_delete_btn])
            
            markup.add(*current_buttons)
            bot.send_message(cid, hint, reply_markup=markup)
            
            # Оставляем текущее слово
            print(f"Оставляем текущее слово: '{current_word}', перевод '{current_translation}', ID {current_word_id}")
    except Exception as e:
        print(f"Ошибка в обработке сообщения: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
            create_cards(message)
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def delete_word_from_database(word_id):
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return False

        try:
            with conn:
                with conn.cursor() as cur:
                    # Сначала удаляем все связи с пользователями
                    cur.execute("""
                        DELETE FROM user_words 
                        WHERE word_id = %s
                    """, (word_id,))
                    
                    # Затем удаляем само слово
                    cur.execute("""
                        DELETE FROM words 
                        WHERE word_id = %s
                    """, (word_id,))
                    
                    conn.commit()
                    return True
        finally:
            conn.close()
    except (Exception, Error) as error:
        print(f"Ошибка при удалении слова из базы: {error}")
        if 'conn' in locals():
            conn.rollback()
        return False


@bot.message_handler(func=lambda message: message.text == Command.ADMIN_DELETE_WORD)
def admin_delete_word(message):
    try:
        cid = message.chat.id
        if cid not in ADMIN_IDS:
            bot.send_message(cid, "У вас нет прав для удаления слов из базы данных")
            return

        if cid not in current_word_data:
            bot.send_message(cid, "Нет активного слова для удаления")
            return

        current_data = current_word_data[cid]
        word_id = current_data['word_id']
        
        if delete_word_from_database(word_id):
            bot.send_message(cid, f"Слово '{current_data['target_word']}' успешно удалено из базы данных!")
            # Показываем новую карточку
            create_cards(message)
        else:
            bot.send_message(cid, "Произошла ошибка при удалении слова из базы данных")
            # Показываем новую карточку
            create_cards(message)
    except Exception as e:
        print(f"Ошибка при удалении слова администратором: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка при удалении слова")
            # Показываем новую карточку
            create_cards(message)
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def delete_unwanted_words():
    try:
        conn = get_connection()
        if not conn:
            print("Ошибка подключения к базе данных")
            return False

        try:
            with conn:
                with conn.cursor() as cur:
                    # Список нежелательных слов
                    unwanted_words = ['хуй', 'член', 'chlen']
                    
                    # Удаляем все связи с пользователями для нежелательных слов
                    cur.execute("""
                        DELETE FROM user_words 
                        WHERE word_id IN (
                            SELECT word_id FROM words 
                            WHERE LOWER(word) = ANY(%s) 
                            OR LOWER(translation) = ANY(%s)
                        )
                    """, (unwanted_words, unwanted_words))
                    
                    # Удаляем сами нежелательные слова
                    cur.execute("""
                        DELETE FROM words 
                        WHERE LOWER(word) = ANY(%s) 
                        OR LOWER(translation) = ANY(%s)
                    """, (unwanted_words, unwanted_words))
                    
                    conn.commit()
                    print("Нежелательные слова успешно удалены из базы данных")
                    return True
        finally:
            conn.close()
    except (Exception, Error) as error:
        print(f"Ошибка при удалении нежелательных слов: {error}")
        if 'conn' in locals():
            conn.rollback()
        return False


# Вызываем функцию при запуске бота
delete_unwanted_words()

bot.add_custom_filter(custom_filters.StateFilter(bot))

def start_bot():
    while True:
        try:
            print("Запуск бота...")
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            print(f"Ошибка при запуске бота: {e}")
            print("Повторная попытка через 5 секунд...")
            time.sleep(5)

if __name__ == "__main__":
    print("Инициализация базы данных...")
    initialize_database()
    print("Запуск бота...")
    start_bot()