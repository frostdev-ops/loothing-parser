"""
Example streaming client for WoW combat log data.

Demonstrates how to connect to the streaming server and send combat log
lines in real-time for processing.
"""

import asyncio
import json
import time
import logging
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from src.api.models import StreamMessage, StreamResponse, SessionStart

logger = logging.getLogger(__name__)


class CombatLogStreamer:
    """
    Streaming client for sending combat log data to the server.

    Features:
    - WebSocket connection with automatic reconnection
    - File monitoring and streaming
    - Sequence tracking and acknowledgments
    - Error handling and recovery
    """

    def __init__(
        self,
        server_url: str = "ws://localhost:8000/stream",
        api_key: str = "dev_key_12345",
        client_id: str = "test_client",
        reconnect_delay: float = 5.0,
    ):
        """
        Initialize combat log streamer.

        Args:
            server_url: WebSocket server URL
            api_key: API key for authentication
            client_id: Unique client identifier
            reconnect_delay: Seconds to wait before reconnecting
        """
        self.server_url = f"{server_url}?api_key={api_key}"
        self.api_key = api_key
        self.client_id = client_id
        self.reconnect_delay = reconnect_delay

        # Connection state
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.connected = False
        self.session_id: Optional[str] = None

        # Sequence tracking
        self.sequence_counter = 0
        self.pending_acks: Dict[int, float] = {}  # sequence -> timestamp

        # File streaming state
        self.file_position = 0
        self.last_file_size = 0

        # Statistics
        self.stats = {
            "lines_sent": 0,
            "acks_received": 0,
            "errors": 0,
            "reconnections": 0,
            "start_time": time.time(),
        }

    async def connect(self) -> bool:
        """
        Connect to the streaming server.

        Returns:
            True if connection successful
        """
        try:
            logger.info(f"Connecting to {self.server_url}")
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True

            logger.info("Connected successfully, waiting for welcome message...")

            # Wait for welcome message
            welcome_msg = await self.websocket.recv()
            welcome = StreamResponse.model_validate_json(welcome_msg)

            if welcome.type == "status":
                self.session_id = welcome.data.get("session_id")
                logger.info(f"Session established: {self.session_id}")

                # Send session start
                await self.send_session_start()
                return True
            else:
                logger.error(f"Unexpected welcome message: {welcome}")
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from server."""
        if self.connected and self.websocket:
            try:
                # Send session end
                await self.send_session_end()

                # Close connection
                await self.websocket.close()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")

        self.connected = False
        self.websocket = None
        self.session_id = None

    async def send_session_start(self):
        """Send session start message."""
        session_start = SessionStart(
            client_id=self.client_id,
            client_version="1.0.0",
            character_name="TestCharacter",
            server="TestRealm",
            region="US",
            log_start_time=time.time(),
        )

        message = StreamMessage(
            type="start_session",
            timestamp=time.time(),
            metadata=session_start.model_dump(),
        )

        await self._send_message(message)
        logger.info("Session start sent")

    async def send_session_end(self):
        """Send session end message."""
        message = StreamMessage(type="end_session", timestamp=time.time())

        await self._send_message(message)
        logger.info("Session end sent")

    async def send_heartbeat(self):
        """Send heartbeat message."""
        message = StreamMessage(type="heartbeat", timestamp=time.time())

        await self._send_message(message)
        logger.debug("Heartbeat sent")

    async def send_log_line(self, line: str) -> int:
        """
        Send a combat log line.

        Args:
            line: Combat log line

        Returns:
            Sequence number assigned
        """
        sequence = self.sequence_counter
        self.sequence_counter += 1

        message = StreamMessage(
            type="log_line", timestamp=time.time(), line=line.strip(), sequence=sequence
        )

        await self._send_message(message)

        # Track pending acknowledgment
        self.pending_acks[sequence] = time.time()
        self.stats["lines_sent"] += 1

        return sequence

    async def stream_file(
        self,
        file_path: str,
        follow: bool = False,
        start_position: int = 0,
        lines_per_batch: int = 100,
        batch_delay: float = 0.1,
    ):
        """
        Stream a combat log file to the server.

        Args:
            file_path: Path to combat log file
            follow: Continue reading as file grows (tail -f mode)
            start_position: Byte position to start reading from
            lines_per_batch: Lines to send per batch
            batch_delay: Delay between batches
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Combat log file not found: {file_path}")

        self.file_position = start_position
        logger.info(f"Starting to stream file: {file_path} (follow={follow})")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(self.file_position)

                lines_batch = []
                while True:
                    line = f.readline()

                    if line:
                        # Process line
                        if line.strip():  # Skip empty lines
                            lines_batch.append(line)

                            # Send batch when full
                            if len(lines_batch) >= lines_per_batch:
                                await self._send_batch(lines_batch)
                                lines_batch = []
                                await asyncio.sleep(batch_delay)

                        self.file_position = f.tell()

                    else:
                        # End of file
                        if lines_batch:
                            # Send remaining lines
                            await self._send_batch(lines_batch)
                            lines_batch = []

                        if not follow:
                            break

                        # In follow mode, wait and check for new data
                        await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Error streaming file: {e}")
            raise

        logger.info("File streaming completed")

    async def _send_batch(self, lines: list):
        """Send a batch of log lines."""
        for line in lines:
            if not self.connected:
                raise ConnectionError("Not connected to server")

            try:
                await self.send_log_line(line)
            except Exception as e:
                logger.error(f"Error sending line: {e}")
                self.stats["errors"] += 1

        logger.debug(f"Sent batch of {len(lines)} lines")

    async def _send_message(self, message: StreamMessage):
        """Send a message to the server."""
        if not self.connected or not self.websocket:
            raise ConnectionError("Not connected to server")

        try:
            await self.websocket.send(message.model_dump_json())
        except (ConnectionClosed, WebSocketException) as e:
            logger.error(f"WebSocket error: {e}")
            self.connected = False
            raise

    async def handle_messages(self):
        """Handle incoming messages from server."""
        while self.connected and self.websocket:
            try:
                message_json = await self.websocket.recv()
                response = StreamResponse.model_validate_json(message_json)

                if response.type == "ack":
                    self._handle_acknowledgment(response)
                elif response.type == "error":
                    logger.error(f"Server error: {response.message}")
                    self.stats["errors"] += 1
                elif response.type == "status":
                    logger.info(f"Server status: {response.message}")
                else:
                    logger.debug(f"Received message: {response.type}")

            except (ConnectionClosed, WebSocketException):
                logger.warning("Connection lost")
                self.connected = False
                break
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    def _handle_acknowledgment(self, response: StreamResponse):
        """Handle acknowledgment from server."""
        if response.sequence_ack is not None:
            # Remove from pending
            if response.sequence_ack in self.pending_acks:
                del self.pending_acks[response.sequence_ack]
                self.stats["acks_received"] += 1

    async def run_with_reconnect(self, stream_task: Callable, max_reconnects: int = 10):
        """
        Run with automatic reconnection.

        Args:
            stream_task: Async function to run after connection
            max_reconnects: Maximum reconnection attempts
        """
        reconnect_count = 0

        while reconnect_count < max_reconnects:
            try:
                # Connect
                if await self.connect():
                    # Start message handler
                    message_task = asyncio.create_task(self.handle_messages())

                    try:
                        # Run the main streaming task
                        await stream_task()

                    except Exception as e:
                        logger.error(f"Streaming task error: {e}")

                    finally:
                        # Cleanup
                        message_task.cancel()
                        await self.disconnect()

                    # If we get here without error, task completed successfully
                    break

                else:
                    # Connection failed
                    reconnect_count += 1
                    logger.warning(
                        f"Connection failed, attempt {reconnect_count}/{max_reconnects}"
                    )

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                reconnect_count += 1

            if reconnect_count < max_reconnects:
                logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.stats["reconnections"] += 1

        if reconnect_count >= max_reconnects:
            logger.error("Maximum reconnection attempts reached")

    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        uptime = time.time() - self.stats["start_time"]

        return {
            "uptime_seconds": uptime,
            "connected": self.connected,
            "session_id": self.session_id,
            "lines_sent": self.stats["lines_sent"],
            "acks_received": self.stats["acks_received"],
            "pending_acks": len(self.pending_acks),
            "errors": self.stats["errors"],
            "reconnections": self.stats["reconnections"],
            "lines_per_second": self.stats["lines_sent"] / max(uptime, 1.0),
            "ack_rate": (
                (self.stats["acks_received"] / self.stats["lines_sent"]) * 100
                if self.stats["lines_sent"] > 0
                else 0
            ),
        }


async def main():
    """Example usage of the streaming client."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create client
    client = CombatLogStreamer(
        server_url="ws://localhost:8000/stream",
        api_key="dev_key_12345",
        client_id="example_client",
    )

    async def example_stream_task():
        """Example streaming task."""
        # Send some sample log lines
        sample_lines = [
            "9/15/2025 21:30:21.462-4  COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,11.2.0,PROJECT_ID,1",
            '9/15/2025 21:30:21.463-4  ZONE_CHANGE,2649,"Hallowfall",23',
            '9/15/2025 21:30:21.463-4  MAP_CHANGE,2215,"Hallowfall",4939.580078,-593.750000,4397.919922,-3902.080078',
            '9/15/2025 21:30:22.123-4  SPELL_CAST_START,Player-1234,"PlayerName",0x512,0x0,Player-1234,"PlayerName",0x512,0x0,1234,"Example Spell",0x1',
            '9/15/2025 21:30:23.456-4  SPELL_DAMAGE,Player-1234,"PlayerName",0x512,0x0,Creature-5678,"TargetName",0x10a28,0x0,1234,"Example Spell",0x1,5678,0,0,0,0,0,0,0',
        ]

        logger.info("Sending sample log lines...")
        for line in sample_lines:
            await client.send_log_line(line)
            await asyncio.sleep(0.1)  # Small delay between lines

        # Wait a bit for acknowledgments
        await asyncio.sleep(2.0)

        # Send heartbeat
        await client.send_heartbeat()

        # Show stats
        stats = client.get_stats()
        logger.info(f"Final stats: {stats}")

    # Run with reconnection
    await client.run_with_reconnect(example_stream_task)


if __name__ == "__main__":
    asyncio.run(main())
