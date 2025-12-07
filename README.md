# Stalcraft Modules API

Простой API-сервис для расчёта статов модулей по формуле `value = a + b * q` на основе коэффициентов из `modules.json`.

## Запуск локально

```bash
# клон репозитория
git clone https://github.com/ayojoydev/modules_api
cd modules_api

# (опционально) создать виртуальное окружение
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# установить зависимости
pip install fastapi "uvicorn[standard]"

# запустить сервер
uvicorn app:app

Сервер по умолчанию поднимется на:
http://127.0.0.1:8000

Swagger / документация

Интерактивная документация (Swagger UI):
http://127.0.0.1:8000/docs

Альтернатива (ReDoc):
http://127.0.0.1:8000/redoc