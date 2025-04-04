# English Learning Bot

Telegram бот для изучения английского языка. 

## Функциональность

- Показ карточек с английскими словами и их переводами
- Проверка знаний через выбор правильного перевода
- Добавление новых слов в базу данных
- Отслеживание прогресса обучения
- Возможность сброса прогресса
- Система подсказок при неправильных ответах

## Технологии

- Python 3.x
- PostgreSQL
- python-telegram-bot
- psycopg2
- python-dotenv

## Установка и настройка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/EnglishCard.git
cd EnglishCard
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте базу данных PostgreSQL:
```sql
CREATE DATABASE db_english_bot;
```

5. Создайте таблицы в базе данных:
```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(255)
);

CREATE TABLE words (
    id SERIAL PRIMARY KEY,
    target_word VARCHAR(255) NOT NULL,
    translate_word VARCHAR(255) NOT NULL
);

CREATE TABLE user_words (
    user_id BIGINT REFERENCES users(id),
    word_id INTEGER REFERENCES words(id),
    PRIMARY KEY (user_id, word_id)
);
```

6. Создайте файл `.env` в корневой директории проекта:
```env
TOKEN=your_bot_token
DB_HOST=localhost
DB_NAME=db_english_bot
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

7. Запустите бота:
```bash
python main.py
```

## Использование

1. Запустите бота командой `/start` или `/cards`
2. Выберите правильный перевод предложенного слова
3. Используйте кнопки для управления:
   - "Дальше ⏭" - перейти к следующему слову
   - "Добавить слово ➕" - добавить новое слово
   - "Удалить слово🔙" - удалить слово из списка
   - "Перезапустить бота 🔄" - сбросить прогресс



## Важные замечания

- Не загружайте файл `.env` в репозиторий
- Храните чувствительные данные (токены, пароли) только в локальном файле `.env`
- Регулярно делайте бэкап базы данных
- Используйте виртуальное окружение для изоляции зависимостей
