# EnglishCard - Telegram Bot для изучения английского языка

Бот для изучения английского языка, который помогает запоминать слова с помощью карточек.

## Функциональность

- 🎯 Изучение слов с помощью карточек
- 📝 Добавление новых слов
- 🗑 Удаление слов из личного словаря
- 👨‍💼 Административные функции (удаление слов из общей базы)
- 🔄 Сброс прогресса
- 📊 Отслеживание прогресса

## Требования

- Python 3.8+
- PostgreSQL
- Библиотеки:
  - telebot
  - psycopg2
  - python-dotenv

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/EnglishCard.git
cd EnglishCard
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` с настройками:
```env
TOKEN=your_telegram_bot_token
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_NAME=your_db_name
```

4. Создайте базу данных и таблицы:
```sql
CREATE DATABASE english_card;
\c english_card

CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255)
);

CREATE TABLE words (
    word_id SERIAL PRIMARY KEY,
    word VARCHAR(255) NOT NULL,
    translation VARCHAR(255) NOT NULL
);

CREATE TABLE user_words (
    user_id BIGINT REFERENCES users(user_id),
    word_id INTEGER REFERENCES words(word_id),
    PRIMARY KEY (user_id, word_id)
);
```

## Использование

1. Запустите бота:
```bash
python main.py
```

2. В Telegram:
   - Начните с команды `/start`
   - Используйте кнопки для навигации:
     - `Дальше ⏭` - следующее слово
     - `Добавить слово ➕` - добавить новое слово
     - `Удалить слово🔙` - удалить слово из личного словаря
     - `Перезапустить бота 🔄` - сбросить прогресс
     - `Удалить слово из базы 🗑` - удалить слово из общей базы (только для администраторов)

## Особенности

- 🎯 4 варианта ответа для каждого слова
- 📝 Персональный словарь для каждого пользователя
- 🔄 Автоматическая инициализация базы данных
- 🛡 Защита от дублирования слов
- 📊 Отображение количества выученных слов

## Структура базы данных

1. Таблица `users`:
   - `user_id` - ID пользователя в Telegram
   - `username` - имя пользователя

2. Таблица `words`:
   - `word_id` - уникальный идентификатор слова
   - `word` - английское слово
   - `translation` - перевод

3. Таблица `user_words`:
   - `user_id` - ID пользователя
   - `word_id` - ID слова
   - Связь многие-ко-многим между пользователями и словами

## Обновление проекта

1. Получите последние изменения:
```bash
git pull origin main
```

2. Установите новые зависимости (если есть):
```bash
pip install -r requirements.txt
```

3. Перезапустите бота:
```bash
python main.py
```

