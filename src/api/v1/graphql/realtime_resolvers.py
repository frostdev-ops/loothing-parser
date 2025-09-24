"""Real-time GraphQL subscription resolvers."""

import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import redis.asyncio as redis
import logging

from .types import Encounter, CharacterPerformance
from ...database.schema import DatabaseManager
from ...config import get_settings

logger = logging.getLogger(__name__)


class RealtimeResolver:
    """Resolver for real-time GraphQL subscriptions."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.settings = get_settings()
        self.redis_client = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection for real-time events."""
        try:
            redis_url = self.settings.redis_url or "redis://localhost:6379"
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info("GraphQL realtime resolver: Redis connection initialized")
        except Exception as error:
            logger.warning(f"GraphQL realtime resolver: Redis not available: {error}")
            self.redis_client = None

    async def live_encounter_updates(
        self,
        encounter_id: Optional[int] = None
    ) -> AsyncGenerator[Union[Encounter, str], None]:
        """Subscribe to live encounter updates via Redis pub/sub."""

        if not self.redis_client:
            logger.warning("GraphQL realtime: Redis not available for live encounters")
            yield "Real-time subscriptions require Redis connection"
            return

        try:
            # Create pubsub client
            pubsub = self.redis_client.pubsub()

            # Subscribe to encounter update channels
            if encounter_id:
                channel = f"encounter:updates:{encounter_id}"
                await pubsub.subscribe(channel)
                logger.info(f"GraphQL subscription: listening to {channel}")
            else:
                # Subscribe to all encounter updates
                await pubsub.psubscribe("encounter:updates:*")
                logger.info("GraphQL subscription: listening to all encounter updates")

            # Set up a timeout to prevent infinite hanging
            timeout_time = datetime.now() + timedelta(hours=2)  # 2-hour max session
            last_keepalive = datetime.now()
            keepalive_interval = timedelta(seconds=30)

            while datetime.now() < timeout_time:
                try:
                    # Check for messages with timeout
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=5.0
                    )

                    if message and message.get('data'):
                        try:
                            # Parse the encounter update
                            update_data = json.loads(message['data'])

                            # Fetch the updated encounter from database
                            encounter = await self._get_encounter_by_id(
                                update_data.get('encounter_id')
                            )

                            if encounter:
                                logger.debug(f"GraphQL: yielding encounter update {encounter.id}")
                                yield encounter
                            else:
                                # Yield raw update if encounter not found
                                yield f"Encounter updated: {update_data}"

                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"GraphQL: Invalid encounter update format: {e}")
                            yield "Received invalid encounter update"

                    # Send periodic keepalives
                    if datetime.now() - last_keepalive > keepalive_interval:
                        yield "keepalive"
                        last_keepalive = datetime.now()

                except asyncio.TimeoutError:
                    # No message received, send keepalive
                    if datetime.now() - last_keepalive > keepalive_interval:
                        yield "keepalive"
                        last_keepalive = datetime.now()
                    continue

        except Exception as error:
            logger.error(f"GraphQL live encounters error: {error}")
            yield f"Subscription error: {str(error)}"
        finally:
            if pubsub:
                await pubsub.close()

    async def performance_alerts(
        self,
        character_name: Optional[str] = None,
        threshold: Optional[float] = None
    ) -> AsyncGenerator[Union[CharacterPerformance, str], None]:
        """Subscribe to performance alerts via Redis pub/sub."""

        if not self.redis_client:
            logger.warning("GraphQL realtime: Redis not available for performance alerts")
            yield "Real-time subscriptions require Redis connection"
            return

        try:
            # Create pubsub client
            pubsub = self.redis_client.pubsub()

            # Subscribe to performance alert channels
            if character_name:
                channel = f"performance:alerts:{character_name.lower()}"
                await pubsub.subscribe(channel)
                logger.info(f"GraphQL subscription: listening to {channel}")
            else:
                # Subscribe to all performance alerts
                await pubsub.psubscribe("performance:alerts:*")
                logger.info("GraphQL subscription: listening to all performance alerts")

            # Set up timeout and keepalive
            timeout_time = datetime.now() + timedelta(hours=2)  # 2-hour max session
            last_keepalive = datetime.now()
            keepalive_interval = timedelta(seconds=30)

            while datetime.now() < timeout_time:
                try:
                    # Check for messages with timeout
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=5.0
                    )

                    if message and message.get('data'):
                        try:
                            # Parse the performance alert
                            alert_data = json.loads(message['data'])

                            # Apply threshold filter if specified
                            if threshold is not None:
                                performance_value = alert_data.get('dps', 0) or alert_data.get('hps', 0)
                                if performance_value < threshold:
                                    continue  # Skip alerts below threshold

                            # Create CharacterPerformance object from alert data
                            performance = await self._create_performance_from_alert(alert_data)

                            if performance:
                                logger.debug(f"GraphQL: yielding performance alert for {performance.character_name}")
                                yield performance
                            else:
                                # Yield raw alert if performance object creation fails
                                yield f"Performance alert: {alert_data}"

                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"GraphQL: Invalid performance alert format: {e}")
                            yield "Received invalid performance alert"

                    # Send periodic keepalives
                    if datetime.now() - last_keepalive > keepalive_interval:
                        yield "keepalive"
                        last_keepalive = datetime.now()

                except asyncio.TimeoutError:
                    # No message received, send keepalive
                    if datetime.now() - last_keepalive > keepalive_interval:
                        yield "keepalive"
                        last_keepalive = datetime.now()
                    continue

        except Exception as error:
            logger.error(f"GraphQL performance alerts error: {error}")
            yield f"Subscription error: {str(error)}"
        finally:
            if pubsub:
                await pubsub.close()

    async def _get_encounter_by_id(self, encounter_id: int) -> Optional[Encounter]:
        """Get encounter from database by ID."""
        try:
            if not encounter_id:
                return None

            query = """
                SELECT e.id, e.boss_name, e.difficulty, e.start_time, e.end_time,
                       e.success, e.duration, e.guild_name, e.instance_name,
                       e.participants_count, e.wipe_count, e.encounter_id
                FROM combat_encounters e
                WHERE e.id = %s
                LIMIT 1
            """

            async with self.db.get_session() as session:
                result = await session.execute(query, (encounter_id,))
                row = await result.fetchone()

                if row:
                    return Encounter(
                        id=row[0],
                        boss_name=row[1],
                        difficulty=row[2],
                        start_time=row[3],
                        end_time=row[4],
                        success=row[5],
                        duration=row[6],
                        guild_name=row[7],
                        instance_name=row[8],
                        participants_count=row[9],
                        wipe_count=row[10],
                        encounter_id=row[11],
                        participants=[],  # Could be populated separately if needed
                        performance_summary={}
                    )

        except Exception as error:
            logger.error(f"Error fetching encounter {encounter_id}: {error}")

        return None

    async def _create_performance_from_alert(self, alert_data: Dict[str, Any]) -> Optional[CharacterPerformance]:
        """Create CharacterPerformance object from alert data."""
        try:
            # Extract required fields from alert data
            character_name = alert_data.get('character_name')
            if not character_name:
                return None

            return CharacterPerformance(
                id=alert_data.get('performance_id', 0),
                character_name=character_name,
                encounter_id=alert_data.get('encounter_id', 0),
                role=alert_data.get('role', 'Unknown'),
                class_name=alert_data.get('class_name', 'Unknown'),
                spec=alert_data.get('spec', 'Unknown'),
                dps=alert_data.get('dps', 0.0),
                hps=alert_data.get('hps', 0.0),
                damage_taken=alert_data.get('damage_taken', 0),
                deaths=alert_data.get('deaths', 0),
                interrupts=alert_data.get('interrupts', 0),
                dispels=alert_data.get('dispels', 0),
                active_time_percent=alert_data.get('active_time_percent', 0.0),
                gear_score=alert_data.get('gear_score', 0),
                item_level=alert_data.get('item_level', 0),
                timestamp=alert_data.get('timestamp', datetime.now()),
                alerts=alert_data.get('alerts', []),
                performance_percentile=alert_data.get('performance_percentile', 0.0),
                improvement_suggestions=alert_data.get('improvement_suggestions', [])
            )

        except Exception as error:
            logger.error(f"Error creating performance from alert: {error}")

        return None


# Helper function to publish encounter updates
async def publish_encounter_update(encounter_id: int, update_data: Dict[str, Any]):
    """Publish encounter update to Redis for GraphQL subscriptions."""
    try:
        settings = get_settings()
        redis_url = settings.redis_url or "redis://localhost:6379"
        redis_client = redis.from_url(redis_url, decode_responses=True)

        channel = f"encounter:updates:{encounter_id}"
        message = json.dumps({
            'encounter_id': encounter_id,
            'timestamp': datetime.now().isoformat(),
            **update_data
        })

        await redis_client.publish(channel, message)
        logger.debug(f"Published encounter update to {channel}")

    except Exception as error:
        logger.error(f"Failed to publish encounter update: {error}")


# Helper function to publish performance alerts
async def publish_performance_alert(character_name: str, performance_data: Dict[str, Any]):
    """Publish performance alert to Redis for GraphQL subscriptions."""
    try:
        settings = get_settings()
        redis_url = settings.redis_url or "redis://localhost:6379"
        redis_client = redis.from_url(redis_url, decode_responses=True)

        channel = f"performance:alerts:{character_name.lower()}"
        message = json.dumps({
            'character_name': character_name,
            'timestamp': datetime.now().isoformat(),
            **performance_data
        })

        await redis_client.publish(channel, message)
        logger.debug(f"Published performance alert to {channel}")

    except Exception as error:
        logger.error(f"Failed to publish performance alert: {error}")