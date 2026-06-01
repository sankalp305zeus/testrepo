"""Entry point: uvicorn src.api.main:app (used by Makefile and Docker)."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
