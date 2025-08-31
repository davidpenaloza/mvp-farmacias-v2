"""
Simple test server to isolate the frontend-backend connection issue
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn

app = FastAPI(title="Test Pharmacy Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_frontend():
    """Serve the main web interface"""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return FileResponse(template_path)
    return {"message": "Frontend not found"}

@app.get("/api/stats")
def get_test_stats():
    """Test stats endpoint"""
    from datetime import datetime
    return {
        "total": 2802,
        "turno": 150,
        "regular": 2652,
        "communes": 346,
        "current_time": datetime.now().strftime("%H:%M:%S"),
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "test_mode"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "server": "test"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8009)
