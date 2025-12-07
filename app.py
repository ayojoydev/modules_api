from pathlib import Path
from typing import Dict, List, Optional

import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

#  Pydantic-models 


class StatCoeffs(BaseModel):
    a: float
    b: float


class ModuleDefinition(BaseModel):
    display_name: Optional[str] = None
    stats: Dict[str, StatCoeffs]


class ModuleStatsResponse(BaseModel):
    module: str
    display_name: Optional[str]
    percent: float
    stats: Dict[str, float]


class ModuleListItem(BaseModel):
    key: str
    display_name: Optional[str]
    stat_keys: List[str]


# Upload modules.json

BASE_DIR = Path(__file__).resolve().parent
MODULES_FILE = BASE_DIR / "modules.json"

MODULES: Dict[str, ModuleDefinition] = {}


def load_modules() -> None:
    global MODULES

    if MODULES:
        return  # уже загружено

    if not MODULES_FILE.exists():
        raise RuntimeError(f"Файл {MODULES_FILE} не найден")

    try:
        raw = json.loads(MODULES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ошибка парсинга {MODULES_FILE}: {e}") from e

    try:
        MODULES = {key: ModuleDefinition(**value) for key, value in raw.items()}
    except TypeError as e:
        raise RuntimeError(f"Неверная структура {MODULES_FILE}: {e}") from e


# FastAPI-application 

app = FastAPI(title="Stalcraft Modules API")


@app.on_event("startup")
async def startup_event():
    try:
        load_modules()
    except RuntimeError as e:
        print(f"[startup] Ошибка загрузки modules.json: {e}")


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/modules", response_model=List[ModuleListItem])
async def list_modules():
    """
    Список доступных модулей: ключ, display_name и список статов.
    """
    try:
        load_modules()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result: List[ModuleListItem] = []
    for key, mod in MODULES.items():
        result.append(
            ModuleListItem(
                key=key,
                display_name=mod.display_name,
                stat_keys=list(mod.stats.keys()),
            )
        )
    return result


@app.get("/module-stats", response_model=ModuleStatsResponse)
async def module_stats(
    module: str = Query(..., description="Ключ модуля из modules.json"),
    q: float = Query(..., description="Процент модуля"),
):
    try:
        load_modules()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    mod = MODULES.get(module)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Unknown module '{module}'")

    percent = q
    stats_values: Dict[str, float] = {}

    for stat_name, coeffs in mod.stats.items():
        value = coeffs.a + coeffs.b * percent
        stats_values[stat_name] = value

    return ModuleStatsResponse(
        module=module,
        display_name=mod.display_name,
        percent=percent,
        stats=stats_values,
    )
