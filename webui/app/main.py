from pathlib import Path
from typing import List, Optional

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    auth_enabled,
    check_password,
    clear_session_cookie,
    is_authenticated,
    make_session_cookie,
    require_auth,
)
from .converter import convert_bytes, convert_url

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="MarkItDown Web UI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(md_session: Optional[str] = Cookie(default=None)):
    if not is_authenticated(md_session):
        return RedirectResponse(url="/login")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(md_session: Optional[str] = Cookie(default=None)):
    if is_authenticated(md_session):
        return RedirectResponse(url="/")
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/login")
async def login(password: str = Form(...)):
    if not check_password(password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response = RedirectResponse(url="/", status_code=303)
    make_session_cookie(response)
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@app.get("/api/status")
async def status():
    return {"auth_enabled": auth_enabled()}


@app.post("/api/convert", dependencies=[Depends(require_auth)])
async def api_convert(
    files: List[UploadFile] = File(default=[]),
    url: Optional[str] = Form(default=None),
):
    if not files and not url:
        raise HTTPException(status_code=400, detail="Provide at least one file or a URL")

    results = []

    for upload in files:
        data = await upload.read()
        result = convert_bytes(upload.filename or "file", data)
        results.append(result.__dict__)

    if url:
        result = convert_url(url.strip())
        results.append(result.__dict__)

    return {"results": results}
