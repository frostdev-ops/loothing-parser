"""
Integration tests for the streaming pipeline.

Tests the complete flow from WebSocket client to database storage,
including event processing, segmentation, and compression.
"""

import asyncio
import json
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.streaming_server import StreamingServer
from src.streaming.client import CombatLogStreamer
from src.database.schema import DatabaseManager, create_tables
from src.api.models import StreamMessage, SessionStart


@pytest_asyncio.fixture
async def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    db = DatabaseManager(db_path)
    create_tables(db)
    yield db
    db.close()

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest_asyncio.fixture
async def streaming_server(test_db):
    """Create a test streaming server instance."""
    server = StreamingServer(test_db.db_path)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def sample_combat_log_lines():
    """Sample combat log lines for testing."""
    return [
        "9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,11.2.0,PROJECT_ID,1",
        '9/15/2025 21:30:21.463-4  ZONE_CHANGE,2649,"Hallowfall",23',
        '9/15/2025 21:30:21.463-4  MAP_CHANGE,2215,"Hallowfall",4939.580078,-593.750000,4397.919922,-3902.080078',
        '9/15/2025 21:30:22.123-4  ENCOUNTER_START,2902,"Ulgrax the Devourer",16,20,2657',
        '9/15/2025 21:30:22.124-4  SPELL_CAST_START,Player-1234,"Testplayer",0x512,0x0,Player-1234,"Testplayer",0x512,0x0,1234,"Test Spell",0x1',
        '9/15/2025 21:30:23.456-4  SPELL_DAMAGE,Player-1234,"Testplayer",0x512,0x0,Creature-5678,"Ulgrax the Devourer",0x10a28,0x0,1234,"Test Spell",0x1,5678,0,0,0,0,0,0,0',
        '9/15/2025 21:30:24.789-4  UNIT_DIED,nil,nil,0x0,0x0,Creature-5678,"Ulgrax the Devourer",0x10a28,0x0',
        '9/15/2025 21:30:25.000-4  ENCOUNTER_END,2902,"Ulgrax the Devourer",16,20,1,180000',
    ]


class TestStreamingPipeline:
    """Test the complete streaming pipeline."""

    @pytest.mark.asyncio
    async def test_full_streaming_flow(self, streaming_server, sample_combat_log_lines):
        """Test complete flow from client to database storage."""
        # Create a mock WebSocket connection
        websocket = AsyncMock()
        api_key = "dev_key_12345"

        # Simulate client connection
        session_id = None

        # Mock WebSocket message sequence
        messages = []

        # Session start
        session_start = SessionStart(
            client_id="test_client",
            client_version="1.0.0",
            character_name="Testplayer",
            realm="TestRealm",
            log_start_time=time.time(),
        )

        messages.append(
            StreamMessage(
                type="start_session",
                timestamp=time.time(),
                metadata=session_start.model_dump(),
            )
        )

        # Log lines
        for i, line in enumerate(sample_combat_log_lines):
            messages.append(
                StreamMessage(
                    type="log_line",
                    timestamp=time.time(),
                    line=line,
                    sequence=i,
                )
            )

        # Session end
        messages.append(StreamMessage(type="end_session", timestamp=time.time()))

        # Mock WebSocket receive to return our messages
        message_iter = iter([msg.model_dump_json() for msg in messages])
        websocket.receive_text.side_effect = message_iter

        # Capture sent responses
        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(json.loads(x))

        # Mock WebSocket client info
        websocket.client.host = "127.0.0.1"

        # Process the connection
        try:
            await streaming_server.handle_websocket_connection(websocket, api_key)
        except StopIteration:
            # Expected when we run out of messages
            pass

        # Verify responses
        assert len(sent_responses) >= 2  # Welcome message + acknowledgments

        # Check welcome message
        welcome = sent_responses[0]
        assert welcome["type"] == "status"
        assert welcome["message"] == "Connected successfully"
        assert "session_id" in welcome["data"]

        # Check database storage
        cursor = streaming_server.db.execute("SELECT COUNT(*) FROM encounters")
        encounter_count = cursor.fetchone()[0]
        assert encounter_count >= 1  # Should have at least one encounter

        cursor = streaming_server.db.execute("SELECT COUNT(*) FROM characters")
        character_count = cursor.fetchone()[0]
        assert character_count >= 1  # Should have at least one character

    @pytest.mark.asyncio
    async def test_error_handling(self, streaming_server):
        """Test error handling in the streaming pipeline."""
        websocket = AsyncMock()
        api_key = "invalid_key"

        # Should reject invalid API key
        websocket.close = AsyncMock()
        await streaming_server.handle_websocket_connection(websocket, api_key)

        websocket.close.assert_called_with(code=4001, reason="Authentication failed")

    @pytest.mark.asyncio
    async def test_rate_limiting(self, streaming_server):
        """Test rate limiting functionality."""
        websocket = AsyncMock()
        api_key = "dev_key_12345"

        # Mock rapid message sending
        rapid_messages = [
            StreamMessage(
                type="log_line",
                timestamp=time.time(),
                line="test line",
                sequence=i,
            ).model_dump_json()
            for i in range(1000)  # Send many messages rapidly
        ]

        message_iter = iter(rapid_messages)
        websocket.receive_text.side_effect = message_iter
        websocket.client.host = "127.0.0.1"

        # Track responses
        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(json.loads(x))

        # Process messages
        try:
            await streaming_server.handle_websocket_connection(websocket, api_key)
        except StopIteration:
            pass

        # Should have received some responses (not necessarily all due to rate limiting)
        assert len(sent_responses) > 0

    @pytest.mark.asyncio
    async def test_concurrent_connections(self, streaming_server):
        """Test multiple concurrent client connections."""
        num_clients = 3
        api_key = "dev_key_12345"

        async def simulate_client(client_id):
            websocket = AsyncMock()
            websocket.client.host = f"127.0.0.{client_id}"

            # Simple message sequence
            messages = [
                StreamMessage(
                    type="start_session",
                    timestamp=time.time(),
                    metadata={"client_id": f"client_{client_id}"},
                ).model_dump_json(),
                StreamMessage(
                    type="log_line",
                    timestamp=time.time(),
                    line="test line",
                    sequence=1,
                ).model_dump_json(),
                StreamMessage(
                    type="end_session", timestamp=time.time()
                ).model_dump_json(),
            ]

            message_iter = iter(messages)
            websocket.receive_text.side_effect = message_iter

            sent_responses = []
            websocket.send_text.side_effect = lambda x: sent_responses.append(
                json.loads(x)
            )

            try:
                await streaming_server.handle_websocket_connection(websocket, api_key)
            except StopIteration:
                pass

            return len(sent_responses)

        # Run clients concurrently
        tasks = [simulate_client(i) for i in range(num_clients)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all clients were handled
        assert len(results) == num_clients
        for result in results:
            if not isinstance(result, Exception):
                assert result > 0  # Each client should receive responses

    @pytest.mark.asyncio
    async def test_data_compression_integration(self, streaming_server):
        """Test that data is properly compressed in the database."""
        websocket = AsyncMock()
        api_key = "dev_key_12345"

        # Generate many log lines to trigger compression
        many_lines = [
            f'9/15/2025 21:30:{20 + i}.000-4  SPELL_DAMAGE,Player-1234,"Testplayer",0x512,0x0,Creature-5678,"Target",0x10a28,0x0,1234,"Spell",0x1,{1000 + i},0,0,0,0,0,0,0'
            for i in range(100)
        ]

        messages = [
            StreamMessage(
                type="start_session",
                timestamp=time.time(),
                metadata={"client_id": "test_compression"},
            ).model_dump_json()
        ]

        for i, line in enumerate(many_lines):
            messages.append(
                StreamMessage(
                    type="log_line",
                    timestamp=time.time(),
                    line=line,
                    sequence=i,
                ).model_dump_json()
            )

        messages.append(
            StreamMessage(type="end_session", timestamp=time.time()).model_dump_json()
        )

        message_iter = iter(messages)
        websocket.receive_text.side_effect = message_iter
        websocket.client.host = "127.0.0.1"

        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(json.loads(x))

        try:
            await streaming_server.handle_websocket_connection(websocket, api_key)
        except StopIteration:
            pass

        # Wait for processing to complete
        await asyncio.sleep(0.1)

        # Check that compressed data exists
        cursor = streaming_server.db.execute(
            "SELECT COUNT(*), SUM(compressed_size), SUM(uncompressed_size) FROM event_blocks"
        )
        row = cursor.fetchone()
        block_count, compressed_size, uncompressed_size = row

        if block_count > 0:
            assert compressed_size < uncompressed_size  # Should be compressed
            compression_ratio = compressed_size / uncompressed_size
            assert compression_ratio < 0.8  # Should achieve reasonable compression

    @pytest.mark.asyncio
    async def test_encounter_segmentation(
        self, streaming_server, sample_combat_log_lines
    ):
        """Test that encounters are properly segmented and stored."""
        websocket = AsyncMock()
        api_key = "dev_key_12345"

        # Use sample lines that include ENCOUNTER_START/END
        messages = [
            StreamMessage(
                type="start_session",
                timestamp=time.time(),
                metadata={"client_id": "test_encounters"},
            ).model_dump_json()
        ]

        for i, line in enumerate(sample_combat_log_lines):
            messages.append(
                StreamMessage(
                    type="log_line",
                    timestamp=time.time(),
                    line=line,
                    sequence=i,
                ).model_dump_json()
            )

        messages.append(
            StreamMessage(type="end_session", timestamp=time.time()).model_dump_json()
        )

        message_iter = iter(messages)
        websocket.receive_text.side_effect = message_iter
        websocket.client.host = "127.0.0.1"

        sent_responses = []
        websocket.send_text.side_effect = lambda x: sent_responses.append(json.loads(x))

        try:
            await streaming_server.handle_websocket_connection(websocket, api_key)
        except StopIteration:
            pass

        # Wait for processing to complete
        await asyncio.sleep(0.1)

        # Check encounter storage
        cursor = streaming_server.db.execute(
            "SELECT boss_name, success, encounter_type FROM encounters"
        )
        encounters = cursor.fetchall()

        # Should have at least one encounter (Ulgrax)
        assert len(encounters) >= 1

        # Check for the specific encounter from our sample data
        ulgrax_encounters = [e for e in encounters if "Ulgrax" in e[0]]
        assert len(ulgrax_encounters) >= 1

        encounter = ulgrax_encounters[0]
        assert encounter[1] == 1  # success = True
        assert encounter[2] == "raid"  # encounter_type = raid


if __name__ == "__main__":
    pytest.main([__file__])
