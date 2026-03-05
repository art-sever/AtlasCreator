# MVP: Video -> Frame Extract -> rembg -> SpriteSheet

## 1. Назначение

Приложение конвертирует видео (`mp4/mov`) в `spritesheet.png` с прозрачным фоном:

1. Извлекает кадры через `FFmpeg`
2. Удаляет фон через `rembg` (Python API)
3. Приводит кадры к размеру в одном из 3 режимов ресайза
4. Собирает atlas (`PNG RGBA`) и экспортирует файл

## 2. Стек

- Python 3.9+
- PySide6
- Qt Multimedia (`QMediaPlayer`/`QVideoWidget`) для предпросмотра видео в UI
- FFmpeg/FFprobe
- rembg
- onnxruntime (через установку `rembg[cpu]`)
- Pillow

## 3. Структура модулей

- `src/models.py`:
  - `VideoMeta`, `ExtractionParams`, `BackgroundRemovalParams`, `AtlasParams`
  - `ExtractMode`, `ResizeMode`
- `src/app_state.py`:
  - runtime-состояние UI и путей `temp/`
- `src/services/video_service.py`:
  - метаданные (`ffprobe`)
  - извлечение кадров по FPS
  - извлечение ровно `N` кадров по равномерным timestamp от начала до конца таймлайна
- `src/services/background_service.py`:
  - batch-обработка кадров через `rembg.remove` без `alpha_matting` (`alpha_matting=False`)
  - включена постобработка маски `post_process_mask=True` для очистки краев
  - параметры `FG Threshold`, `BG Threshold`, `Erode Size` валидируются на уровне модели, но не участвуют в текущем режиме удаления фона
  - нормализация выхода в `RGBA PNG`
- `src/services/image_service.py`:
  - режимы `FIT`, `CROP_CENTER`, `STRETCH`
- `src/services/atlas_service.py`:
  - сборка atlas и проверка capacity
- `src/ui/workers.py`:
  - фоновые задачи (`QRunnable`) и прогресс
- `src/ui/main_window.py`:
  - layout, привязка кнопок, пайплайн действий, обработка ошибок
  - выбор `Frame Width/Frame Height` в блоке пайплайна перед `Extract Frames` с применением размера сразу после извлечения
  - единый выбор фона предпросмотра `Preview Background` (`Black/White/Green`) для статичного spritesheet и окна анимации
  - запуск отдельного окна предпросмотра анимации из готового spritesheet
- `src/ui/spritesheet_preview_dialog.py`:
  - покадровый предпросмотр анимации из `spritesheet.png` с `Play/Pause`, `Prev/Next` и выбором FPS
  - принимает и применяет фон из основного окна, чтобы цвет в обоих предпросмотрах совпадал

## 4. Временные директории

- `temp/frames/` — извлеченные кадры
- `temp/cut/` — кадры после удаления фона
- `temp/output/` — итоговый `spritesheet.png`
- `temp/preview/` — временный кадр для превью видео

При старте приложения временные PNG очищаются.

## 5. UI-сценарий

1. `Load Video` -> загрузка метаданных + превью
   - `Play` запускает нативный предпросмотр через `QMediaPlayer` в зацикленном режиме (после последнего кадра воспроизведение продолжается с начала)
2. Выбор режима извлечения:
   - `Target FPS`
   - `Exact Frame Count` (по умолчанию)
   - В режиме `Exact Frame Count` используется поле `Count`; в режиме `Target FPS` используется поле `FPS`
3. Выбор размера кадра перед извлечением:
   - `Frame Width`, `Frame Height` (фиксированный список: `16, 32, 64, 128, 256, 512, 1024`)
4. `Extract Frames`
   - после извлечения кадры сразу приводятся к выбранному `Frame Width/Frame Height`
5. Автопродолжение пайплайна после извлечения:
   - если `Auto remove background after extraction` выключен, сразу запускается `Build SpriteSheet`
   - если `Auto remove background after extraction` включен, сначала запускается `Remove Background`, затем автоматически запускается `Build SpriteSheet` на кадрах из `temp/cut`
6. (Опционально вручную) `Remove Background`
   - дополнительные параметры удаления фона (через ползунки):
     - `FG Threshold` (по умолчанию `240`)
     - `BG Threshold` (по умолчанию `10`)
     - `Erode Size` (по умолчанию `10`)
   - в текущем режиме сервис использует обычную маску без alpha matting и включает `post_process_mask` для очистки артефактов по краю
7. Ввод atlas-параметров (могут быть изменены перед ручным повторным запуском):
   - `Columns`, `Rows`, `Resize Mode`
   - `Frame Width` и `Frame Height` задаются в блоке извлечения и используются также для сборки atlas
8. `Build SpriteSheet` (кнопка доступна и для ручного повторного запуска)
9. `Video Preview` (опционально)
   - открывает отдельное окно и проигрывает кадры из готового spritesheet как анимацию
10. `Preview Background`
   - единый селектор фона предпросмотра: `Black`, `White`, `Green`
   - выбранный цвет сразу применяется к `SpriteSheet Preview` и к открытому окну `Video Preview`
11. `Export PNG`

## 6. Правила валидации

- Видео должно быть выбрано до извлечения
- `FPS > 0`
- `Count > 0`
- `Columns/Rows > 0`
- `FG Threshold` в диапазоне `0..255`
- `BG Threshold` в диапазоне `0..255`
- `Erode Size >= 0`
- `Frame Width` и `Frame Height` должны быть одним из значений списка: `16, 32, 64, 128, 256, 512, 1024`
- `len(frames) <= columns * rows`
- окно `Video Preview` доступно только после успешной сборки spritesheet

При нарушении условий показывается короткая ошибка, UI не падает.
Если кадров больше вместимости atlas, UI показывает точные значения (`кадров` и `вместимость`) и предлагает автоматически увеличить `Rows` до минимально необходимого значения.

Для `Exact Frame Count` приложение всегда формирует ровно `N` кадров.  
Кадры выбираются по равномерно распределенным индексам по всей длине видео (от первого до последнего кадра).  
Если запрошено кадров больше, чем реально есть в видео, показывается ошибка с предложением уменьшить `Exact Frame Count`.

## 7. Потоки и отзывчивость

Тяжелые шаги выполняются в фоне через `QThreadPool`:

- extraction
- background removal
- atlas build

Во время фоновой задачи кнопки действий блокируются, прогресс отображается в `QProgressBar`.
Дополнительно показывается отдельный бесконечный индикатор «Идет обработка...», чтобы пользователь видел активную работу даже до появления процентов.

Для стабильности фоновых задач `QRunnable` удерживаются сильными ссылками в `MainWindow` до завершения.  
Это предотвращает ошибки времени выполнения вида `QThreadStorage: entry ... destroyed before end of thread` на долгих шагах (например, `rembg`).
Подключение сигналов воркера выполняется как `QueuedConnection`, чтобы UI-обновления происходили строго в главном потоке.

## 8. Известные ограничения MVP

- Без trim диапазона (`start/end`)
- Без reorder кадров
- Без JSON metadata
- Без сохранения проекта
- Без упаковки в `.app`

## 9. Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m src.main
```

Если `rembg` был установлен без backend:

```bash
pip install "rembg[cpu]"
```

## 10. Тесты

```bash
pytest
```

Часть integration-тестов автоматически пропускается, если в среде отсутствуют `ffmpeg/ffprobe/rembg`.
