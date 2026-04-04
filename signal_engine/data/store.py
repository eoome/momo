"""
JSON 持久化工具函数
统一管理 data/ 目录下的读写
"""
import json
import os
import logging

from signal_engine.config import DATA_DIR

log = logging.getLogger("signal_engine.data")


def ensure_data_dir():
    """确保 data 目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json(filename: str, default=None):
    """从 data/ 加载 JSON 文件"""
    if default is None:
        default = {}
    path = os.path.join(DATA_DIR, filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Load {path} failed: {e}")
    return default


def save_json(filename: str, data):
    """保存 JSON 到 data/ 目录"""
    ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"Save {path} failed: {e}")
