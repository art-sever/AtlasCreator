#!/bin/bash

set -euo pipefail

# Переходим в каталог проекта независимо от того, откуда запущен ярлык.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Подхватываем venv, если он уже создан.
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

# Запускаем приложение через установленный entry point, если доступен.
if [ -x ".venv/bin/atlas-creator" ]; then
  exec ".venv/bin/atlas-creator"
fi

# Фолбэк для случая запуска без локального entry point.
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m src.main
fi

echo "Не найден Python 3. Установите Python 3.9+ и зависимости проекта."
read -r -p "Нажмите Enter для выхода..."
