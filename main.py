import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import Error
import telebot
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
import random

load_dotenv()

print('Start telegram bot...')

state_storage = StateMemoryStorage()
token_bot = os.getenv('TOKEN')

# Настройка таймаутов
telebot.apihelper.CONNECT_TIMEOUT = 30
telebot.apihelper.READ_TIMEOUT = 30

bot = TeleBot(token_bot, state_storage=state_storage, parse_mode=None)

# Подключение к базе данных
try:
    connection = psycopg2.connect(
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port="5432",
        database=os.getenv('DB_NAME'),
        client_encoding='utf8'
    )
    cursor = connection.cursor()
    print("Успешное подключение к базе данных")
except (Exception, Error) as error:
    print("Ошибка при подключении к PostgreSQL:", error)

known_users = []
userStep = {}
buttons = []
current_word_data = {}  # Глобальная переменная для хранения текущего слова


def show_hint(*lines):
    return '\n'.join(lines)


def show_target(data):
    return f"{data['target_word']} -> {data['translate_word']}"


class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'
    RESTART = 'Перезапустить бота 🔄'


class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    another_words = State()
    add_word = State()


def get_user_step(uid):
    if uid in userStep:
        return userStep[uid]
    else:
        known_users.append(uid)
        userStep[uid] = 0
        print("New user detected, who hasn't used \"/start\" yet")
        return 0


def reset_user_progress(user_id):
    try:
        cursor.execute("""
            DELETE FROM user_words 
            WHERE user_id = %s
        """, (user_id,))
        connection.commit()
        print(f"Прогресс пользователя {user_id} сброшен")
    except (Exception, Error) as error:
        print(f"Ошибка при сбросе прогресса пользователя: {error}")
        connection.rollback()  # Откатываем транзакцию при ошибке


def get_random_word(user_id, show_all=False):
    try:
        print(f"Получаем случайное слово для пользователя {user_id}")
        if show_all:
            cursor.execute("""
                SELECT w.word_id, w.word, w.translation 
                FROM words w
                WHERE w.word_id NOT IN (
                    SELECT word_id 
                    FROM user_words 
                    WHERE user_id = %s
                )
                ORDER BY RANDOM()
                LIMIT 1
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT w.word_id, w.word, w.translation 
                FROM words w
                LEFT JOIN user_words uw ON w.word_id = uw.word_id AND uw.user_id = %s
                WHERE uw.user_id IS NULL
                ORDER BY RANDOM()
                LIMIT 1
            """, (user_id,))
        result = cursor.fetchone()
        if result:
            print(f"Найдено слово: {result}")
        else:
            print("Слов не найдено")
        return result
    except (Exception, Error) as error:
        print(f"Ошибка при получении слова: {error}")
        connection.rollback()
        return None


def get_random_other_words(word_id, count=3):
    try:
        cursor.execute("""
            SELECT word, translation 
            FROM words 
            WHERE word_id != %s 
            ORDER BY RANDOM() 
            LIMIT %s
        """, (word_id, count))
        return cursor.fetchall()
    except (Exception, Error) as error:
        print("Ошибка при получении других слов:", error)
        return []


def add_user_word(user_id, word_id):
    try:
        print(f"Добавляем слово {word_id} пользователю {user_id}")
        # Проверяем, не существует ли уже такая запись
        cursor.execute("""
            SELECT 1 FROM user_words 
            WHERE user_id = %s AND word_id = %s
        """, (user_id, word_id))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO user_words (user_id, word_id) 
                VALUES (%s, %s)
            """, (user_id, word_id))
            connection.commit()
            print("Слово успешно добавлено пользователю")
            return True
        print("Слово уже существует у пользователя")
        return False
    except (Exception, Error) as error:
        print(f"Ошибка при добавлении слова пользователю: {error}")
        connection.rollback()
        return False


def delete_user_word(user_id, word_id):
    try:
        cursor.execute("""
            DELETE FROM user_words 
            WHERE user_id = %s AND word_id = %s
        """, (user_id, word_id))
        connection.commit()
    except (Exception, Error) as error:
        print("Ошибка при удалении слова у пользователя:", error)


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


def process_english_word(message, user_id):
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
                        "SELECT id FROM words WHERE LOWER(target_word) = %s",
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


def process_translation(message, english_word, user_id):
    try:
        cid = message.chat.id
        translation = message.text.strip()

        if not translation:
            bot.send_message(cid, "Перевод не может быть пустым. Попробуйте еще раз.")
            return

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
                        "INSERT INTO words (target_word, translate_word) "
                        "VALUES (%s, %s) RETURNING id",
                        (english_word, translation)
                    )
                    word_id = cur.fetchone()[0]

                    # Сразу добавляем слово пользователю
                    cur.execute(
                        "INSERT INTO user_words (user_id, word_id) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (user_id, word_id)
                    )

            bot.send_message(
                cid,
                f"Слово '{english_word}' с переводом '{translation}' "
                "успешно добавлено в ваш словарь!"
            )
        finally:
            conn.close()
    except Exception as e:
        print(f"Ошибка при обработке перевода: {e}")
        try:
            bot.send_message(cid, "Произошла ошибка. Попробуйте еще раз.")
        except Exception as e:
            print(f"Ошибка при отправке сообщения об ошибке: {e}")


def ensure_user_exists(user_id, username):
    try:
        print(f"Проверяем существование пользователя {user_id}")  # Отладочное сообщение
        cursor.execute("""
            SELECT user_id FROM users WHERE user_id = %s
        """, (user_id,))
        if not cursor.fetchone():
            print(f"Создаем нового пользователя {user_id}")  # Отладочное сообщение
            cursor.execute("""
                INSERT INTO users (user_id, username) 
                VALUES (%s, %s)
            """, (user_id, username))
            connection.commit()
            print("Пользователь успешно создан")  # Отладочное сообщение
    except (Exception, Error) as error:
        print(f"Ошибка при проверке/создании пользователя: {error}")  # Отладочное сообщение


@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):
    try:
        cid = message.chat.id
        if cid not in known_users:
            known_users.append(cid)
            userStep[cid] = 0
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
        
        target_word_btn = types.KeyboardButton(target_word)
        buttons.append(target_word_btn)
        other_words_btns = [types.KeyboardButton(word[0]) for word in other_words]
        buttons.extend(other_words_btns)
        random.shuffle(buttons)
        
        next_btn = types.KeyboardButton(Command.NEXT)
        add_word_btn = types.KeyboardButton(Command.ADD_WORD)
        delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
        restart_btn = types.KeyboardButton(Command.RESTART)
        buttons.extend([next_btn, add_word_btn, delete_word_btn, restart_btn])
        
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
    cid = message.chat.id
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        if 'word_id' in data:
            delete_user_word(cid, data['word_id'])
            bot.send_message(cid, "Слово успешно удалено из вашего списка! ✅")
        else:
            bot.send_message(cid, "Не удалось удалить слово. Попробуйте позже.")
    create_cards(message)


@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message):
    cid = message.chat.id
    bot.send_message(cid, "Введите слово на английском:")
    bot.set_state(message.from_user.id, MyStates.add_word, message.chat.id)


@bot.message_handler(state=MyStates.add_word)
def process_add_word(message):
    cid = message.chat.id
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['new_word'] = message.text
        bot.send_message(cid, "Теперь введите перевод:")
        bot.set_state(message.from_user.id, MyStates.translate_word, message.chat.id)


@bot.message_handler(state=MyStates.translate_word)
def process_translate_word(message):
    cid = message.chat.id
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        if 'new_word' in data:
            word_id = add_new_word(message)
            if word_id:
                add_user_word(cid, word_id)
                bot.send_message(cid, "Слово успешно добавлено! ✅")
            else:
                bot.send_message(cid, "Произошла ошибка при добавлении слова. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)
            create_cards(message)


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
            current_buttons.extend([next_btn, add_word_btn, delete_word_btn, restart_btn])
            
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


bot.add_custom_filter(custom_filters.StateFilter(bot))

bot.infinity_polling(skip_pending=True)