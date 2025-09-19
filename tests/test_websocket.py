"""
Tests for WebSocket connection and message flow.

Tests WebSocket protocol implementation, message handling,
and client-server communication patterns.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock
from typing import List, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.models import StreamMessage, StreamResponse, SessionStart
from src.streaming.client import CombatLogStreamer


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.messages_to_send: List[str] = []
        self.received_messages: List[str] = []
        self.closed = False
        self.close_code: int = None
        self.close_reason: str = None
        self.connected = False

    async def connect(self, url: str):
        """Mock connect method."""
        self.connected = True
        # Simulate welcome message
        welcome = StreamResponse(
            type="status",
            message="Connected successfully",
            data={"session_id": "test_session_123"}
        )
        self.messages_to_send.append(welcome.model_dump_json())

    async def send(self, message: str):
        """Mock send method."""
        if self.closed:
            raise ConnectionError("WebSocket is closed")
        self.received_messages.append(message)

    async def recv(self):
        """Mock receive method."""
        if self.closed:
            raise ConnectionError("WebSocket is closed")

        if not self.messages_to_send:
            # If no more messages, simulate connection closing
            await asyncio.sleep(0.1)
            raise ConnectionError("No more messages")

        return self.messages_to_send.pop(0)

    async def close(self, code: int = 1000, reason: str = ""):
        """Mock close method."""
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        self.connected = False


class TestWebSocketProtocol:
    """Test WebSocket protocol implementation."""

    @pytest.mark.asyncio
    async def test_basic_connection_flow(self):
        """Test basic WebSocket connection flow."""
        websocket = MockWebSocket()

        # Simulate connection
        await websocket.connect("ws://localhost:8000/stream?api_key=test")
        assert websocket.connected is True

        # Send a message
        test_message = StreamMessage(
            type="log_line",
            timestamp=time.time(),
            line="test log line",
            sequence=1
        )

        await websocket.send(test_message.model_dump_json())
        assert len(websocket.received_messages) == 1

        # Receive welcome message
        welcome_msg = await websocket.recv()
        welcome = StreamResponse.model_validate_json(welcome_msg)
        assert welcome.type == "status"
        assert welcome.message == "Connected successfully"

    @pytest.mark.asyncio
    async def test_message_serialization(self):
        """Test message serialization/deserialization."""
        # Test StreamMessage
        message = StreamMessage(
            type="log_line",
            timestamp=1234567890.123,
            line='9/15/2025 21:30:22.123-4  SPELL_DAMAGE,Player-1234,"Test",0x512,0x0,Target-5678,"Target",0x10a28,0x0,1234,"Spell",0x1,5000,0,0,0,0,0,0,0',
            sequence=42,
            metadata={"test": "data"}
        )

        # Serialize
        json_data = message.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize
        parsed_message = StreamMessage.model_validate_json(json_data)
        assert parsed_message.type == message.type
        assert parsed_message.timestamp == message.timestamp
        assert parsed_message.line == message.line
        assert parsed_message.sequence == message.sequence
        assert parsed_message.metadata == message.metadata

    @pytest.mark.asyncio
    async def test_response_serialization(self):
        """Test response message serialization."""
        response = StreamResponse(
            type="ack",
            message="Message acknowledged",
            sequence_ack=42,
            data={"processed": True, "lag_ms": 15.5}
        )

        # Serialize
        json_data = response.model_dump_json()

        # Deserialize
        parsed_response = StreamResponse.model_validate_json(json_data)
        assert parsed_response.type == response.type
        assert parsed_response.message == response.message
        assert parsed_response.sequence_ack == response.sequence_ack
        assert parsed_response.data == response.data

    @pytest.mark.asyncio
    async def test_session_start_message(self):
        """Test session start message handling."""
        session_start = SessionStart(
            client_id="test_client_123",
            client_version="1.0.0",
            character_name="Testcharacter",
            realm="TestRealm",
            log_start_time=1234567890.0
        )

        message = StreamMessage(
            type="start_session",
            timestamp=time.time(),
            metadata=session_start.model_dump()
        )

        # Serialize and deserialize
        json_data = message.model_dump_json()
        parsed_message = StreamMessage.model_validate_json(json_data)

        # Validate metadata can be converted back to SessionStart
        session_start_parsed = SessionStart(**parsed_message.metadata)
        assert session_start_parsed.client_id == session_start.client_id
        assert session_start_parsed.character_name == session_start.character_name

    @pytest.mark.asyncio
    async def test_invalid_message_handling(self):
        """Test handling of invalid messages."""
        websocket = MockWebSocket()

        # Test invalid JSON
        with pytest.raises(Exception):  # Should raise some kind of JSON error
            StreamMessage.model_validate_json("invalid json")

        # Test missing required fields
        with pytest.raises(Exception):  # Should raise validation error
            StreamMessage.model_validate_json('{"type": "log_line"}')  # Missing timestamp

        # Test invalid message type
        with pytest.raises(Exception):  # Should raise validation error
            StreamMessage.model_validate_json('{"type": "invalid_type", "timestamp": 1234567890}')


class TestCombatLogStreamer:
    """Test the CombatLogStreamer client implementation."""

    @pytest.mark.asyncio
    async def test_streamer_initialization(self):
        """Test streamer initialization."""
        streamer = CombatLogStreamer(
            server_url="ws://localhost:8000/stream",
            api_key="test_key",
            client_id="test_client",
            reconnect_delay=1.0
        )

        assert streamer.api_key == "test_key"
        assert streamer.client_id == "test_client"
        assert streamer.reconnect_delay == 1.0
        assert streamer.connected is False
        assert streamer.sequence_counter == 0

    @pytest.mark.asyncio
    async def test_streamer_stats_tracking(self):
        """Test that streamer tracks statistics correctly."""
        streamer = CombatLogStreamer()

        # Initial stats
        stats = streamer.get_stats()
        assert stats["lines_sent"] == 0
        assert stats["acks_received"] == 0
        assert stats["connected"] is False

        # Mock websocket connection
        streamer.websocket = AsyncMock()
        streamer.connected = True
        streamer.session_id = "test_session"

        # Simulate sending lines
        await streamer.send_log_line("test line 1")
        await streamer.send_log_line("test line 2")

        # Check stats
        stats = streamer.get_stats()
        assert stats["lines_sent"] == 2
        assert stats["connected"] is True
        assert stats["session_id"] == "test_session"

    @pytest.mark.asyncio
    async def test_streamer_sequence_tracking(self):
        """Test sequence number tracking."""
        streamer = CombatLogStreamer()
        streamer.websocket = AsyncMock()
        streamer.connected = True

        # Send multiple lines
        seq1 = await streamer.send_log_line("line 1")
        seq2 = await streamer.send_log_line("line 2")
        seq3 = await streamer.send_log_line("line 3")

        # Sequences should increment
        assert seq1 == 0
        assert seq2 == 1
        assert seq3 == 2

        # Check pending acknowledgments
        assert len(streamer.pending_acks) == 3
        assert 0 in streamer.pending_acks
        assert 1 in streamer.pending_acks
        assert 2 in streamer.pending_acks

    @pytest.mark.asyncio
    async def test_streamer_message_construction(self):
        """Test that streamer constructs messages correctly."""
        streamer = CombatLogStreamer()
        streamer.websocket = AsyncMock()
        streamer.connected = True

        # Send a log line
        test_line = '9/15/2025 21:30:22.123-4  SPELL_DAMAGE,Player-1234,"Test",0x512,0x0,Target-5678,"Target",0x10a28,0x0,1234,"Spell",0x1,5000,0,0,0,0,0,0,0'
        await streamer.send_log_line(test_line)

        # Check that websocket.send was called with correct message
        streamer.websocket.send.assert_called_once()
        sent_message_json = streamer.websocket.send.call_args[0][0]
        sent_message = StreamMessage.model_validate_json(sent_message_json)

        assert sent_message.type == "log_line"
        assert sent_message.line == test_line.strip()
        assert sent_message.sequence == 0

    @pytest.mark.asyncio
    async def test_heartbeat_functionality(self):
        """Test heartbeat message sending."""
        streamer = CombatLogStreamer()
        streamer.websocket = AsyncMock()
        streamer.connected = True

        await streamer.send_heartbeat()

        # Verify heartbeat message was sent
        streamer.websocket.send.assert_called_once()
        sent_message_json = streamer.websocket.send.call_args[0][0]
        sent_message = StreamMessage.model_validate_json(sent_message_json)

        assert sent_message.type == "heartbeat"
        assert sent_message.line is None
        assert sent_message.sequence is None

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test session start and end messages."""
        streamer = CombatLogStreamer()
        streamer.websocket = AsyncMock()
        streamer.connected = True

        # Send session start
        await streamer.send_session_start()

        # Verify session start message
        calls = streamer.websocket.send.call_args_list
        session_start_json = calls[0][0][0]
        session_start_msg = StreamMessage.model_validate_json(session_start_json)

        assert session_start_msg.type == "start_session"
        assert session_start_msg.metadata is not None

        # Validate metadata structure
        session_data = SessionStart(**session_start_msg.metadata)
        assert session_data.client_id == streamer.client_id

        # Send session end
        await streamer.send_session_end()

        # Verify session end message
        session_end_json = calls[1][0][0]
        session_end_msg = StreamMessage.model_validate_json(session_end_json)
        assert session_end_msg.type == "end_session"

    @pytest.mark.asyncio
    async def test_error_handling_disconnected(self):
        """Test error handling when not connected."""
        streamer = CombatLogStreamer()
        # Don't connect

        # Should raise error when trying to send
        with pytest.raises(ConnectionError):
            await streamer.send_log_line("test line")

        with pytest.raises(ConnectionError):
            await streamer.send_heartbeat()

        with pytest.raises(ConnectionError):
            await streamer.send_session_start()


class TestWebSocketMessageFlow:
    """Test complete message flows between client and server."""

    @pytest.mark.asyncio
    async def test_complete_session_flow(self):
        """Test a complete session from start to finish."""
        # This is a more integration-style test
        messages_sent = []
        responses_received = []

        # Mock a complete flow
        session_flow = [
            # Client sends session start
            StreamMessage(
                type="start_session",
                timestamp=time.time(),
                metadata=SessionStart(
                    client_id="test_client",
                    client_version="1.0.0",
                    character_name="TestChar",
                    realm="TestRealm"
                ).model_dump()
            ),

            # Client sends log lines
            StreamMessage(
                type="log_line",
                timestamp=time.time(),
                line="test line 1",
                sequence=0
            ),
            StreamMessage(
                type="log_line",
                timestamp=time.time(),
                line="test line 2",
                sequence=1
            ),

            # Client sends heartbeat
            StreamMessage(
                type="heartbeat",
                timestamp=time.time()
            ),

            # Client sends session end
            StreamMessage(
                type="end_session",
                timestamp=time.time()
            )
        ]

        # Simulate server responses
        server_responses = [
            StreamResponse(
                type="status",
                message="Session started",
                data={"session_id": "test_123"}
            ),
            StreamResponse(
                type="ack",
                sequence_ack=0,
                data={"processed": True}
            ),
            StreamResponse(
                type="ack",
                sequence_ack=1,
                data={"processed": True}
            ),
            StreamResponse(
                type="status",
                message="Heartbeat received",
                data={"server_time": time.time()}
            ),
            StreamResponse(
                type="status",
                message="Session ended"
            )
        ]

        # Verify message structure integrity
        for message in session_flow:
            json_data = message.model_dump_json()
            parsed = StreamMessage.model_validate_json(json_data)
            assert parsed.type == message.type

        for response in server_responses:
            json_data = response.model_dump_json()
            parsed = StreamResponse.model_validate_json(json_data)
            assert parsed.type == response.type

    @pytest.mark.asyncio
    async def test_acknowledgment_tracking(self):
        """Test acknowledgment tracking in message flow."""
        # Simulate sending multiple messages and receiving acks
        pending_sequences = set()
        ack_count = 0

        # Send messages
        for i in range(5):
            sequence = i
            pending_sequences.add(sequence)

        assert len(pending_sequences) == 5

        # Receive acknowledgments
        for i in [0, 2, 4]:  # Acknowledge some messages
            if i in pending_sequences:
                pending_sequences.remove(i)
                ack_count += 1

        assert ack_count == 3
        assert len(pending_sequences) == 2
        assert pending_sequences == {1, 3}

    @pytest.mark.asyncio
    async def test_error_message_handling(self):
        """Test handling of error messages from server."""
        error_response = StreamResponse(
            type="error",
            message="Processing failed",
            data={"error_code": 500, "details": "Database connection lost"}
        )

        # Serialize and deserialize
        json_data = error_response.model_dump_json()
        parsed_response = StreamResponse.model_validate_json(json_data)

        assert parsed_response.type == "error"
        assert parsed_response.message == "Processing failed"
        assert parsed_response.data["error_code"] == 500

    @pytest.mark.asyncio
    async def test_large_message_handling(self):
        """Test handling of large messages."""
        # Create a large combat log line (realistic size)
        large_line = "9/15/2025 21:30:22.123-4  SPELL_DAMAGE," + "Player-1234-567890AB," * 50 + "Test,0x512,0x0,Target,0x10a28,0x0,1234,Spell,0x1,5000,0,0,0,0,0,0,0"

        message = StreamMessage(
            type="log_line",
            timestamp=time.time(),
            line=large_line,
            sequence=0
        )

        # Should handle large messages without error
        json_data = message.model_dump_json()
        parsed_message = StreamMessage.model_validate_json(json_data)

        assert parsed_message.line == large_line
        assert len(json_data) > 1000  # Should be a substantial message

    @pytest.mark.asyncio
    async def test_concurrent_message_handling(self):
        """Test handling of concurrent messages."""
        # Simulate rapid message sending
        messages = []
        for i in range(100):
            message = StreamMessage(
                type="log_line",
                timestamp=time.time() + i * 0.001,  # Rapid succession
                line=f"test line {i}",
                sequence=i
            )
            messages.append(message)

        # All messages should serialize/deserialize correctly
        for i, message in enumerate(messages):
            json_data = message.model_dump_json()
            parsed_message = StreamMessage.model_validate_json(json_data)

            assert parsed_message.sequence == i
            assert f"test line {i}" in parsed_message.line

    @pytest.mark.asyncio
    async def test_malformed_message_recovery(self):
        """Test recovery from malformed messages."""
        valid_message = StreamMessage(
            type="log_line",
            timestamp=time.time(),
            line="valid line",
            sequence=1
        )

        # Valid message should work
        json_data = valid_message.model_dump_json()
        parsed = StreamMessage.model_validate_json(json_data)
        assert parsed.line == "valid line"

        # Invalid messages should raise appropriate errors
        invalid_messages = [
            '{"type": "log_line"}',  # Missing timestamp
            '{"timestamp": 1234567890}',  # Missing type
            '{"type": "invalid_type", "timestamp": 1234567890}',  # Invalid type
            'invalid json',  # Not JSON at all
            '',  # Empty string
        ]

        for invalid_msg in invalid_messages:
            with pytest.raises(Exception):  # Should raise validation or JSON error
                StreamMessage.model_validate_json(invalid_msg)


if __name__ == "__main__":
    pytest.main([__file__])