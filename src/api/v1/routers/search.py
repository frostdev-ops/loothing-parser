"""
Advanced search endpoints for v1 API.

Provides comprehensive search capabilities including full-text search,
fuzzy matching, saved searches, and complex boolean logic filtering.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field, validator

from ..models.responses import PaginatedResponse
from ..models.common import FilterCriteria
from ..models.characters import CharacterProfile
from ..models.encounters import EncounterDetails
from ..models.guilds import GuildProfile
from ...database.schema import DatabaseManager
from ...database.query import QueryAPI
from ..dependencies import require_read_permission, get_authenticated_user

router = APIRouter()


class SearchScope(str, Enum):
    """Search scope enumeration."""

    CHARACTERS = "characters"
    ENCOUNTERS = "encounters"
    GUILDS = "guilds"
    ALL = "all"


class SearchOperator(str, Enum):
    """Boolean search operators."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class SearchCriteria(BaseModel):
    """Individual search criteria."""

    field: str = Field(..., description="Field to search in")
    operator: str = Field(default="contains", description="Search operator")
    value: Union[str, int, float, bool] = Field(..., description="Search value")
    case_sensitive: bool = Field(default=False, description="Case sensitive search")


class BooleanSearchQuery(BaseModel):
    """Boolean search query with multiple criteria."""

    criteria: List[SearchCriteria] = Field(..., description="Search criteria")
    logic_operator: SearchOperator = Field(
        default=SearchOperator.AND, description="Logic operator between criteria"
    )
    nested_queries: Optional[List["BooleanSearchQuery"]] = Field(
        default=None, description="Nested boolean queries"
    )


class SearchRequest(BaseModel):
    """Comprehensive search request."""

    query: Optional[str] = Field(None, description="Free text search query")
    scope: SearchScope = Field(default=SearchScope.ALL, description="Search scope")
    boolean_query: Optional[BooleanSearchQuery] = Field(
        None, description="Boolean search query"
    )
    fuzzy_matching: bool = Field(default=False, description="Enable fuzzy matching")
    fuzzy_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Fuzzy matching threshold"
    )
    sort_by: Optional[str] = Field(default="relevance", description="Sort field")
    sort_order: str = Field(default="desc", description="Sort order")
    limit: int = Field(default=50, ge=1, le=200, description="Result limit")
    offset: int = Field(default=0, ge=0, description="Result offset")
    include_highlights: bool = Field(
        default=True, description="Include search highlights"
    )

    @validator("sort_order")
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v


class SearchResult(BaseModel):
    """Individual search result."""

    item_type: str
    item_id: str
    title: str
    description: str
    relevance_score: float
    highlights: Optional[Dict[str, List[str]]] = None
    data: Dict[str, Any]


class SearchResponse(BaseModel):
    """Search response with results and metadata."""

    results: List[SearchResult]
    total_count: int
    query_time_ms: float
    suggestions: Optional[List[str]] = None
    facets: Optional[Dict[str, Dict[str, int]]] = None
    metadata: Dict[str, Any]


class SavedSearch(BaseModel):
    """Saved search configuration."""

    id: Optional[int] = None
    name: str = Field(..., description="Search name")
    description: Optional[str] = Field(None, description="Search description")
    search_request: SearchRequest = Field(..., description="Search configuration")
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    use_count: int = Field(default=0, description="Usage count")
    is_public: bool = Field(default=False, description="Public search")


@router.post("/search", response_model=SearchResponse)
async def advanced_search(
    request: SearchRequest,
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    Perform advanced search across combat log data.

    Supports free text search, boolean queries, fuzzy matching,
    and complex filtering with relevance scoring.
    """
    try:
        start_time = datetime.utcnow()
        query_api = QueryAPI(db)

        # Execute search based on type
        if request.query and not request.boolean_query:
            # Free text search
            search_results = await query_api.execute_text_search(
                query=request.query,
                scope=request.scope,
                fuzzy_matching=request.fuzzy_matching,
                fuzzy_threshold=request.fuzzy_threshold,
                limit=request.limit,
                offset=request.offset,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
            )
        elif request.boolean_query:
            # Boolean search
            search_results = await query_api.execute_boolean_search(
                boolean_query=request.boolean_query,
                scope=request.scope,
                text_query=request.query,
                limit=request.limit,
                offset=request.offset,
                sort_by=request.sort_by,
                sort_order=request.sort_order,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Either query or boolean_query must be provided"
            )

        # Calculate query time
        query_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Format results
        formatted_results = []
        for result in search_results["results"]:
            formatted_result = SearchResult(
                item_type=result["type"],
                item_id=str(result["id"]),
                title=result["title"],
                description=result["description"],
                relevance_score=result["score"],
                highlights=result.get("highlights") if request.include_highlights else None,
                data=result["data"],
            )
            formatted_results.append(formatted_result)

        # Generate suggestions if few results
        suggestions = None
        if len(formatted_results) < 5 and request.query:
            suggestions = await query_api.generate_search_suggestions(request.query)

        return SearchResponse(
            results=formatted_results,
            total_count=search_results["total_count"],
            query_time_ms=query_time,
            suggestions=suggestions,
            facets=search_results.get("facets"),
            metadata={
                "scope": request.scope,
                "fuzzy_matching": request.fuzzy_matching,
                "sort_by": request.sort_by,
                "sort_order": request.sort_order,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., description="Partial query for suggestions"),
    scope: SearchScope = Query(default=SearchScope.ALL, description="Search scope"),
    limit: int = Query(default=10, ge=1, le=20, description="Number of suggestions"),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> List[str]:
    """
    Get search suggestions for autocomplete functionality.

    Provides intelligent suggestions based on existing data
    and common search patterns.
    """
    try:
        query_api = QueryAPI(db)

        suggestions = await query_api.get_search_suggestions(
            query=query, scope=scope, limit=limit
        )

        return suggestions

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Suggestion generation failed: {str(e)}"
        )


@router.get("/search/facets")
async def get_search_facets(
    query: Optional[str] = Query(None, description="Base query for faceting"),
    scope: SearchScope = Query(default=SearchScope.ALL, description="Search scope"),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> Dict[str, Dict[str, int]]:
    """
    Get search facets for filtering options.

    Provides faceted search capabilities with counts for each facet value
    to enable drill-down filtering.
    """
    try:
        query_api = QueryAPI(db)

        facets = await query_api.get_search_facets(query=query, scope=scope)

        return facets

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Facet generation failed: {str(e)}"
        )


@router.post("/search/fuzzy")
async def fuzzy_search(
    query: str = Body(..., description="Search query"),
    scope: SearchScope = Body(default=SearchScope.ALL, description="Search scope"),
    threshold: float = Body(
        default=0.8, ge=0.0, le=1.0, description="Fuzzy matching threshold"
    ),
    max_edits: int = Body(
        default=2, ge=1, le=3, description="Maximum edit distance"
    ),
    limit: int = Body(default=50, ge=1, le=200, description="Result limit"),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> SearchResponse:
    """
    Perform fuzzy search with configurable matching parameters.

    Uses edit distance and phonetic matching to find similar terms
    even with typos or variations in spelling.
    """
    try:
        start_time = datetime.utcnow()
        query_api = QueryAPI(db)

        # Execute fuzzy search
        search_results = await query_api.execute_fuzzy_search(
            query=query,
            scope=scope,
            threshold=threshold,
            max_edits=max_edits,
            limit=limit,
        )

        query_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Format results
        formatted_results = [
            SearchResult(
                item_type=result["type"],
                item_id=str(result["id"]),
                title=result["title"],
                description=result["description"],
                relevance_score=result["score"],
                highlights=result.get("highlights"),
                data=result["data"],
            )
            for result in search_results["results"]
        ]

        return SearchResponse(
            results=formatted_results,
            total_count=search_results["total_count"],
            query_time_ms=query_time,
            suggestions=None,
            facets=None,
            metadata={
                "threshold": threshold,
                "max_edits": max_edits,
                "fuzzy_search": True,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fuzzy search failed: {str(e)}")


@router.post("/search/saved", response_model=SavedSearch)
async def save_search(
    saved_search: SavedSearch,
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    Save a search configuration for future use.

    Allows users to save complex search queries and reuse them
    with automatic execution and notification capabilities.
    """
    try:
        query_api = QueryAPI(db)

        # Set metadata
        saved_search.created_by = auth.user_id
        saved_search.created_at = datetime.utcnow()

        # Save search configuration
        saved_search_id = await query_api.save_search_configuration(saved_search)

        saved_search.id = saved_search_id
        return saved_search

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save search: {str(e)}")


@router.get("/search/saved", response_model=List[SavedSearch])
async def list_saved_searches(
    include_public: bool = Query(default=True, description="Include public searches"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    List saved searches for the current user.

    Returns user's saved searches and optionally public searches
    created by other users.
    """
    try:
        query_api = QueryAPI(db)

        saved_searches = await query_api.get_saved_searches(
            user_id=auth.user_id,
            include_public=include_public,
            limit=limit,
            offset=offset,
        )

        return saved_searches

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve saved searches: {str(e)}"
        )


@router.post("/search/saved/{search_id}/execute", response_model=SearchResponse)
async def execute_saved_search(
    search_id: int,
    override_params: Optional[Dict[str, Any]] = Body(
        None, description="Parameters to override"
    ),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    Execute a saved search with optional parameter overrides.

    Runs a previously saved search configuration with the ability
    to override specific parameters like date ranges or limits.
    """
    try:
        query_api = QueryAPI(db)

        # Get saved search
        saved_search = await query_api.get_saved_search(search_id)
        if not saved_search:
            raise HTTPException(status_code=404, detail="Saved search not found")

        # Check permissions
        if (
            saved_search.created_by != auth.user_id
            and not saved_search.is_public
        ):
            raise HTTPException(
                status_code=403, detail="Access denied to private search"
            )

        # Apply overrides
        search_request = saved_search.search_request
        if override_params:
            for key, value in override_params.items():
                if hasattr(search_request, key):
                    setattr(search_request, key, value)

        # Execute search
        search_response = await advanced_search(search_request, db, auth)

        # Update usage statistics
        await query_api.update_saved_search_usage(search_id)

        return search_response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to execute saved search: {str(e)}"
        )


@router.delete("/search/saved/{search_id}")
async def delete_saved_search(
    search_id: int,
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
):
    """
    Delete a saved search.

    Removes a saved search configuration. Only the creator
    can delete their own searches.
    """
    try:
        query_api = QueryAPI(db)

        # Get saved search to check ownership
        saved_search = await query_api.get_saved_search(search_id)
        if not saved_search:
            raise HTTPException(status_code=404, detail="Saved search not found")

        if saved_search.created_by != auth.user_id:
            raise HTTPException(
                status_code=403, detail="Can only delete your own searches"
            )

        # Delete search
        await query_api.delete_saved_search(search_id)

        return {"message": "Saved search deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete saved search: {str(e)}"
        )


@router.get("/search/popular-terms")
async def get_popular_search_terms(
    scope: SearchScope = Query(default=SearchScope.ALL, description="Search scope"),
    days: int = Query(default=30, ge=1, le=365, description="Analysis period"),
    limit: int = Query(default=20, ge=1, le=50, description="Number of terms"),
    db: DatabaseManager = Depends(),
    auth=Depends(require_read_permission),
) -> Dict[str, Any]:
    """
    Get popular search terms and trends.

    Analyzes search patterns to identify trending and popular
    search terms for discovery and analytics.
    """
    try:
        query_api = QueryAPI(db)

        popular_terms = await query_api.get_popular_search_terms(
            scope=scope, days=days, limit=limit
        )

        return {
            "popular_terms": popular_terms["terms"],
            "trending_terms": popular_terms["trending"],
            "search_volume": popular_terms["volume"],
            "metadata": {
                "scope": scope,
                "analysis_period_days": days,
                "generated_at": datetime.utcnow(),
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get popular terms: {str(e)}"
        )