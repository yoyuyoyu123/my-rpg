"""Windows graphical launcher and web settings deep-link contract."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = (ROOT / "launcher.ps1").read_text(encoding="utf-8")
VBS = (ROOT / "Start Wuji RPG.vbs").read_text(encoding="utf-8")
SETUP = (ROOT / "backend" / "setup.ps1").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_double_click_entry_hides_terminal_without_autostart() -> None:
    assert "-WindowStyle Hidden" in VBS
    assert "launcher.ps1" in VBS
    assert "-AutoPlay" not in VBS
    assert "-AutoPlay" not in LAUNCHER
    assert "BeginInvoke" not in LAUNCHER


def test_launcher_has_safe_lifecycle_and_setup_controls() -> None:
    assert "Start-WujiBackend" in LAUNCHER
    assert "Get-OwnedServerProcess" in LAUNCHER
    assert "No backend owned by this launcher" in LAUNCHER
    assert "Install / Repair" in LAUNCHER
    assert "Create Desktop Shortcut" in LAUNCHER
    assert "app.main:app" in LAUNCHER
    assert "--reload" not in LAUNCHER
    assert "pip install" in SETUP
    assert "if ($script:playButton) { $script:playButton.Enabled = $true }" in LAUNCHER
    assert "$script:stopPendingId = 0" in LAUNCHER
    assert "Do not wait synchronously on the WinForms UI thread" in LAUNCHER
    assert "MessageBox]::Show($form" in LAUNCHER
    status_fn = LAUNCHER[LAUNCHER.index("function Update-LauncherStatus"):LAUNCHER.index("function Start-WujiBackend")]
    stop_fn = LAUNCHER[LAUNCHER.index("function Stop-WujiBackend"):LAUNCHER.index("function Start-WujiSetup")]
    assert "Test-WujiHealth" not in status_fn
    assert "Test-WujiHealth" not in stop_fn


def test_launcher_settings_deep_link_opens_existing_web_config() -> None:
    assert "?launcher=settings" in LAUNCHER
    assert "function applyLauncherRoute(" in INDEX
    assert "setTab('be')" in INDEX
    assert "loadBackendConfig()" in INDEX
    assert "saveBackendConfig()" in INDEX


def test_streaming_placeholder_survives_postprocessing() -> None:
    """SSE text must stay visible while option/state/agency passes finish."""
    run_start = INDEX.index("async function _runTurn(")
    run = INDEX[run_start:]
    assert "var typ=addTyp(), live=null" in run
    assert "finally { live.remove(); }" not in run
    keep_until_final = run.index("if(live){live.remove();live=null;}")
    render_final = run.index("renderNar(reply,HIST.length-1);")
    assert keep_until_final < render_final
    assert "if(live)live.remove();" in run
