"""
Webhook management API endpoints for v1.

Provides endpoints for managing webhooks, event subscriptions,
and real-time notifications.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from src.database.schema import DatabaseManager

router = APIRouter()


@router.post("/webhooks/subscribe")
async def subscribe_webhook(
    url: str, events: List[str], secret: Optional[str] = None, db: DatabaseManager = Depends()
):
    """Subscribe to webhook events."""
    raise HTTPException(status_code=501, detail="Webhook endpoints not yet implemented")


@router.get("/webhooks")
async def list_webhooks(active_only: bool = Query(True), db: DatabaseManager = Depends()):
    """List all configured webhooks."""
    raise HTTPException(status_code=501, detail="Webhook endpoints not yet implemented")


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int, db: DatabaseManager = Depends()):
    """Delete a webhook subscription."""
    raise HTTPException(status_code=501, detail="Webhook endpoints not yet implemented")


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: int, db: DatabaseManager = Depends()):
    """Test a webhook by sending a test event."""
    raise HTTPException(status_code=501, detail="Webhook endpoints not yet implemented")
