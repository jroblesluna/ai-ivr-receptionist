from flask import Blueprint, redirect
from storage import storage

media_bp = Blueprint("media", __name__)


@media_bp.route("/intro.wav")
def serve_intro():
    url = storage.get_audio_url("assets/intro.wav")
    return redirect(url)


@media_bp.route("/wait-music.wav")
def serve_wait():
    url = storage.get_audio_url("assets/wait-music.wav")
    return redirect(url)


@media_bp.route("/wait-music-<use_case_id>.wav")
def serve_wait_use_case(use_case_id):
    filename = f"wait-music-{use_case_id}.wav"
    url = storage.get_audio_url(f"assets/{filename}")
    return redirect(url)
