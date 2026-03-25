Проект: Youtube Easy Downloader (Telegram bot)

## Цель

Система скачивания видео/аудио (YouTube и др.) в условиях:

* блокировок
* нестабильных прокси
* ограничений Telegram

Основной принцип:
→ управляем нестабильной сетью, а не надеемся на неё

---

## Архитектура

* aiogram (Telegram bot)
* aiohttp webhook
* yt-dlp downloader
* proxy layer (rotation + blacklist + scoring)
* texts.py (UX + мультиязычность)

---

## Ключевые правила разработки

* файлы ≤ 100 строк
* изменения только целыми файлами
* никаких частичных правок
* UX только через texts.py
* обязательная мультиязычность (ru / en)
* async + background tasks (anti-duplicate webhook fix)

---

## Текущее состояние

* скачивание работает
* прокси перебираются (включая fallback)
* yt-dlp fallback форматов реализован
* добавлено имя файла (title → filename)
* добавлен вывод:
  формат / размер / битрейт
* есть fallback совместимость:
  download_video → (file_path, info) ИЛИ file_path

---

## Ограничения

* free прокси нестабильны
* успех зависит от качества proxy pool
* Telegram лимит ~50MB

---

## Логирование (обязательный стандарт)

Цель:
→ быстро понимать, где и почему ломается система

---

### Формат логов

[TIMESTAMP] [BUILD] [TYPE] user=ID message

---

### Обязательные типы логов

1. BUILD

[BUILD] 20260325-2130 started

---

2. REQUEST

[REQUEST] user=123 url=...

---

3. DOWNLOAD START

[DOWNLOAD START] user=123 mode=audio url=...

---

4. TRY (proxy attempt)

[TRY] user=123 attempt=3/65 proxy=...

---

5. PROXY USED

[PROXY USED] user=123 proxy=...

---

6. SUCCESS

[SUCCESS] user=123 proxy=... size=3.2MB time=6.2s

---

7. ERROR (на попытке)

[ERROR] user=123 proxy=... type=YOUTUBE error=...

---

8. FINAL ERROR

[FINAL ERROR] user=123 url=... reason=All attempts failed

---

9. FILE (результат)

[FILE] user=123 ext=mp3 size=3.2MB bitrate=192

---

10. TIME (метрики)

[TIME] user=123 total=8.4s download=6.2s proxy=2.2s

---

11. CLEANUP

[CLEANUP] user=123 file_deleted

---

## Классификация ошибок

Каждый ERROR должен иметь тип:

* NETWORK
* PROXY
* YOUTUBE
* TIMEOUT
* INTERNAL

---

## Где логировать

handlers.py:

* REQUEST
* DOWNLOAD START
* FILE
* TIME
* FINAL ERROR

downloader.py:

* TRY
* PROXY USED
* SUCCESS
* ERROR

main.py:

* BUILD

---

## Пример полного лога

[BUILD] 20260325-2130 started

[REQUEST] user=123 url=https://youtu.be/...
[DOWNLOAD START] user=123 mode=audio

[TRY] user=123 attempt=1/65 proxy=...
[ERROR] user=123 proxy=... type=YOUTUBE

[TRY] user=123 attempt=2/65 proxy=...
[SUCCESS] user=123 proxy=... size=3.2MB time=6.1s

[FILE] user=123 ext=mp3 size=3.2MB bitrate=192
[TIME] user=123 total=8.3s
[CLEANUP] user=123 file_deleted

---

## Инженерный вывод

Система успешна, если:

* видно каждый этап выполнения
* можно быстро локализовать проблему
* можно измерить success rate и время
* логирование не зависит от UI

→ логирование = часть архитектуры, а не отладка
