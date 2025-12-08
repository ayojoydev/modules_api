from pathlib import Path
from typing import Dict, List, Optional

import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


# Pydantic-модели


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
    moduleType: str           # Accuracy / Control / Speed / Convenience / Anomaly / Concept
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


class BuildStatsResponse(BaseModel):
    lang: str
    modules: List[ModuleStatsResponse]
    total_stats: Dict[str, float]


# Пути к JSON с модулями

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

    Формат файла:
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

            try:
                MODULES[key] = ModuleDefinition(group=group_name, **mod_data)
            except TypeError as e:
                raise RuntimeError(
                    f"Неверная структура модуля '{key}' в {path}: {e}"
                ) from e


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

    for key in ("ru", "en", "es", "fr"):
        candidate = by_lang.get(key)
        if candidate:
            return candidate
    return None


def calculate_stats(mod: ModuleDefinition, percent: float) -> Dict[str, float]:
    """
    Считает карту статов для модуля по формуле value = a + b * percent.
    """
    stats_values: Dict[str, float] = {}
    for stat_name, coeffs in mod.stats.items():
        stats_values[stat_name] = coeffs.a + coeffs.b * percent
    return stats_values


def compute_module_stats_payload(
    module_key: str,
    percent: float,
    lang: str,
) -> ModuleStatsResponse:
    """
    Внутренняя функция, которую используют и /module-stats, и /build-stats.
    """
    mod = MODULES.get(module_key)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"Unknown module '{module_key}'")

    stats_values = calculate_stats(mod, percent)
    display_name = resolve_display_name(mod, lang)

    return ModuleStatsResponse(
        module=module_key,
        group=mod.group,
        moduleType=mod.moduleType,
        display_name=display_name,
        percent=percent,
        stats=stats_values,
    )


# FastAPI-приложение

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
    Рассчитать статы одного модуля по имени и проценту.
    Формула: value = a + b * q.
    """
    try:
        load_modules()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return compute_module_stats_payload(module, q, lang)


@app.get("/build-stats", response_model=BuildStatsResponse)
async def build_stats(
    add_on: str = Query(..., description="Ключ модуля из группы Add-On"),
    add_on_q: float = Query(..., description="Процент модуля Add-On"),
    deviation: str = Query(..., description="Ключ модуля из группы Deviation"),
    deviation_q: float = Query(..., description="Процент модуля Deviation"),
    concept: str = Query(..., description="Ключ модуля из группы Concept"),
    concept_q: float = Query(..., description="Процент модуля Concept"),
    lang: str = Query(
        "ru",
        description="Код языка локализации (ru/en/es/fr)",
        regex="^(ru|en|es|fr)$",
    ),
):
    """
    Посчитать сборку из трёх модулей:
    - один из Add-On,
    - один из Deviation groups,
    - один из Concept groups.

    Возвращает:
    - список трёх ModuleStatsResponse,
    - total_stats — сумму всех статов по ключам.
    """
    try:
        load_modules()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Считаем каждый модуль отдельно
    add_on_stats = compute_module_stats_payload(add_on, add_on_q, lang)
    deviation_stats = compute_module_stats_payload(deviation, deviation_q, lang)
    concept_stats = compute_module_stats_payload(concept, concept_q, lang)

    # Проверяем, что группы соответствуют ожиданию
    if add_on_stats.group != "Add-On":
        raise HTTPException(
            status_code=400,
            detail=f"Module '{add_on}' не из группы Add-On (group={add_on_stats.group})",
        )
    if deviation_stats.group != "Deviation":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Module '{deviation}' не из группы Deviation "
                f"(group={deviation_stats.group})"
            ),
        )
    if concept_stats.group != "Concept":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Module '{concept}' не из группы Concept "
                f"(group={concept_stats.group})"
            ),
        )

    # Агрегируем статы
    total_stats: Dict[str, float] = {}
    for m in (add_on_stats, deviation_stats, concept_stats):
        for stat_name, value in m.stats.items():
            total_stats[stat_name] = total_stats.get(stat_name, 0.0) + value

    return BuildStatsResponse(
        lang=lang,
        modules=[add_on_stats, deviation_stats, concept_stats],
        total_stats=total_stats,
    )
