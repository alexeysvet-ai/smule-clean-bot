# === smule_media_flow.py ===
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.media import send_media_with_retry
from bot_core.utils import log
from config import BOT_CODE, TOKEN, ALERT_CHANNEL_ID
from smule_download import pick_smule_media, build_smule_title, build_final_path
from smule_flow import insert_event_safe
from smule_tags import retag_smule_audio
from texts import TEXTS
from bot_i18n import t


def resolve_available_media(extract: dict) -> dict:
    audio_mode, audio_url = pick_smule_media(extract, preferred_mode="audio")
    video_mode, video_url = pick_smule_media(extract, preferred_mode="video")

    return {
        "audio_mode": audio_mode,
        "audio_url": audio_url,
        "video_mode": video_mode,
        "video_url": video_url,
        "has_audio": bool(audio_mode and audio_url),
        "has_video": bool(video_mode and video_url),
    }


def has_any_media(extract: dict) -> bool:
    media = resolve_available_media(extract)
    return media["has_audio"] or media["has_video"]


async def handle_no_media(user_id: int, url: str, message_target) -> None:
    insert_event_safe(
        BOT_CODE,
        user_id,
        "media_url_not_found",
        status="fail"
    )

    await message_target.answer(t("no_media", user_id))

    try:
        alert_text = build_download_fail_alert(
            BOT_CODE,
            user_id,
            url,
            "no_media",
            "media_url_not_found"
        )
        await send_alert(TOKEN, ALERT_CHANNEL_ID, alert_text)
    except Exception as e:
        log(f"[ALERT ERROR] bot_code={BOT_CODE} user_id={user_id} error={e}")


async def handle_audio_download(
    *,
    message_target,
    callback_for_send,
    user_id: int,
    url: str,
    extract: dict,
    download_func,
) -> tuple[str, int]:
    selected_mode, media_url = pick_smule_media(extract, preferred_mode="audio")
    if not selected_mode or not media_url:
        raise RuntimeError("Audio media URL not found")

    await message_target.answer(t("status_audio", user_id))

    insert_event_safe(
        BOT_CODE,
        user_id,
        "download_started",
        status="success"
    )

    temp_path = await download_func(
        extract,
        media_url,
        selected_mode
    )
    title = build_smule_title(extract)
    file_path = build_final_path(temp_path, title, selected_mode)

    if not file_path:
        raise RuntimeError("File not created")

    retag_smule_audio(file_path, extract)

    import os
    if not os.path.exists(file_path):
        raise RuntimeError("File not created")

    size = os.path.getsize(file_path)
    size_mb = round(size / (1024 * 1024), 2)

    result_text = t("file_info", user_id).format(
        ext="M4A",
        size=size_mb
    )

    final_caption = t("success", user_id) + "\n\n" + result_text
    await send_media_with_retry(
        callback=callback_for_send,
        user_id=user_id,
        file_path=file_path,
        mode="audio",
        title=title,
        uploader=(extract.get("perf") or {}).get("artist"),
        caption=final_caption,
        retry_text=t("send_retry", user_id)
    )

    insert_event_safe(
        BOT_CODE,
        user_id,
        "download_success",
        status="success",
        mode="audio",
        file_size_bytes=size
    )

    return file_path, size


async def handle_video_download(
    *,
    message_target,
    callback_for_send,
    user_id: int,
    url: str,
    extract: dict,
    download_func,
) -> tuple[str, int]:
    selected_mode, media_url = pick_smule_media(extract, preferred_mode="video")
    if not selected_mode or not media_url:
        raise RuntimeError("Video media URL not found")

    await message_target.answer(t("status_video", user_id))

    insert_event_safe(
        BOT_CODE,
        user_id,
        "download_started",
        status="success"
    )

    temp_path = await download_func(
        extract,
        media_url,
        selected_mode
    )
    title = build_smule_title(extract)
    file_path = build_final_path(temp_path, title, selected_mode)

    if not file_path:
        raise RuntimeError("File not created")

    import os
    if not os.path.exists(file_path):
        raise RuntimeError("File not created")

    size = os.path.getsize(file_path)
    size_mb = round(size / (1024 * 1024), 2)

    result_text = t("file_info", user_id).format(
        ext="MP4",
        size=size_mb
    )

    final_caption = t("success", user_id) + "\n\n" + result_text
    await send_media_with_retry(
        callback=callback_for_send,
        user_id=user_id,
        file_path=file_path,
        mode="video",
        title=title,
        uploader=(extract.get("perf") or {}).get("artist"),
        caption=final_caption,
        retry_text=t("send_retry", user_id)
    )

    insert_event_safe(
        BOT_CODE,
        user_id,
        "download_success",
        status="success",
        mode="video",
        file_size_bytes=size
    )

    return file_path, size