# ... (весь код без изменений до handle_quality)

@dp.callback_query(lambda c: c.data.startswith("q_"))
async def handle_quality(callback: types.CallbackQuery):
    user = callback.from_user
    user_id = user.id
    username = user.username

    url = user_requests.get(user_id)
    if not url:
        return

    log(f"[REQUEST][BUILD {BUILD_ID}] user={user_id} username={username} url={url}")

    mode = callback.data.replace("q_", "")

    metrics["total"] += 1

    await callback.message.edit_text(t("downloading", user_id))

    file_path = None

    try:
        file_path = await safe_download(url, mode)

        if not os.path.exists(file_path):
            raise RuntimeError("file not found")

        size = os.path.getsize(file_path)

        # 🔥 НОВАЯ ЛОГИКА
        if size > MAX_FILE_SIZE:
            metrics["fail"] += 1

            await callback.message.answer(
                "⚠️ Видео слишком большое для Telegram (>50MB)\n\n"
                "Это ограничение Telegram, а не бота.\n\n"
                f"Вот ссылка для скачивания 👇\n{url}"
            )
            return

        if mode == "audio":
            await callback.message.answer_audio(types.FSInputFile(file_path))
        else:
            await callback.message.answer_video(types.FSInputFile(file_path))

        metrics["success"] += 1

    except asyncio.TimeoutError:
        metrics["timeouts"] += 1
        await callback.message.answer(t("timeout", user_id))
    except Exception:
        metrics["fail"] += 1

        service = get_service(url)

        if service == "vk":
            await callback.message.answer(t("vk_error", user_id))
        elif service == "mail":
            await callback.message.answer(t("mail_error", user_id))
        else:
            await callback.message.answer(t("error", user_id))

    finally:
        if file_path:
            cleanup_file(file_path)

        log(f"[METRICS][BUILD {BUILD_ID}] total={metrics['total']} success={metrics['success']} fail={metrics['fail']} timeouts={metrics['timeouts']} rate={success_rate()}%")
