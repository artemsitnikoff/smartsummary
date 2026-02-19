# Деплой SmartSummary

## Требования к серверу

- Docker + Docker Compose
- Git
- Доступ к OpenAI API (VPN если сервер в РФ)

## Первый запуск

### 1. Клонировать репозиторий

```bash
git clone https://github.com/artemsitnikoff/smartsummary.git
cd smartsummary
```

### 2. Создать `.env`

```bash
cp .env.example .env
nano .env
```

Заполнить все поля:

| Переменная | Описание |
|---|---|
| `API_ID` | Telegram API ID (https://my.telegram.org) |
| `API_HASH` | Telegram API Hash |
| `OPENAI_API_KEY` | Ключ OpenAI API |
| `BITRIX_CLIENT_ID` | Bitrix24 OAuth client ID |
| `BITRIX_CLIENT_SECRET` | Bitrix24 OAuth client secret |
| `BITRIX_DOMAIN` | Домен Bitrix24 (например `company.bitrix24.ru`) |
| `BITRIX_REFRESH_TOKEN` | Начальный refresh token Bitrix24 |
| `JIRA_URL` | URL Jira Server |
| `JIRA_USERNAME` | Логин Jira |
| `JIRA_PASSWORD` | Пароль Jira |

### 3. Авторизовать Telegram-сессию

Сессию нужно создать один раз — она привязывает бота к аккаунту Telegram.

```bash
docker compose run --rm smartsummary python auth.py
```

Ввести номер телефона и код из Telegram. Появится файл `smartsummary.session`.

### 4. Запустить

```bash
docker compose up -d --build
```

Проверить:

```bash
# Логи
docker compose logs -f --tail=50

# API
curl http://localhost:8001/api/me
```

## Обновление

```bash
./deploy.sh
```

Или вручную:

```bash
git pull
docker compose up -d --build
```

## Управление

```bash
# Статус
docker compose ps

# Логи (live)
docker compose logs -f --tail=100

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Пересборка без кеша
docker compose build --no-cache && docker compose up -d
```

## Файлы на сервере (не в git)

| Файл | Описание |
|---|---|
| `.env` | Секреты и конфигурация |
| `smartsummary.session` | Telegram-сессия (создаётся через `auth.py`) |
| `bitrix_tokens.json` | OAuth токены Bitrix24 (создаётся автоматически) |

Эти файлы монтируются в контейнер через volumes в `docker-compose.yml`.

## Проверка работоспособности

1. **API**: `curl http://localhost:8001/api/me` — должен вернуть имя и username
2. **Триггеры**: написать "Суммаризация" в любой чат Telegram
3. **Bitrix**: написать "Найди время @nickname" в чат
4. **Swagger UI**: открыть `http://<server-ip>:8001/docs`
