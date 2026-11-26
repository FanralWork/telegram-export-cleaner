# Telegram Export Cleaner

A command-line tool that converts Telegram Desktop HTML chat exports into UTF-8 text for offline reading and text processing.

## Features

- Processes a single HTML page or a folder of numbered `messages*.html` pages.
- Merges messages in chronological order when timestamps can be parsed.
- Preserves reply references and available forwarding details. Attachments are represented as text markers.
- Can omit the sender name from each message header.

## Stack and architecture

The tool uses the Python standard library. `telegram_cleaner.py` builds a small HTML tree with `HTMLParser`, extracts message records, and renders the combined plain-text output. No Telegram credentials or Python packages are needed.

## Setup and usage

Export a chat as HTML in Telegram Desktop. Run these commands with Python 3.10 or later.

```sh
python telegram_cleaner.py "./telegram-export"
python telegram_cleaner.py "./telegram-export/messages.html" -o "./output/chat.txt" --no-sender
```

The default output is `telegram_clean.txt` next to the export or inside the input folder. A file at the chosen output path is overwritten.

## Status and limitations

The parser depends on Telegram Desktop's export markup and loads each page into memory. It processes the HTML export format. Sender names can still appear in forwarded headers or message content when using `--no-sender`. Keep real exports and the resulting text private.

## Кратко для портфолио

Локальная утилита преобразует HTML-экспорт Telegram Desktop в хронологический текст с отметками ответов, пересылок и вложений. Использует стандартную библиотеку Python.
