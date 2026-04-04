#!/usr/bin/env python3
"""
T+0 可视化仪表盘
启动: python3 dashboard.py
浏览器访问 http://localhost:8888
"""
import asyncio
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from signal_engine.api.routes import router, data_loop
from signal_engine.api.collector import init_api

# ── 路径 ──
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# ── 初始化 ──
init_api()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(data_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(router)

# 静态文件 (JS/CSS/图片)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


def main():
    print("🚀 T+0 可视化仪表盘启动中...")
    print("   浏览器访问: http://127.0.0.1:8888")
    print("   按 Ctrl+C 退出\n")
    uvicorn.run(app, host="127.0.0.1", port=8888)


if __name__ == "__main__":
    main()
