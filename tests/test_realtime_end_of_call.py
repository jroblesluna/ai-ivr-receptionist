"""Unit tests for src/realtime/end_of_call.py.

Tests the end-of-call processing logic including report generation,
WhatsApp notifications, email reports, and the orchestration function.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.realtime.end_of_call import (
    generate_call_report,
    process_end_of_call,
    save_call_report,
    send_email_report,
    send_whatsapp_notification,
)


# ---------------------------------------------------------------------------
# Report Generation Tests
# ---------------------------------------------------------------------------


class TestGenerateCallReport:
    """Tests for generate_call_report()."""

    @patch("src.realtime.end_of_call._now_local")
    @patch("src.db.uc_get")
    def test_generates_report_with_all_fields(self, mock_uc_get, mock_now):
        """Report should contain all required fields."""
        mock_uc_get.return_value = {"name": "Acme Corp", "is_demo": True}
        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0, tzinfo=ZoneInfo("UTC"))

        history = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        info = {
            "name": "John Doe",
            "phone": "+14085551234",
            "notes": "Interested in product X",
            "goodbye": "Goodbye!",
        }

        report = generate_call_report(
            call_sid="CA123",
            demo_id="demo_1",
            language="en",
            caller_from="+14085551234",
            conversation_history=history,
            collected_info=info,
        )

        assert report["use_case"] == "Acme Corp"
        assert report["caller_name"] == "John Doe"
        assert report["caller_phone"] == "+14085551234"
        assert report["topic"] == "Conversational Agent"
        assert report["language"] == "English"
        assert report["summary"] == "Interested in product X"
        assert report["goodbye"] == "Goodbye!"
        # System messages should be filtered out
        assert len(report["conversation"]) == 2
        assert report["conversation"][0]["role"] == "user"
        assert report["conversation"][1]["role"] == "assistant"
        assert report["timestamp"] == "2024-01-15 10:30:00"

    @patch("src.realtime.end_of_call._now_local")
    @patch("src.db.uc_get")
    def test_incomplete_report_marked(self, mock_uc_get, mock_now):
        """Incomplete reports should have the incomplete flag and prefix in summary."""
        mock_uc_get.return_value = {"name": "Test Co", "is_demo": True}
        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0, tzinfo=ZoneInfo("UTC"))

        report = generate_call_report(
            call_sid="CA123",
            demo_id="demo_1",
            language="es",
            caller_from="+34600111222",
            conversation_history=[],
            collected_info={"notes": "partial info"},
            incomplete=True,
        )

        assert report["incomplete"] is True
        assert "[INCOMPLETE" in report["summary"]
        assert report["language"] == "Español"

    @patch("src.realtime.end_of_call._now_local")
    @patch("src.db.uc_get")
    def test_fallback_to_caller_from_when_no_name(self, mock_uc_get, mock_now):
        """When no name is collected, caller_from should be used."""
        mock_uc_get.return_value = {"name": "Demo", "is_demo": True}
        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0, tzinfo=ZoneInfo("UTC"))

        report = generate_call_report(
            call_sid="CA123",
            demo_id="demo_1",
            language="en",
            caller_from="+14085559999",
            conversation_history=[],
            collected_info={},
        )

        assert report["caller_name"] == "+14085559999"
        assert report["caller_phone"] == "+14085559999"

    @patch("src.realtime.end_of_call._now_local")
    def test_empty_demo_id_gives_empty_use_case(self, mock_now):
        """When demo_id is empty, use_case should be empty string."""
        mock_now.return_value = datetime(2024, 1, 15, 10, 30, 0, tzinfo=ZoneInfo("UTC"))

        report = generate_call_report(
            call_sid="CA123",
            demo_id="",
            language="en",
            caller_from="+14085551234",
            conversation_history=[],
            collected_info={},
        )

        assert report["use_case"] == ""


# ---------------------------------------------------------------------------
# Save Report Tests
# ---------------------------------------------------------------------------


class TestSaveCallReport:
    """Tests for save_call_report()."""

    @patch("reports.save")
    def test_saves_report_and_returns_id(self, mock_save):
        """Should call reports.save() and return the report ID."""
        mock_save.return_value = "abc123def456"

        report_data = {"timestamp": "2024-01-01 12:00:00", "use_case": "Test"}
        result = save_call_report(report_data)

        assert result == "abc123def456"
        mock_save.assert_called_once_with(report_data)


# ---------------------------------------------------------------------------
# WhatsApp Notification Tests
# ---------------------------------------------------------------------------


class TestSendWhatsappNotification:
    """Tests for send_whatsapp_notification()."""

    @pytest.fixture(autouse=True)
    def _set_db_url(self, monkeypatch, tmp_path):
        """Set DATABASE_URL so runtime_config can import without error."""
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    @patch("config.twilio_client")
    @patch("runtime_config.get")
    def test_sends_whatsapp_when_enabled(self, mock_rc_get, mock_twilio):
        """Should send WhatsApp message when notifications are enabled."""
        mock_rc_get.side_effect = lambda key, *args: {
            "notify_whatsapp": "1",
            "whatsapp_from": "+14155238886",
            "whatsapp_to": "+14085551234",
        }.get(key, "")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(sid="SM123")
        mock_twilio.return_value = mock_client

        report_data = {
            "timestamp": "2024-01-01 12:00:00",
            "use_case": "Acme Corp",
            "topic": "Conversational Agent",
            "language": "English",
            "caller_name": "John",
            "caller_phone": "+14085559999",
            "summary": "Test summary",
        }

        send_whatsapp_notification(
            report_data=report_data,
            report_id="rpt123",
            base_url="https://example.com",
        )

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["from_"] == "whatsapp:+14155238886"
        assert call_kwargs["to"] == "whatsapp:+14085551234"
        assert "Acme Corp" in call_kwargs["body"]
        assert "rpt123" in call_kwargs["body"]

    @patch("runtime_config.get")
    def test_skips_when_disabled(self, mock_rc_get):
        """Should not send when notify_whatsapp is not '1'."""
        mock_rc_get.side_effect = lambda key, *args: {
            "notify_whatsapp": "0",
        }.get(key, "")

        # Should not raise
        send_whatsapp_notification(
            report_data={"timestamp": "now"},
            report_id="rpt123",
        )

    @patch("runtime_config.get")
    def test_skips_when_no_from_to(self, mock_rc_get):
        """Should not send when whatsapp_from or whatsapp_to is empty."""
        mock_rc_get.side_effect = lambda key, *args: {
            "notify_whatsapp": "1",
            "whatsapp_from": "",
            "whatsapp_to": "",
        }.get(key, "")

        # Should not raise
        send_whatsapp_notification(
            report_data={"timestamp": "now"},
            report_id="rpt123",
        )

    @patch("config.twilio_client")
    @patch("runtime_config.get")
    def test_incomplete_flag_in_message(self, mock_rc_get, mock_twilio):
        """Incomplete reports should include a warning in the WhatsApp message."""
        mock_rc_get.side_effect = lambda key, *args: {
            "notify_whatsapp": "1",
            "whatsapp_from": "+14155238886",
            "whatsapp_to": "+14085551234",
        }.get(key, "")

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(sid="SM123")
        mock_twilio.return_value = mock_client

        report_data = {
            "timestamp": "2024-01-01",
            "use_case": "Test",
            "topic": "Agent",
            "language": "English",
            "caller_name": "Jane",
            "caller_phone": "+1234",
            "summary": "",
            "incomplete": True,
        }

        send_whatsapp_notification(
            report_data=report_data,
            report_id="rpt456",
        )

        body = mock_client.messages.create.call_args[1]["body"]
        assert "incompleta" in body.lower() or "incomplete" in body.lower()


# ---------------------------------------------------------------------------
# Email Report Tests
# ---------------------------------------------------------------------------


class TestSendEmailReport:
    """Tests for send_email_report()."""

    @pytest.fixture(autouse=True)
    def _set_db_url(self, monkeypatch, tmp_path):
        """Set DATABASE_URL so runtime_config can import without error."""
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    @patch("email_helper.send_report_email")
    def test_sends_email_with_correct_format(self, mock_send):
        """Should call send_report_email with formatted subject and body."""
        report_data = {
            "timestamp": "2024-01-01 12:00:00",
            "use_case": "Acme Corp",
            "caller_name": "John",
            "caller_phone": "+14085559999",
            "topic": "Conversational Agent",
            "language": "English",
            "summary": "Customer inquiry about pricing",
        }

        send_email_report(
            report_data=report_data,
            report_id="rpt789",
            base_url="https://example.com",
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args[1]
        assert "+14085559999" in call_args["subject"]
        assert "Acme Corp" in call_args["body"]
        assert "rpt789" in call_args["body"]

    @patch("email_helper.send_report_email")
    def test_incomplete_status_in_email(self, mock_send):
        """Incomplete reports should include status in email body."""
        report_data = {
            "timestamp": "2024-01-01",
            "use_case": "Test",
            "caller_name": "Jane",
            "caller_phone": "+1234",
            "topic": "Agent",
            "language": "English",
            "summary": "",
            "incomplete": True,
        }

        send_email_report(
            report_data=report_data,
            report_id="rpt000",
        )

        body = mock_send.call_args[1]["body"]
        assert "INCOMPLETE" in body


# ---------------------------------------------------------------------------
# End-of-Call Orchestration Tests
# ---------------------------------------------------------------------------


class TestProcessEndOfCall:
    """Tests for process_end_of_call() orchestration."""

    @patch("src.realtime.end_of_call.send_email_report")
    @patch("src.realtime.end_of_call.send_whatsapp_notification")
    @patch("src.realtime.end_of_call.save_call_report")
    @patch("src.realtime.end_of_call.generate_call_report")
    def test_full_flow_normal_end(self, mock_gen, mock_save, mock_wa, mock_email):
        """Normal end-of-call should generate report, save, and send notifications."""
        mock_gen.return_value = {"timestamp": "now", "use_case": "Test"}
        mock_save.return_value = "rpt_abc"

        result = process_end_of_call(
            call_sid="CA123",
            demo_id="demo_1",
            language="en",
            caller_from="+14085551234",
            conversation_history=[{"role": "user", "content": "hi"}],
            collected_info={"name": "John"},
            incomplete=False,
            base_url="https://example.com",
        )

        assert result == "rpt_abc"
        mock_gen.assert_called_once()
        mock_save.assert_called_once_with({"timestamp": "now", "use_case": "Test"})
        mock_wa.assert_called_once()
        mock_email.assert_called_once()

    @patch("src.realtime.end_of_call.send_email_report")
    @patch("src.realtime.end_of_call.send_whatsapp_notification")
    @patch("src.realtime.end_of_call.save_call_report")
    @patch("src.realtime.end_of_call.generate_call_report")
    def test_incomplete_flag_passed_through(self, mock_gen, mock_save, mock_wa, mock_email):
        """Incomplete flag should be passed to generate_call_report."""
        mock_gen.return_value = {"timestamp": "now", "incomplete": True}
        mock_save.return_value = "rpt_partial"

        result = process_end_of_call(
            call_sid="CA123",
            demo_id="demo_1",
            language="en",
            caller_from="+14085551234",
            conversation_history=[],
            collected_info={},
            incomplete=True,
        )

        assert result == "rpt_partial"
        gen_kwargs = mock_gen.call_args[1]
        assert gen_kwargs["incomplete"] is True

    @patch("src.realtime.end_of_call.save_call_report")
    @patch("src.realtime.end_of_call.generate_call_report")
    def test_returns_none_on_failure(self, mock_gen, mock_save):
        """Should return None if an exception occurs."""
        mock_gen.side_effect = Exception("DB error")

        result = process_end_of_call(
            call_sid="CA123",
            demo_id="demo_1",
            language="en",
            caller_from="+14085551234",
            conversation_history=[],
            collected_info={},
        )

        assert result is None
