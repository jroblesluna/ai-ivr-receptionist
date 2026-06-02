"""FastAPI WebSocket server for Twilio Media Streams.

Handles bidirectional audio streaming between Twilio and the real-time
voice pipeline. Receives inbound audio, routes it through STT and VAD,
and sends synthesized audio back to the caller.

Endpoints:
- GET /health — Health check for the async service
- WebSocket /media-stream — Twilio Media Streams connection
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.realtime.end_of_call import process_end_of_call
from src.realtime.error_recovery import (
    PipelineHealthMonitor,
    handle_llm_failure,
    handle_stt_failure,
)
from src.realtime.llm import LLMStreamClient
from src.realtime.models import (
    PipelineState,
    decode_media_payload,
    encode_audio_for_twilio,
    parse_start_event,
)
from src.realtime.session import ConversationSession, handle_barge_in, unregister_session
from src.realtime.store_integration import save_conversation_history
from src.realtime.vad import VADEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Timeout for detecting unexpected WebSocket disconnections (seconds)
DISCONNECT_TIMEOUT_SECONDS = 5.0

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(title="PickUp Real-Time Voice Server", version="1.0.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for the real-time voice service."""
    return {"status": "ok"}


@app.websocket("/media-stream")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Handle a single Twilio Media Stream WebSocket connection.

    Processes the Twilio WebSocket protocol events:
    - connected: Twilio confirms the WebSocket is established
    - start: Contains call metadata and custom parameters; initializes session
    - media: Contains base64-encoded audio; forwarded to STT and VAD
    - stop: Twilio signals the stream is ending; triggers cleanup

    A 5-second timeout is used on ws.receive_text() to detect unexpected
    disconnections when Twilio stops sending data without a proper close.
    """
    await ws.accept()
    logger.info("WebSocket connection accepted")

    session: ConversationSession | None = None
    health_monitor: PipelineHealthMonitor | None = None
    pipeline_failure_event = asyncio.Event()

    try:
        while True:
            # Check if pipeline health monitor detected a full failure
            if pipeline_failure_event.is_set():
                logger.warning(
                    "Pipeline failure event set, closing WebSocket",
                    extra={
                        "stream_sid": session.stream_sid if session else "unknown",
                    },
                )
                break

            try:
                # 5-second timeout to detect unexpected disconnections
                raw_message = await asyncio.wait_for(
                    ws.receive_text(),
                    timeout=DISCONNECT_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "WebSocket disconnect detected (no data for %ss)",
                    DISCONNECT_TIMEOUT_SECONDS,
                    extra={
                        "stream_sid": session.stream_sid if session else "unknown",
                    },
                )
                break

            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON WebSocket message, ignoring")
                continue

            event = msg.get("event")

            if event == "connected":
                logger.info(
                    "Twilio Media Stream connected",
                    extra={
                        "protocol": msg.get("protocol"),
                        "version": msg.get("version"),
                    },
                )

            elif event == "start":
                session = await _handle_start_event(msg, ws)
                # Start pipeline health monitor
                health_monitor = PipelineHealthMonitor(session)
                await health_monitor.start_monitoring(pipeline_failure_event)

            elif event == "media":
                if session is not None:
                    should_close = await _handle_media_event(msg, session, ws)

                    # STT recovery failed — close WebSocket for fallback
                    if should_close:
                        logger.warning(
                            "Media handler signaled close (STT recovery failed)",
                            extra={"stream_sid": session.stream_sid},
                        )
                        break

                    # Record successful processing for health monitor
                    if health_monitor is not None:
                        health_monitor.record_success()

                    # Check if end_call was signaled after processing
                    if session.state.collected_info.get("_end_call"):
                        logger.info(
                            "End call signaled, closing WebSocket after final audio",
                            extra={"stream_sid": session.stream_sid},
                        )
                        # Wait briefly for any remaining audio to be sent
                        await asyncio.sleep(0.5)
                        break

            elif event == "stop":
                logger.info(
                    "Twilio Media Stream stop event received",
                    extra={
                        "stream_sid": msg.get("streamSid", "unknown"),
                    },
                )
                break

            else:
                logger.debug(
                    "Unhandled WebSocket event: %s",
                    event,
                )

    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected",
            extra={
                "stream_sid": session.stream_sid if session else "unknown",
            },
        )

    except Exception as exc:
        logger.error(
            "Unexpected error in WebSocket handler",
            extra={
                "error": str(exc),
                "stream_sid": session.stream_sid if session else "unknown",
            },
        )

    finally:
        # Stop health monitor
        if health_monitor is not None:
            await health_monitor.stop()

        # End-of-call processing
        if session is not None:
            end_call_signaled = session.state.collected_info.get("_end_call", False)
            unexpected_disconnect = not end_call_signaled

            # Process end of call (report + notifications)
            try:
                process_end_of_call(
                    call_sid=session.call_sid,
                    demo_id=session.demo_id,
                    language=session.language,
                    caller_from=session.caller_from,
                    conversation_history=list(session.state.conversation_history),
                    collected_info=dict(session.state.collected_info),
                    incomplete=unexpected_disconnect,
                )
            except Exception as exc:
                logger.error(
                    "End-of-call processing error",
                    extra={
                        "call_sid": session.call_sid,
                        "error": str(exc),
                    },
                )

            # Cleanup session resources
            await session.cleanup()
            logger.info(
                "Session cleaned up after WebSocket close",
                extra={
                    "call_sid": session.call_sid,
                    "stream_sid": session.stream_sid,
                    "end_call_signaled": end_call_signaled,
                    "unexpected_disconnect": unexpected_disconnect,
                },
            )

        # Close WebSocket if still open
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------


async def _handle_start_event(
    msg: dict,
    ws: WebSocket,
) -> ConversationSession:
    """Handle a Twilio 'start' event: extract parameters and initialize session.

    Parses the start message to extract call_sid, stream_sid, and custom
    parameters (lang, demo_id, caller_from). Creates and initializes a
    ConversationSession with all pipeline components. Then triggers the
    opening greeting via LLM → TTS → Twilio.

    Args:
        msg: The parsed Twilio start event message.
        ws: The WebSocket connection for outbound audio.

    Returns:
        The initialized ConversationSession.
    """
    # Parse session state from the start event
    state = parse_start_event(msg)

    logger.info(
        "Handling start event",
        extra={
            "call_sid": state.call_sid,
            "stream_sid": state.stream_sid,
            "language": state.language,
            "demo_id": state.demo_id,
            "caller_from": state.caller_from,
        },
    )

    # Create the conversation session
    session = ConversationSession(
        call_sid=state.call_sid,
        stream_sid=state.stream_sid,
        language=state.language,
        demo_id=state.demo_id,
        caller_from=state.caller_from,
        voice_id=state.voice_id,
    )

    # Initialize all pipeline components (STT, TTS, VAD, playback tracker)
    await session.initialize()

    # Register the STT transcript callback
    if session.stt_client is not None:
        session.stt_client.on_transcript(
            lambda transcript, is_final: _on_transcript(session, ws, transcript, is_final)
        )

    logger.info(
        "ConversationSession initialized",
        extra={
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
        },
    )

    # Trigger opening greeting in background
    greeting_task = asyncio.create_task(
        _trigger_opening_greeting(session, ws)
    )
    session.add_pipeline_task(greeting_task)

    return session


async def _handle_media_event(
    msg: dict,
    session: ConversationSession,
    ws: WebSocket,
) -> bool:
    """Handle a Twilio 'media' event: decode audio and forward to STT and VAD.

    Decodes the base64 audio payload and concurrently sends it to:
    - STT client (send_audio) for transcription
    - VAD processor (process_frame) for voice activity detection

    Also checks VAD result for barge-in handling when in SPEAKING state.

    Args:
        msg: The parsed Twilio media event message.
        session: The active ConversationSession for this call.
        ws: The WebSocket connection for sending clear messages on barge-in.

    Returns:
        True if the WebSocket should be closed (STT recovery failed), False otherwise.
    """
    # Decode base64 audio payload
    try:
        audio_bytes = decode_media_payload(msg)
    except Exception as exc:
        logger.warning(
            "Failed to decode media payload",
            extra={
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )
        return False

    # Update activity timestamp
    session.update_activity()

    # Forward audio to STT
    if session.stt_client is not None:
        try:
            await session.stt_client.send_audio(audio_bytes)
        except Exception as exc:
            logger.warning(
                "Error forwarding audio to STT, attempting recovery",
                extra={
                    "stream_sid": session.stream_sid,
                    "error": str(exc),
                },
            )
            # Attempt STT recovery (reconnect within 2s, max 2 attempts)
            recovered = await handle_stt_failure(session, ws)
            if not recovered:
                # Fallback triggered — signal the WebSocket loop to close
                # The session's conversation history has been preserved in Redis
                return True

    # Forward audio to VAD and check for barge-in
    if session.vad_processor is not None:
        try:
            vad_event = session.vad_processor.process_frame(audio_bytes)

            if vad_event == VADEvent.SPEECH_START:
                # Barge-in: caller started speaking during SPEAKING state
                if session.pipeline_state == PipelineState.SPEAKING:
                    await _handle_barge_in(session, ws)

        except Exception as exc:
            logger.warning(
                "Error processing audio in VAD",
                extra={
                    "stream_sid": session.stream_sid,
                    "error": str(exc),
                },
            )

    return False


# ---------------------------------------------------------------------------
# Pipeline Orchestration
# ---------------------------------------------------------------------------


async def _on_transcript(
    session: ConversationSession,
    ws: WebSocket,
    transcript: str,
    is_final: bool,
) -> None:
    """Callback invoked by STT when a transcript result arrives.

    For interim results, updates the partial transcript buffer.
    For final results, triggers the LLM → TTS → Twilio pipeline.

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection for outbound audio.
        transcript: The transcribed text.
        is_final: Whether this is a final transcript result.
    """
    if not transcript or not transcript.strip():
        return

    if not is_final:
        # Buffer interim transcript
        session.state.partial_transcript = transcript
        return

    # Final transcript received — trigger LLM generation
    logger.info(
        "Final transcript received",
        extra={
            "stream_sid": session.stream_sid,
            "transcript": transcript,
            "pipeline_state": session.pipeline_state.value,
        },
    )

    # Clear partial transcript
    session.state.partial_transcript = ""

    # Add user message to conversation history
    session.state.conversation_history.append({
        "role": "user",
        "content": transcript,
    })

    # Transition to PROCESSING state
    session.pipeline_state = PipelineState.PROCESSING

    # Cancel any existing generation task
    if session.current_generation_task and not session.current_generation_task.done():
        session.current_generation_task.cancel()

    # Start LLM → TTS → Twilio pipeline in background
    task = asyncio.create_task(
        _generate_and_speak(session, ws)
    )
    session.current_generation_task = task
    session.add_pipeline_task(task)


async def _generate_and_speak(
    session: ConversationSession,
    ws: WebSocket,
) -> None:
    """Run the LLM → TTS → Twilio pipeline for a single turn.

    Generates a response via LLM streaming, forwards sentence chunks to TTS,
    and streams the resulting audio to Twilio. Manages state transitions
    from PROCESSING → SPEAKING → LISTENING.

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection for outbound audio.
    """
    cancel_event = asyncio.Event()
    llm_client = LLMStreamClient()
    accumulated_text = ""
    first_audio_sent = False

    # Build messages for LLM
    messages = list(session.state.conversation_history)

    async def on_sentence_chunk(chunk: str) -> None:
        """Forward a sentence chunk to TTS and stream audio to Twilio."""
        nonlocal accumulated_text, first_audio_sent

        if cancel_event.is_set():
            return

        accumulated_text += chunk

        # Synthesize via TTS and stream to Twilio
        if session.tts_client is not None:
            await session.tts_client.synthesize_stream(
                text=chunk,
                voice_id=session.voice_id or session.state.voice_id,
                on_audio_chunk=lambda audio_chunk: _send_audio_to_twilio(
                    session, ws, audio_chunk, chunk
                ),
            )

            # Transition to SPEAKING on first audio sent
            if not first_audio_sent:
                first_audio_sent = True
                session.pipeline_state = PipelineState.SPEAKING

    async def on_complete(parsed_response: dict) -> None:
        """Handle LLM response completion — update conversation history and check end_call."""
        nonlocal cancel_event

        message_text = parsed_response.get("message", "")

        # Add assistant message to conversation history
        if message_text:
            session.state.conversation_history.append({
                "role": "assistant",
                "content": message_text,
            })

        # Update collected info from LLM response
        name = parsed_response.get("name")
        phone = parsed_response.get("phone")
        notes = parsed_response.get("notes")
        if name:
            session.state.collected_info["name"] = name
        if phone:
            session.state.collected_info["phone"] = phone
        if notes:
            session.state.collected_info["notes"] = notes

        # Store goodbye message if end_call
        end_call = parsed_response.get("end_call", False)
        if end_call and message_text:
            session.state.collected_info["goodbye"] = message_text

        # Persist conversation history
        save_conversation_history(
            session.call_sid,
            session.state.conversation_history,
        )

        # Transition back to LISTENING after speaking completes
        if session.pipeline_state == PipelineState.SPEAKING:
            session.pipeline_state = PipelineState.LISTENING

        # Reset playback tracker for next turn
        if session.playback_tracker is not None:
            session.playback_tracker.clear()

        # Reset VAD state for next turn
        if session.vad_processor is not None:
            session.vad_processor.reset()

        # Handle end_call: allow final TTS audio to finish, then signal close
        if end_call:
            logger.info(
                "LLM returned end_call=true, signaling session end",
                extra={"call_sid": session.call_sid, "stream_sid": session.stream_sid},
            )
            # Mark session for end-of-call processing
            session.state.collected_info["_end_call"] = True

    try:
        await llm_client.generate_response(
            messages=messages,
            on_sentence_chunk=on_sentence_chunk,
            on_complete=on_complete,
            cancel_event=cancel_event,
        )

        # If we never sent audio (empty response), go back to LISTENING
        if not first_audio_sent and session.pipeline_state == PipelineState.PROCESSING:
            session.pipeline_state = PipelineState.LISTENING

    except asyncio.CancelledError:
        logger.info(
            "Generation task cancelled (barge-in)",
            extra={"stream_sid": session.stream_sid},
        )
        # Save partial response if we had accumulated text
        if accumulated_text:
            session.state.conversation_history.append({
                "role": "assistant",
                "content": accumulated_text,
                "interrupted": True,
            })
            session.state.interrupted_text = accumulated_text

    except Exception as exc:
        logger.error(
            "Error in generate_and_speak pipeline",
            extra={
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )
        # Attempt LLM failure recovery: speak apology, retry once
        recovered = await handle_llm_failure(
            session=session,
            ws=ws,
            messages=messages,
            on_sentence_chunk=on_sentence_chunk,
            on_complete=on_complete,
            cancel_event=cancel_event,
        )
        if not recovered:
            # Retry also failed — stream will be closed by the caller
            logger.error(
                "LLM recovery failed, stream will close",
                extra={"stream_sid": session.stream_sid},
            )
        # Transition back to LISTENING on error
        if session.pipeline_state in (PipelineState.PROCESSING, PipelineState.SPEAKING):
            session.pipeline_state = PipelineState.LISTENING


async def _send_audio_to_twilio(
    session: ConversationSession,
    ws: WebSocket,
    audio_chunk: bytes,
    text_segment: str,
) -> None:
    """Encode audio and send it to Twilio via WebSocket.

    Also records the chunk in the playback tracker for interruption handling.

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection.
        audio_chunk: Raw mulaw audio bytes from TTS.
        text_segment: The text that this audio represents.
    """
    try:
        # Encode audio for Twilio
        media_message = encode_audio_for_twilio(audio_chunk, session.stream_sid)

        # Send via WebSocket
        await ws.send_json(media_message)

        # Track in playback tracker
        if session.playback_tracker is not None:
            chunk_id = f"chunk_{session.state.turn_count}_{id(audio_chunk)}"
            session.playback_tracker.record_chunk_sent(chunk_id, text_segment)

    except Exception as exc:
        logger.warning(
            "Error sending audio to Twilio",
            extra={
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )


# ---------------------------------------------------------------------------
# Barge-In Handling
# ---------------------------------------------------------------------------


async def _handle_barge_in(
    session: ConversationSession,
    ws: WebSocket,
) -> None:
    """Handle a barge-in event: cancel generation, clear buffers, notify Twilio.

    When the caller starts speaking during SPEAKING state:
    1. Get partial text from playback tracker before clearing
    2. Call handle_barge_in() to transition state, clear tracker, cancel task
    3. Send clear message to Twilio to flush audio buffer
    4. Save partial response to conversation history with interrupted marker
    5. Transition to LISTENING

    Args:
        session: The active ConversationSession in SPEAKING state.
        ws: The WebSocket connection for sending the clear message.
    """
    logger.info(
        "Barge-in detected",
        extra={
            "stream_sid": session.stream_sid,
            "pipeline_state": session.pipeline_state.value,
        },
    )

    # Get partial text before clearing
    partial_text = ""
    if session.playback_tracker is not None:
        partial_text = session.playback_tracker.get_partial_text_at_interruption()

    # Use handle_barge_in from session.py (transitions to INTERRUPTED, clears tracker, cancels task)
    clear_msg = handle_barge_in(session, session.stream_sid)

    # Send clear message to Twilio to flush audio buffer
    try:
        await ws.send_json(clear_msg)
    except Exception as exc:
        logger.warning(
            "Error sending clear message to Twilio",
            extra={
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )

    # Save partial response to conversation history with interrupted marker
    if partial_text:
        session.state.conversation_history.append({
            "role": "assistant",
            "content": partial_text,
            "interrupted": True,
        })
        session.state.interrupted_text = partial_text

    # Transition from INTERRUPTED to LISTENING
    session.pipeline_state = PipelineState.LISTENING

    # Reset VAD for next turn
    if session.vad_processor is not None:
        session.vad_processor.reset()

    logger.info(
        "Barge-in handled, back to LISTENING",
        extra={
            "stream_sid": session.stream_sid,
            "partial_text_length": len(partial_text),
        },
    )


# ---------------------------------------------------------------------------
# Opening Greeting
# ---------------------------------------------------------------------------


async def _trigger_opening_greeting(
    session: ConversationSession,
    ws: WebSocket,
) -> None:
    """Generate and speak the opening greeting when a session starts.

    Sends "(start conversation)" as the user message to trigger the LLM
    greeting, synthesizes it via TTS, and streams audio to the caller.

    Args:
        session: The newly initialized ConversationSession.
        ws: The WebSocket connection for outbound audio.
    """
    logger.info(
        "Triggering opening greeting",
        extra={
            "stream_sid": session.stream_sid,
            "call_sid": session.call_sid,
        },
    )

    # Load system prompt for this demo use case
    try:
        import sys as _sys
        if "/app/src" not in _sys.path:
            _sys.path.insert(0, "/app/src")
        import db
        from prompts import get_conversational_prompt

        demo_uc = db.uc_get(session.demo_id) if session.demo_id else None
        caller_profile = db.caller_profile_get(session.caller_from, session.demo_id) if session.demo_id and session.caller_from else {}

        # Load voice_id from demo UC if configured
        if demo_uc and demo_uc.get("elevenlabs_voice_id"):
            session.voice_id = demo_uc["elevenlabs_voice_id"]
            session.state.voice_id = demo_uc["elevenlabs_voice_id"]

        if demo_uc:
            system_prompt = get_conversational_prompt(
                session.language, demo_uc,
                caller_from=session.caller_from,
                caller_profile=caller_profile,
            )
            # Strip JSON format instructions - realtime pipeline uses plain text
            # The prompt tells the model to "Respond ONLY in valid JSON" but we
            # need natural speech for TTS, not JSON
            import re
            system_prompt = re.sub(
                r'Respond ONLY in valid JSON:.*?(?=\n\n|\Z)',
                'Respond in natural, conversational speech. Keep responses concise (1-3 sentences). '
                'Do NOT use JSON format. Speak as if talking to the caller directly.',
                system_prompt,
                flags=re.DOTALL,
            )
            system_prompt = re.sub(
                r'Responde SOLO en JSON válido:.*?(?=\n\n|\Z)',
                'Responde en habla natural y conversacional. Mantén las respuestas concisas (1-3 oraciones). '
                'NO uses formato JSON. Habla como si estuvieras hablando directamente con el llamante.',
                system_prompt,
                flags=re.DOTALL,
            )
        else:
            system_prompt = "You are a helpful AI assistant. Respond naturally and conversationally. Keep responses brief and friendly."

        session.state.conversation_history.append({
            "role": "system",
            "content": system_prompt,
        })
    except Exception as exc:
        logger.warning(
            "Could not load system prompt, using default",
            extra={"error": str(exc), "stream_sid": session.stream_sid},
        )
        session.state.conversation_history.append({
            "role": "system",
            "content": "You are a helpful AI assistant. Respond naturally and conversationally. Keep responses brief and friendly.",
        })

    # Add the trigger message to conversation history
    session.state.conversation_history.append({
        "role": "user",
        "content": "(start conversation) - Respond with ONLY a brief, natural greeting. Do not recite information from the knowledge base. Just welcome the caller warmly in 1-2 sentences.",
    })

    # Transition to PROCESSING
    session.pipeline_state = PipelineState.PROCESSING

    # Run the LLM → TTS → Twilio pipeline for the greeting as a tracked task
    # so that barge-in can cancel it via session.current_generation_task
    task = asyncio.create_task(_generate_and_speak(session, ws))
    session.current_generation_task = task
    session.add_pipeline_task(task)
    try:
        await task
    except asyncio.CancelledError:
        logger.info(
            "Opening greeting cancelled (barge-in)",
            extra={"stream_sid": session.stream_sid},
        )
