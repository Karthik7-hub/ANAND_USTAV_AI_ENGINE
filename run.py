# FILE: run.py
import uvicorn

if __name__ == "__main__":
    """
    Entry point for LOCAL DEVELOPMENT.
    Starts a Uvicorn server on port 8000 with auto-reloading enabled.
    """
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
