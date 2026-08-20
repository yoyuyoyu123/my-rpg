"""本机后端配置：让用户无需手动打开 .env 文件即可保存 provider key。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import ENV_FILE, Settings, get_settings
from app.domain.providers import PROVIDERS, requires_key
from app.schemas.config import ConfigProvider, ConfigResponse, ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["本机配置"])

_KEY_FIELDS = {
    "deepseek": ("deepseek_api_key", "clear_deepseek"),
    "zhipu": ("zhipu_api_key", "clear_zhipu"),
    "siliconflow": ("siliconflow_api_key", "clear_siliconflow"),
    "openrouter": ("openrouter_api_key", "clear_openrouter"),
}


def _require_local_request(request: Request) -> None:
    """API key 写入只允许本机浏览器，避免 LAN 上的页面盗写密钥。"""
    host = (request.client.host if request.client else "").lower()
    if host not in {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}:
        raise HTTPException(status_code=403, detail="只能在运行后端的这台电脑上修改 API 配置")


def _mask(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "已配置"
    return value[:4] + "••••" + value[-4:]


def _read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8").splitlines()


def _write_env(updates: dict[str, str | None]) -> None:
    """保留 .env 中的注释和其它配置，只替换允许由 UI 管理的字段。"""
    lines = _read_env_lines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else ""
        if key in updates:
            seen.add(key)
            value = updates[key]
            output.append(f"{key}={value or ''}")
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value or ''}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _providers(settings: Settings) -> list[ConfigProvider]:
    result: list[ConfigProvider] = []
    for provider in PROVIDERS.values():
        raw = settings.key_for(provider.id)
        result.append(ConfigProvider(
            id=provider.id,
            label=provider.label,
            configured=(not requires_key(provider.id)) or bool(raw),
            key_hint=_mask(raw),
            note=provider.note,
        ))
    return result


@router.get("", response_model=ConfigResponse, summary="读取本机后端配置状态")
def get_config(request: Request, settings: Settings = Depends(get_settings)) -> ConfigResponse:
    _require_local_request(request)
    return ConfigResponse(providers=_providers(settings), default_provider=settings.default_provider)


@router.post("", response_model=ConfigResponse, summary="保存本机后端配置")
def save_config(
    payload: ConfigUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ConfigResponse:
    _require_local_request(request)
    updates: dict[str, str | None] = {}
    for provider_id, (key_field, clear_field) in _KEY_FIELDS.items():
        if getattr(payload, clear_field):
            updates[key_field.upper()] = ""
        else:
            value = getattr(payload, key_field)
            # 空输入表示“留着原 key”，避免刷新配置面板时误清空。
            if value and value.strip():
                clean = value.replace("\r", "").replace("\n", "").strip()
                updates[key_field.upper()] = clean
    if payload.default_provider:
        updates["DEFAULT_PROVIDER"] = payload.default_provider

    if not updates:
        return ConfigResponse(providers=_providers(settings), default_provider=settings.default_provider)

    _write_env(updates)
    get_settings.cache_clear()
    fresh = get_settings()
    return ConfigResponse(providers=_providers(fresh), default_provider=fresh.default_provider)
