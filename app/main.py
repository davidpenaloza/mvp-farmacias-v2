# app/main.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os

from app.services.minsal_client import get_locales, get_locales_turno
from app.services.vademecum_service import load_vademecum, search_vademecum
from app.database import PharmacyDatabase
from app.cache.redis_client import get_redis_client
from app.cache.invalidation import get_invalidation_manager, manual_cache_invalidation
from app.middleware.cache_middleware import CacheMiddleware, cache_warmup, cache_health_check
from app.agents.spanish_agent import SpanishPharmacyAgent
import json
import sqlite3
from pathlib import Path
import asyncio
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
APP_NAME = os.getenv("APP_NAME", "Farmacias de Turno + Vademécum (MVP v2)")
ENV = os.getenv("ENV", "dev")
VADEMECUM_PATH = os.getenv("VADEMECUM_PATH", "./data/vademecum_clean.parquet")

# Initialize database
db = PharmacyDatabase()

# Initialize Spanish AI Agent (will be done on startup)
spanish_agent = None

app = FastAPI(title=APP_NAME, version="0.2.0")

# Add cache middleware (temporarily disabled - sync/async compatibility)
# app.middleware("http")(CacheMiddleware(app))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for our modern frontend
app.mount("/templates/assets", StaticFiles(directory="templates/assets"), name="assets")

# Request/Response Models
class ChatPayload(BaseModel):
    message: str

class ChatSessionPayload(BaseModel):
    message: str
    session_id: Optional[str] = None

# Legacy constants (for backward compatibility)
DISCLAIMER = "Servicio informativo: no entregamos dosis, tratamientos ni diagnósticos. En urgencias, llama al 131."

REJECTION_TRIGGERS = [
    "dosis", "posología", "mg", "cada ", "frecuencia", "puedo mezclar",
    "interacción", "interacciones", "qué tomo", "que tomo", "diagnóstico", "diagnostico",
    "recetar", "recétame", "recetame", "para mi hijo", "embarazo"
]

@app.on_event("startup")
async def startup_event():
    """Initialize Redis connection, Spanish AI Agent, and warm up cache"""
    global spanish_agent
    logger.info("🚀 Starting Pharmacy Finder application...")
    
    # Initialize Redis connection
    redis_client = await get_redis_client()
    connected = await redis_client.connect()
    
    if connected:
        logger.info("✅ Redis cache system initialized")
        
        # Initialize Spanish AI Agent
        try:
            spanish_agent = SpanishPharmacyAgent()
            logger.info("✅ Spanish AI Agent initialized and ready")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Spanish AI Agent: {e}")
            spanish_agent = None
        
        # Warm up cache with popular data
        try:
            await cache_warmup()
            logger.info("🔥 Cache warmup completed")
        except Exception as e:
            logger.error(f"⚠️  Cache warmup failed: {e}")
    else:
        logger.warning("⚠️  Redis unavailable - continuing with SQLite only")
    
    logger.info("🎯 Application startup completed")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up Redis connection"""
    logger.info("🛑 Shutting down Pharmacy Finder application...")
    
    redis_client = await get_redis_client()
    await redis_client.disconnect()
    
    logger.info("✅ Application shutdown completed")

@app.get("/health")
def health():
    return {"status": "ok", "env": ENV}

@app.get("/farmacias")
def farmacias(
    region: Optional[str] = Query(None),
    comuna: Optional[str] = Query(None),
    abierto: Optional[bool] = Query(False),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        items = get_locales_turno(region=region, comuna=comuna, abierto=abierto, limit=limit)
        if not items:
            items = get_locales(region=region, comuna=comuna, limit=limit)
        return {"items": items, "source": "MINSAL"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando fuente oficial: {e}")

@app.get("/medicamentos")
def medicamentos(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
):
    items = load_vademecum(VADEMECUM_PATH)
    res = search_vademecum(items, q=q, limit=limit) if items else []
    return {"items": res, "source": "vademecum"}

# ======================================
# AI AGENT CHAT ENDPOINTS
# ======================================

@app.post("/chat")
async def chat_with_agent(payload: ChatSessionPayload):
    """
    Chat with the Spanish Pharmacy AI Agent
    Supports both session-based and stateless conversations
    """
    if not spanish_agent:
        raise HTTPException(status_code=503, detail="AI Agent not available")
    
    try:
        # Create new session if none provided
        if not payload.session_id:
            session_id = await spanish_agent.create_session()
        else:
            session_id = payload.session_id
        
        # Process message with the agent
        response = await spanish_agent.process_message(session_id, payload.message)
        
        if response.get("success"):
            return {
                "session_id": session_id,
                "reply": response.get("response", ""),
                "tools_used": response.get("tools_used", []),
                "response_time_ms": response.get("response_time_ms", 0),
                "model": response.get("model", "gpt-3.5-turbo")
            }
        else:
            return {
                "session_id": session_id,
                "reply": "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo?",
                "error": response.get("error"),
                "tools_used": [],
                "response_time_ms": 0
            }
            
    except Exception as e:
        logger.error(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"Error en el chat: {str(e)}")

@app.post("/api/chat/session")
async def create_chat_session():
    """Create a new chat session with the AI agent"""
    if not spanish_agent:
        raise HTTPException(status_code=503, detail="AI Agent not available")
    
    try:
        session_id = await spanish_agent.create_session()
        return {
            "session_id": session_id,
            "status": "created",
            "message": "Nueva sesión de chat creada"
        }
    except Exception as e:
        logger.error(f"❌ Session creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Error creando sesión: {str(e)}")

@app.post("/api/chat/message")
async def send_chat_message(
    payload: ChatPayload,
    session_id: str = Query(..., description="Session ID for the conversation")
):
    """Send a message to an existing chat session"""
    if not spanish_agent:
        raise HTTPException(status_code=503, detail="AI Agent not available")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    try:
        response = await spanish_agent.process_message(session_id, payload.message)
        return response
    except Exception as e:
        logger.error(f"❌ Message processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando mensaje: {str(e)}")

@app.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    """Get conversation history for a session"""
    if not spanish_agent:
        raise HTTPException(status_code=503, detail="AI Agent not available")
    
    try:
        summary = await spanish_agent.get_session_summary(session_id)
        return summary
    except Exception as e:
        logger.error(f"❌ History retrieval error: {e}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo historial: {str(e)}")

@app.delete("/api/chat/session/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete a chat session and its history"""
    if not spanish_agent:
        raise HTTPException(status_code=503, detail="AI Agent not available")
    
    try:
        success = await spanish_agent.delete_session(session_id)
        if success:
            return {"status": "deleted", "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"❌ Session deletion error: {e}")
        raise HTTPException(status_code=500, detail=f"Error eliminando sesión: {str(e)}")

# ======================================
# LEGACY CHAT ENDPOINT (DEPRECATED)
# ======================================

@app.post("/chat/legacy")
def chat_legacy(payload: ChatPayload):
    """
    Legacy chat endpoint (deprecated - use /chat instead)
    Kept for backward compatibility
    """
    text = (payload.message or "").lower()

    if any(t in text for t in REJECTION_TRIGGERS):
        return {
            "reply": "No puedo entregar recomendaciones médicas (p. ej. dosis o diagnósticos). "
                     "Consulta con un profesional. En caso de urgencia, llama al 131.",
            "tool_used": None,
            "disclaimers": [DISCLAIMER]
        }

    if any(k in text for k in ["farmacia", "turno", "abierta", "abierto", "dirección", "direccion", "comuna", "región", "region"]):
        return {
            "reply": "Para buscar farmacias de turno usa `/farmacias?comuna=...&abierto=true` o indica región/comuna.",
            "tool_used": "SearchFarmaciasTool",
            "disclaimers": [DISCLAIMER]
        }

    if any(k in text for k in ["medicamento", "principio activo", "paracetamol", "ibuprofeno"]):
        return {
            "reply": "Para ver fichas informativas (no prescriptivas) usa `/medicamentos?q=...`.",
            "tool_used": "LookupMedicamentoTool",
            "disclaimers": [DISCLAIMER]
        }

    return {
        "reply": "Puedo ayudarte con farmacias de turno y fichas informativas de medicamentos. "
                 "Indica tu comuna o el nombre del medicamento. No entrego dosis ni diagnósticos.",
        "tool_used": None,
        "disclaimers": [DISCLAIMER]
    }

# New endpoints for the web interface
@app.get("/")
def read_root():
    """Serve the main web interface"""
    template_path = Path(__file__).parent.parent / "templates" / "index.html"
    if template_path.exists():
        return FileResponse(template_path)
    return {"message": "Web interface not available. Use /docs for API documentation."}

@app.get("/modern")
def read_modern():
    """Serve the modern web interface with AI chat"""
    template_path = Path(__file__).parent.parent / "templates" / "index_modern.html"
    if template_path.exists():
        return FileResponse(template_path)
    return {"message": "Modern web interface not available. Use /docs for API documentation."}

@app.get("/templates/index_modern.html")
def serve_modern_template():
    """Direct access to modern template"""
    template_path = Path(__file__).parent.parent / "templates" / "index_modern.html"
    if template_path.exists():
        return FileResponse(template_path)
    return {"message": "Modern template not found"}

@app.get("/api/stats")
def get_stats():
    """Get database statistics"""
    try:
        from datetime import datetime
        stats = db.get_pharmacy_count()
        communes = db.get_all_communes()
        current_time = datetime.now().strftime("%H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")

        return {
            "total": stats["total"],
            "turno": stats["turno"],
            "regular": stats["regular"],
            "communes": len(communes),
            "current_time": current_time,
            "current_date": current_date
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {e}")

@app.get("/api/open-now")
def get_open_now_pharmacies(
    lat: Optional[float] = Query(None, description="Latitude for location-based search"),
    lng: Optional[float] = Query(None, description="Longitude for location-based search"),
    comuna: Optional[str] = Query(None, description="Commune for commune-based search"),
    radius: float = Query(5.0, description="Search radius in km")
):
    """Get pharmacies that are currently open"""
    try:
        if lat is not None and lng is not None:
            pharmacies = db.find_nearby_pharmacies_open_now(lat, lng, radius)
        elif comuna:
            pharmacies = db.find_by_comuna_open_now(comuna)
        else:
            # Get all pharmacies and filter by current time
            # This is less efficient but works as fallback
            all_pharmacies = []
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM pharmacies LIMIT 1000')  # Limit for performance
                rows = cursor.fetchall()
                all_pharmacies = [db._row_to_pharmacy(row) for row in rows]

            pharmacies = [p for p in all_pharmacies if db.is_pharmacy_currently_open(p)]

        return {
            "items": [
                {
                    "local_id": p.local_id,
                    "nombre": p.nombre,
                    "direccion": p.direccion,
                    "comuna": p.comuna,
                    "localidad": p.localidad,
                    "telefono": p.telefono,
                    "lat": p.lat,
                    "lng": p.lng,
                    "hora_apertura": p.hora_apertura,
                    "hora_cierre": p.hora_cierre,
                    "dia_funcionamiento": p.dia_funcionamiento,
                    "es_turno": p.es_turno,
                    "abierto_ahora": True
                }
                for p in pharmacies[:50]  # Limit results
            ],
            "count": len(pharmacies),
            "source": "database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding open pharmacies: {e}")

@app.get("/api/nearby")
def get_nearby_pharmacies(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(5.0, description="Search radius in km"),
    abierto: bool = Query(False, description="Only open pharmacies"),
    abierto_ahora: bool = Query(False, description="Only pharmacies open right now")
):
    """Find pharmacies near a location"""
    try:
        if abierto_ahora:
            # Use new method that checks current time
            pharmacies = db.find_nearby_pharmacies_open_now(lat, lng, radius)
        else:
            pharmacies = db.find_nearby_pharmacies(lat, lng, radius, abierto)

        return {
            "items": [
                {
                    "local_id": p.local_id,
                    "nombre": p.nombre,
                    "direccion": p.direccion,
                    "comuna": p.comuna,
                    "localidad": p.localidad,
                    "telefono": p.telefono,
                    "lat": p.lat,
                    "lng": p.lng,
                    "hora_apertura": p.hora_apertura,
                    "hora_cierre": p.hora_cierre,
                    "dia_funcionamiento": p.dia_funcionamiento,
                    "es_turno": p.es_turno,
                    "abierto_ahora": db.is_pharmacy_currently_open(p)
                }
                for p in pharmacies
            ],
            "source": "database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding nearby pharmacies: {e}")

@app.get("/api/communes")
def get_communes():
    """Get list of all communes"""
    try:
        communes = db.get_all_communes()
        return {"communes": communes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting communes: {e}")

@app.get("/api/search")
def search_pharmacies(
    comuna: Optional[str] = Query(None, description="Commune name to search in"),
    abierto: bool = Query(False, description="Only show pharmacies de turno"),
    limit: int = Query(50, description="Maximum number of results")
):
    """Search pharmacies by commune"""
    try:
        if comuna:
            pharmacies = db.find_by_comuna(comuna, only_open=abierto)
        else:
            # Return some default pharmacies
            pharmacies = []
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                if abierto:
                    cursor.execute('SELECT * FROM pharmacies WHERE es_turno = 1 LIMIT ?', (limit,))
                else:
                    cursor.execute('SELECT * FROM pharmacies LIMIT ?', (limit,))
                rows = cursor.fetchall()
                pharmacies = [db._row_to_pharmacy(row) for row in rows]

        return {
            "items": [
                {
                    "local_id": p.local_id,
                    "nombre": p.nombre,
                    "direccion": p.direccion,
                    "comuna": p.comuna,
                    "localidad": p.localidad,
                    "telefono": p.telefono,
                    "lat": p.lat,
                    "lng": p.lng,
                    "hora_apertura": p.hora_apertura,
                    "hora_cierre": p.hora_cierre,
                    "dia_funcionamiento": p.dia_funcionamiento,
                    "es_turno": p.es_turno,
                    "abierto_ahora": db.is_pharmacy_currently_open(p)
                }
                for p in pharmacies[:limit]
            ],
            "count": len(pharmacies),
            "source": "database"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching pharmacies: {e}")

# =============================================================================
# CACHE MANAGEMENT ENDPOINTS
# =============================================================================

@app.get("/api/cache/health")
async def get_cache_health():
    """Get cache system health status"""
    try:
        health_info = await cache_health_check()
        return {
            "status": "ok" if health_info.get("operations_healthy", False) else "degraded",
            "cache_system": health_info,
            "timestamp": health_info.get("timestamp")
        }
    except Exception as e:
        logger.error(f"❌ Cache health check error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "cache_system": {"status": "error"}
        }

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get detailed cache statistics"""
    try:
        redis_client = await get_redis_client()
        stats = redis_client.get_cache_stats()
        
        return {
            "redis_stats": stats,
            "cache_config": {
                "ttl_critical": redis_client.ttl_critical,
                "ttl_high": redis_client.ttl_high,
                "ttl_medium": redis_client.ttl_medium,
                "ttl_low": redis_client.ttl_low,
                "fallback_enabled": redis_client.fallback_enabled,
                "max_stale_age": redis_client.max_stale_age
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Cache stats error: {e}")
        raise HTTPException(status_code=500, detail=f"Cache stats error: {e}")

@app.post("/api/cache/invalidate")
async def invalidate_cache():
    """Manually invalidate all pharmacy cache entries"""
    try:
        result = await manual_cache_invalidation()
        
        if result["status"] == "manual_invalidation_completed":
            return {
                "status": "success",
                "message": f"Invalidated {result['invalidated']} cache entries",
                "invalidated_count": result["invalidated"],
                "timestamp": result["timestamp"]
            }
        else:
            return {
                "status": "error",
                "message": result.get("message", "Unknown error"),
                "timestamp": result.get("timestamp")
            }
    except Exception as e:
        logger.error(f"❌ Manual cache invalidation error: {e}")
        raise HTTPException(status_code=500, detail=f"Cache invalidation error: {e}")

@app.get("/api/cache/invalidation-check")
async def run_invalidation_check():
    """Run cache invalidation check and report results"""
    try:
        invalidation_manager = await get_invalidation_manager()
        result = await invalidation_manager.run_invalidation_check()
        
        return {
            "status": result["status"],
            "result": result,
            "timestamp": result.get("timestamp", asyncio.get_event_loop().time())
        }
    except Exception as e:
        logger.error(f"❌ Invalidation check error: {e}")
        raise HTTPException(status_code=500, detail=f"Invalidation check error: {e}")

@app.post("/api/cache/warmup")
async def warm_cache():
    """Manually trigger cache warmup"""
    try:
        await cache_warmup()
        return {
            "status": "success",
            "message": "Cache warmup completed",
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"❌ Cache warmup error: {e}")
        raise HTTPException(status_code=500, detail=f"Cache warmup error: {e}")
