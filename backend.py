# File Upload Endpoint - POST /upload
# Handles multipart/form-data with file and optional source_id and version fields

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import datetime
import os
import uuid
import shutil

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory if it doesn't exist
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    source_id: Optional[str] = Form(None),
    version: Optional[str] = Form(None)
):
    """
    Upload a file with optional source_id and version fields.
    
    Parameters:
    - file: The file to upload (required)
    - source_id: Optional source identifier
    - version: Optional version string
    """
    try:
        # Validate file
        if not file:
            raise HTTPException(status_code=400, detail="No file uploaded")
        
        # Check file size
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE / (1024*1024)}MB"
            )
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Prepare response
        response_data = {
            "success": True,
            "message": "File uploaded successfully",
            "data": {
                "filename": unique_filename,
                "original_name": file.filename,
                "content_type": file.content_type,
                "size": file_size,
                "path": file_path,
                "source_id": source_id,
                "version": version,
                "uploaded_at": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(content=response_data, status_code=200)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/")
async def root():
    return {"message": "File Upload API", "endpoint": "/upload"}


if __name__ == "__main__":
    import uvicorn
    # Option 1: Disable auto-reload (recommended for development)
    # uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
    
    # Option 2: Run with reload but exclude .venv directory
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        reload_excludes=[".venv/*", "*.pyc", "__pycache__"]
    )