from mutagen.mp4 import MP4


def retag_smule_audio(file_path: str, extract: dict) -> None:
    perf = extract.get("perf") or {}
    title = (perf.get("title") or "").strip() or "Smule"
    artist = (perf.get("artist") or "").strip() or "Smule"

    audio = MP4(file_path)
    audio.clear()
    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [artist]
    audio["aART"] = [artist]
    audio["\xa9alb"] = ["Smule"]
    audio.save()