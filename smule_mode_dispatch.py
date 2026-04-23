async def run_smule_download_by_mode(
    *,
    mode: str,
    message_target,
    callback_for_send,
    user_id: int,
    url: str,
    extract: dict,
    download_func,
    handle_audio_download,
    handle_video_download,
):
    if mode == "audio":
        return await handle_audio_download(
            message_target=message_target,
            callback_for_send=callback_for_send,
            user_id=user_id,
            url=url,
            extract=extract,
            download_func=download_func,
        )

    return await handle_video_download(
        message_target=message_target,
        callback_for_send=callback_for_send,
        user_id=user_id,
        url=url,
        extract=extract,
        download_func=download_func,
    )