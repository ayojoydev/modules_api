from pathlib import Path
from typing import Dict, List, Optional

import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


#  Pydantic-модели 


class StatCoeffs(BaseModel):
    a: float
    b: float


class Localization(BaseModel):
    ru: Optional[str] = None
    en: Optional[str] = None
    es: Optional[str] = None
    fr: Optional[str] = None


class ModuleDefinition(BaseModel):
    group: str                # Add-On / Deviation groups / Concept groups
    moduleType: str           # Accuracy / Control / Speed / Convenience / Concept
    localization: Localization
    stats: Dict[str, StatCoeffs]


class ModuleStatsResponse(BaseModel):
    module: str
    group: str
    moduleType: str
    display_name: Optional[str]
    percent: float
    stats: Dict[str, float]


class ModuleListItem(BaseModel):
    key: str
    group: str
    moduleType: str
    display_name: Optional[str]
    stat_keys: List[str]


#  Пути к JSON с модулями 

BASE_DIR = Path(__file__).resolve().parent

MODULE_FILES = [
    BASE_DIR / "modules_configuration/add_on_modules.json",
    BASE_DIR / "modules_configuration/concept_modules.json",
    BASE_DIR / "modules_configuration/deviation_modules.json",
]

MODULES: Dict[str, ModuleDefinition] = {}


def load_modules() -> None:
    """
    Ленивая загрузка всех JSON-файлов с модулями в глобальный словарь MODULES.

    Ожидаемый формат каждого файла:

    {
      "group": "Add-On" | "Concept groups" | "Deviation groups",
      "modules": {
        "module_key": {
          "moduleType": "...",
          "localization": { "ru": "...", "en": "...", "es": "", "fr": "" },
          "stats": {
            "stat_key": { "a": ..., "b": ... }
          }
        },
        ...
      }
    }
    """
    global MODULES

    if MODULES:
        return  # уже загружено

    for path in MODULE_FILES:
        if not path.exists():
            raise RuntimeError(f"Файл {path} не найден")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ошибка парсинга {path}: {e}") from e

        group_name = raw.get("group")
        modules_raw = raw.get("modules")

        if not isinstance(group_name, str) or not isinstance(modules_raw, dict):
            raise RuntimeError(f"Неверная структура файла {path}")

        for key, mod_data in modules_raw.items():
            if key in MODULES:
                raise RuntimeError(f"Дублирующийся ключ модуля '{key}' в файле {path}")

            # добавляем поле group внутрь описания модуля
            try:
                MODULES[key] = ModuleDefinition(group=group_name, **mod_data)
            except TypeError as e:
                raise RuntimeError(f"Неверная структура модуля '{key}' в {path}: {e}") from e


def resolve_display_name(mod: ModuleDefinition, lang: str) -> Optional[str]:
    """
    Выбирает локализованное имя модуля.
    Приоритет: запрошенный lang -> ru -> en -> es -> fr.
    """
    loc = mod.localization
    by_lang = {
        "ru": loc.ru,
        "en": loc.en,
        "es": loc.es,
        "fr": loc.fr,
    }
    name = by_lang.get(lang)
    if name:
        return name

    # Fallback-ы, если для выбранного языка строки нет
    for key in ("ru", "en", "es", "fr"):
        candidate = by_lang.get(key)
        if candidate:
            return candidate
    return None


#  FastAPI-приложение 

app = FastAPI(title="Stalcraft Modules API")


@app.on_event("startup")
async def startup_event():
    try:
        load_modules()
    except RuntimeError as e:
        print(f"[startup] Ошибка загрузки модулей: {e}")


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/modules", response_model=List[ModuleListItem])
async def list_modules(
    lang: str = Query(
        "ru",
        description="Код языка локализации (ru/en/es/fr)",
        regex="^(ru|en|es|fr)$",
    )
):
    """
    Список всех модулей с учётом локализации имени.
    """
    try:
        load_modules()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result: List[ModuleListItem] = []
    for key, mod in MODULES.items():
        display_name = resolve_display_name(mod, lang)
        result.append(
            ModuleListItem(
                key=key,
                group=mod.group,
                moduleType=mod.moduleType,
                display_name=display_name,
                stat_keys=list(mod.stats.keys()),
            )
        )
    return result


@app.get("/module-stats", response_model=ModuleStatsResponse)
async def module_stats(
    module: str = Query(..., description="Ключ модуля из JSON-файлов"),
    q: float = Query(..., description="Процент модуля"),
    lang: str = Query(
        "ru",
        description="Код языка локализации (ru/en/es/fr)",
        regex="^(ru|en|es|fr)$",
    ),
):
    """
    Рассчитать статы модуля по имени и проценту.
    Формула: value = a + b * q.
    Возвращает также группу и тип модуля.
    """
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

    display_name = resolve_display_name(mod, lang)

    return ModuleStatsResponse(
        module=module,
        group=mod.group,
        moduleType=mod.moduleType,
        display_name=display_name,
        percent=percent,
        stats=stats_values,
    )
