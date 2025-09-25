# Changelog

All notable changes to this project will be documented in this file.

## 0.0.7 - 2025-09-21
- Переработан формат prices.json: одна запись на предмет, добавлены поля price_lp0…price_lp4 и comment_lp0…comment_lp4, поддержка заметок и сохранение порядка в known_order.
- Обновлены db.py, GUI и worker: таблица цен показывает LP-колонки, поиск и оверлей используют новые поля.
- Добавлен скрипт миграции legacy-базы (scripts/migrate_prices_lp.py) и тесты для проверки конверсии.
- Обновлена документация (README, AGENTS) и примеры, отражающие обязательный запуск миграции.

## 0.0.6 - 2025-09-21
- Полностью убран Tesseract и любые вызовы OCR: воркер работает только через шаблоны и сразу предлагает снять новый образец.
- Обновлены GUI, документация и скрипты установки — больше нет полей и инструкций для Tesseract.
- Упростён модуль `ocr.py`: оставлены только функции захвата экрана и поиска рамки по шаблонам.
- requirements.txt очищен от `pytesseract`, а README/FAQ переведены на русский.

## 0.0.5 - 2025-09-21
- Улучшена подсветка оверлея: значения ЛП анализируются корректно, и строки с ценой выше 100 000 теперь окрашиваются в зелёный цвет.
- Сдвиг фона текста исправлен — плашки под строками выравниваются вплотную к глифам.
- Названия предметов больше не подсвечиваются красным, если в строке нет цены.
- Подсказки по инвентарю ограничены максимум тремя экземплярами одного предмета.

## 0.0.4 - 2025-09-21
- Added config-driven hotkeys and overlay lifetimes with default duration extended to four seconds.
- Redesigned overlay visuals with per-line highlights that colour-code values above or below 100 000.
- Updated the template capture selection to a frosted-glass overlay with blur while dragging.

## 0.0.3 - 2025-09-21
- Restored readable Cyrillic text in the Russian FAQ section.
- Added a workflow rule to enforce UTF-8 encoding for PowerShell file writes.

## 0.0.2 - 2025-09-21
- Prevent duplicate template dialogs by ensuring worker signals are connected only once.

## 0.0.1 - 2025-09-21
- Added bilingual FAQ (EN/RU) to the README.
- Documented workflow rules for Git usage, changelog maintenance, and version bumps in AGENTS.md.

