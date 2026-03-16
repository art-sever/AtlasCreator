# AtlasCreator

Локальный desktop-инструмент для macOS: видео или изображение -> удаление фона через `rembg` -> прозрачный `PNG` или `spritesheet.png`. Используется для создания покадровой анимации из видео и для быстрой вырезки объекта из одиночной картинки.

## Требования

- Python 3.9+
- `ffmpeg` и `ffprobe` в `PATH`
- Зависимости Python из `pyproject.toml`

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m src.main
```

Если `rembg` уже был установлен без backend, доустановите CPU backend:

```bash
pip install "rembg[cpu]"
```

## Запуск через ярлык (без ручного терминала)

В корне проекта есть ярлык `Launch AtlasCreator.command`.

1. При первом запуске подготовьте окружение из блока «Быстрый старт».
2. После этого запускайте приложение двойным кликом по `Launch AtlasCreator.command`.
3. При желании можно создать alias этого файла и вынести его на рабочий стол.

## Что умеет MVP

- Загрузка `mp4/mov` и `png/jpg/jpeg`
- Извлечение кадров (`Target FPS` и `Exact Frame Count`)
- Batch-удаление фона через `rembg`
- Удаление фона у одиночного изображения и экспорт прозрачного `PNG` без обязательной сборки spritesheet
- 3 режима ресайза (`Fit`, `Crop Center`, `Stretch`)
- Сборка и экспорт `spritesheet.png` с прозрачностью

## Важные ограничения

- Работа полностью локально
- Без JSON metadata
- Без сохранения проекта
- Без автопересчета после изменения параметров
