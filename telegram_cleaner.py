#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Очищает HTML-экспорт личной переписки Telegram.

Использование:
    python telegram_cleaner.py "./telegram-export/messages.html"
    python telegram_cleaner.py "./telegram-export" -o "./output/chat.txt"
    python telegram_cleaner.py "./telegram-export" --no-sender

Если передана папка, скрипт объединяет messages.html, messages2.html,
messages3.html и т. д. в хронологическом порядке.
Используется только стандартная библиотека Python — ничего устанавливать не нужно.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S GMT%z",
    "%d.%m.%Y %H:%M:%S %Z%z",
)

MEDIA_LABELS = {
    "photo": "Фото",
    "video file": "Видео",
    "video message": "Видеосообщение",
    "voice message": "Голосовое сообщение",
    "sticker": "Стикер",
    "animation": "Анимация",
    "audio file": "Аудиофайл",
}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: list

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)


class TelegramHTMLParser(HTMLParser):
    """Мини-DOM на стандартной библиотеке: хватает для HTML-экспорта Telegram."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag.lower(), dict(attrs), [])
        self.stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag.lower(), dict(attrs), []))

    def handle_endtag(self, tag):
        tag = tag.lower()
        # Закрываем стек до ближайшего соответствующего открытого тега.
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def walk(node: Node):
    for child in node.children:
        if isinstance(child, Node):
            yield child
            yield from walk(child)


def find_first(node: Node, *, tag: Optional[str] = None,
               cls: Optional[str] = None, skip_cls: Optional[str] = None):
    for child in node.children:
        if not isinstance(child, Node):
            continue
        if skip_cls and child.has_class(skip_cls):
            continue
        if (tag is None or child.tag == tag) and (cls is None or child.has_class(cls)):
            return child
        found = find_first(child, tag=tag, cls=cls, skip_cls=skip_cls)
        if found is not None:
            return found
    return None


def find_all(node: Node, *, tag: Optional[str] = None,
             cls: Optional[str] = None, skip_cls: Optional[str] = None):
    result = []
    for child in node.children:
        if not isinstance(child, Node):
            continue
        if skip_cls and child.has_class(skip_cls):
            continue
        if (tag is None or child.tag == tag) and (cls is None or child.has_class(cls)):
            result.append(child)
        result.extend(find_all(child, tag=tag, cls=cls, skip_cls=skip_cls))
    return result


def direct_child(node: Node, *, tag: Optional[str] = None, cls: Optional[str] = None):
    for child in node.children:
        if not isinstance(child, Node):
            continue
        if (tag is None or child.tag == tag) and (cls is None or child.has_class(cls)):
            return child
    return None


def render_text(node: Node, *, skip_classes: tuple[str, ...] = ()) -> str:
    """Извлекает текст, сохраняя переносы и видимые ссылки."""
    parts = []

    def visit(item):
        if isinstance(item, str):
            parts.append(item)
            return

        if any(item.has_class(c) for c in skip_classes):
            return
        if item.tag in {"script", "style", "noscript"}:
            return
        if item.tag == "br":
            parts.append("\n")
            return
        if item.tag == "a":
            label = "".join(render_child(x) for x in item.children)
            href = item.attr("href").strip()
            if href and href != label.strip():
                parts.append(f"{label} ({href})")
            else:
                parts.append(label)
            return

        for child in item.children:
            visit(child)

    def render_child(item):
        if isinstance(item, str):
            return item
        if item.tag == "br":
            return "\n"
        if item.tag in {"script", "style", "noscript"}:
            return ""
        return "".join(render_child(x) for x in item.children)

    visit(node)
    return clean_text("".join(parts))


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ").replace("\u200b", "")
    lines = []
    for raw_line in value.splitlines():
        line = re.sub(r"[ \t\f\v]+", " ", raw_line).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
        else:
            lines.append(line)

    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()

    # Не допускаем длинных пустых промежутков, но сохраняем абзацы.
    compact = []
    for line in lines:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    return "\n".join(compact)


def parse_date(value: str) -> Optional[datetime]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def display_date(value: str) -> str:
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime("%d.%m.%Y %H:%M:%S")
    return value.strip()


def media_description(media_node: Node) -> str:
    title_node = find_first(media_node, cls="title")
    title = render_text(title_node) if title_node else ""
    status_node = find_first(media_node, cls="status")
    status = render_text(status_node) if status_node else ""

    key = title.lower().strip()
    label = MEDIA_LABELS.get(key)

    if label is None:
        # В Telegram имя документа часто записано прямо в title.
        if title:
            label = f"Файл: {title}"
        else:
            classes = media_node.attr("class")
            if "media_photo" in classes:
                label = "Фото"
            elif "media_video" in classes:
                label = "Видео"
            elif "media_voice_message" in classes:
                label = "Голосовое сообщение"
            elif "media_file" in classes:
                label = "Файл"
            else:
                label = "Вложение"

    # Длительность полезна для видео/голосовых, размер файла — нет.
    duration = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", status)
    if duration and label in {"Видео", "Видеосообщение", "Голосовое сообщение"}:
        return f"[{label}, {duration.group(0)}]"
    return f"[{label}]"


def extract_media(container: Node) -> list[str]:
    media_nodes = find_all(container, cls="media")
    if media_nodes:
        return [media_description(node) for node in media_nodes]

    # Запасной вариант для изменившейся разметки Telegram.
    wraps = find_all(container, cls="media_wrap")
    return ["[Вложение]"] * len(wraps)


@dataclass
class Message:
    dt: Optional[datetime]
    date_text: str
    sender: str
    content: str
    sequence: int


def parse_html_file(path: Path, start_sequence: int) -> list[Message]:
    parser = TelegramHTMLParser()
    parser.feed(path.read_text(encoding="utf-8-sig", errors="replace"))
    parser.close()

    message_nodes = [
        node for node in walk(parser.root)
        if node.tag == "div" and node.has_class("message")
    ]

    result = []
    sequence = start_sequence

    for message in message_nodes:
        body = direct_child(message, tag="div", cls="body")
        if body is None:
            continue

        # Даты-разделители Telegram не являются сообщениями.
        if message.has_class("service"):
            continue

        date_node = find_first(body, cls="date", skip_cls="forwarded")
        raw_date = date_node.attr("title") if date_node else ""
        dt = parse_date(raw_date)
        date_text = display_date(raw_date) if raw_date else "дата неизвестна"

        sender_node = find_first(body, cls="from_name", skip_cls="forwarded")
        sender = render_text(sender_node) if sender_node else ""

        # Текст именно текущего сообщения, не вложенный текст пересланного поста.
        text_node = find_first(body, cls="text", skip_cls="forwarded")
        text = render_text(text_node) if text_node else ""

        # В Telegram класс "forwarded" есть и у аватарки пересланного автора.
        # Нам нужен именно контейнер "forwarded body", а не userpic_wrap.
        forwarded_node = next(
            (
                node for node in walk(body)
                if node.tag == "div"
                and node.has_class("forwarded")
                and node.has_class("body")
            ),
            None,
        )
        forwarded_prefix = ""
        forwarded_text = ""
        forwarded_media = []

        if forwarded_node:
            original_sender_node = find_first(forwarded_node, cls="from_name")
            original_date_node = find_first(forwarded_node, cls="date")
            original_sender = ""
            original_date = ""

            if original_sender_node:
                original_sender = render_text(original_sender_node, skip_classes=("date",))
            if original_date_node:
                original_date = display_date(original_date_node.attr("title"))

            origin_parts = [x for x in (original_sender, original_date) if x]
            if origin_parts:
                forwarded_prefix = "[Переслано: " + ", ".join(origin_parts) + "]"

            if not text:
                forwarded_text_node = find_first(forwarded_node, cls="text")
                if forwarded_text_node:
                    forwarded_text = render_text(forwarded_text_node)
                forwarded_media = extract_media(forwarded_node)

        # Сохраняем ссылку на сообщение, на которое отвечали: это почти не
        # увеличивает объём, но помогает ИИ восстановить контекст диалога.
        reply_marker = ""
        reply_node = find_first(body, cls="reply_to", skip_cls="forwarded")
        if reply_node:
            reply_link = find_first(reply_node, tag="a")
            reply_href = reply_link.attr("href") if reply_link else ""
            reply_match = re.search(r"go_to_message(\d+)", reply_href)
            if reply_match:
                reply_marker = f"[Ответ на сообщение #{reply_match.group(1)}]"
            else:
                reply_marker = "[Ответ на сообщение]"

        # Вложения текущего сообщения. Если это пересланное медиа без отдельного
        # вложения у текущего сообщения — берём описание из пересланного блока.
        media = extract_media(body)
        if not media and forwarded_media:
            media = forwarded_media

        content_parts = []
        if reply_marker:
            content_parts.append(reply_marker)
        if forwarded_prefix:
            content_parts.append(forwarded_prefix)
        if text:
            content_parts.append(text)
        elif forwarded_text:
            content_parts.append(forwarded_text)
        content_parts.extend(media)

        content = "\n".join(part for part in content_parts if part).strip()
        if not content:
            continue

        result.append(Message(
            dt=dt,
            date_text=date_text,
            sender=sender,
            content=content,
            sequence=sequence,
        ))
        sequence += 1

    return result


def messages_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]

    if not input_path.is_dir():
        raise FileNotFoundError(f"Не найден файл или папка: {input_path}")

    candidates = []
    for path in input_path.glob("messages*.html"):
        # Берём стандартные страницы экспорта: messages.html, messages2.html...
        if re.fullmatch(r"messages\d*\.html", path.name, flags=re.IGNORECASE):
            candidates.append(path)

    def sort_key(path: Path):
        match = re.fullmatch(r"messages(\d*)\.html", path.name, flags=re.IGNORECASE)
        number = int(match.group(1) or "1")
        return number

    return sorted(candidates, key=sort_key)


def format_messages(messages: list[Message], include_sender: bool = True) -> str:
    # Даты надёжнее номера страницы; sequence сохраняет порядок при одинаковом времени.
    messages.sort(key=lambda item: (
        item.dt is None,
        item.dt.timestamp() if item.dt is not None else 0,
        item.sequence,
    ))

    output = []
    last_sender = ""

    for message in messages:
        if message.sender:
            last_sender = message.sender
        sender = message.sender or last_sender or "Неизвестный отправитель"

        if include_sender:
            header = f"[{message.date_text}] {sender}:"
        else:
            header = f"[{message.date_text}]"

        output.append(header + "\n" + message.content)

    return "\n\n".join(output).rstrip() + ("\n" if output else "")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Очищает HTML-экспорт Telegram до текста с датами и авторами."
    )
    ap.add_argument("input", help="HTML-файл или папка с messages*.html")
    ap.add_argument(
        "-o", "--output",
        help="Путь к итоговому TXT (по умолчанию telegram_clean.txt рядом с экспортом)",
    )
    ap.add_argument(
        "--no-sender",
        action="store_true",
        help="Не записывать имя отправителя (оставить только дату и текст).",
    )
    args = ap.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    files = messages_files(input_path)
    if not files:
        raise SystemExit(
            "Не найдены HTML-файлы messages.html, messages2.html и т. п."
        )

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (input_path.parent if input_path.is_file() else input_path) / "telegram_clean.txt"
    )

    all_messages = []
    sequence = 0
    total_input_bytes = 0

    for html_file in files:
        total_input_bytes += html_file.stat().st_size
        parsed = parse_html_file(html_file, sequence)
        all_messages.extend(parsed)
        sequence += len(parsed)
        print(f"Обработан: {html_file.name} — сообщений: {len(parsed):,}")

    result = format_messages(all_messages, include_sender=not args.no_sender)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")

    output_bytes = output_path.stat().st_size
    reduction = (1 - output_bytes / total_input_bytes) * 100 if total_input_bytes else 0

    print("\nГотово.")
    print(f"HTML-файлов:       {len(files):,}")
    print(f"Сообщений:         {len(all_messages):,}")
    print(f"Размер исходников: {total_input_bytes:,} байт")
    print(f"Размер TXT:        {output_bytes:,} байт")
    print(f"Сокращение размера: {reduction:.1f}%")
    print(f"Результат:         {output_path}")
    print("\nПримечание: размер файла не равен числу токенов. Точное число зависит от токенизатора модели.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
