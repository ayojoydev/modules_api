import json
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


# ---------- Модели ----------

class StatCoeffs(BaseModel):
    a: float
    b: float


class ModuleDefinition(BaseModel):
    display_name: str
    stats: Dict[str, StatCoeffs]


class ModuleStatsResponse(BaseModel):
    module: str
    display_name: str | None
    percent: float
    stats: Dict[str, float]


class ModuleListItem(BaseModel):
    key: str
    display_name: str | None
    stat_keys: list[str]


# ---------- Загрузка modules.json ----------

BASE_DIR = Path(__file__).resolve().parent
MODULES_FILE = BASE_DIR / "modules.json"

def load_modules() -> Dict[str, ModuleDefinition]:
    with MODULES_FILE.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {k: ModuleDefinition(**v) for k, v in raw.items()}


app = FastAPI(title="Stalcraft modules API")
MODULES: Dict[str, ModuleDefinition] = load_modules()


# ---------- Эндпоинты ----------

@app.get("/modules", response_model=list[ModuleListItem])
async def list_modules():
    """
    Список доступных модулей:
    key, display_name и список статов.
    """
    out: list[ModuleListItem] = []
    for key, mod in MODULES.items():
        out.append(
            ModuleListItem(
                key=key,
                display_name=mod.display_name,
                stat_keys=list(mod.stats.keys()),
            )
        )
    return out


@app.get("/module-stats", response_model=ModuleStatsResponse)
async def module_stats(
    module: str,
    percent: float = Query(..., alias="q"),  # /module-stats?module=sniper&q=73.21
):
    """
    Рассчитать статы модуля по его имени и проценту.
    Формула: value = a + b * percent.
    """
    # на всякий случай поддержим запятую
    # если percent уже float, это игнорится, так что можно убрать
    # q = float(str(percent).replace(",", "."))

    mod = MODULES.get(module)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Unknown module '{module}'")

    stats: Dict[str, float] = {}
    for name, coeffs in mod.stats.items():
        value = coeffs.a + coeffs.b * percent
        stats[name] = value

    return ModuleStatsResponse(
        module=module,
        display_name=mod.display_name,
        percent=percent,
        stats=stats,
    )
