import os
from flask import Blueprint, send_from_directory

media_bp = Blueprint("media", __name__)

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets"))


@media_bp.route("/intro.wav")
def serve_intro():
    return send_from_directory(ASSETS_DIR, "intro.wav")


@media_bp.route("/wait-music.wav")
def serve_wait():
    return send_from_directory(ASSETS_DIR, "wait-music.wav")


@media_bp.route("/wait-music-<use_case_id>.wav")
def serve_wait_use_case(use_case_id):
    filename = f"wait-music-{use_case_id}.wav"
    if os.path.exists(os.path.join(ASSETS_DIR, filename)):
        return send_from_directory(ASSETS_DIR, filename)
    return send_from_directory(ASSETS_DIR, "wait-music.wav")
