"""
ComfyUI 进程守护（auto restart / auto reconnect）

随 webui(webapp) 启动而启动，随其关闭而停止。
周期性探测 ComfyUI 健康端点（/system_stats），连续失败达到阈值后自动拉起 ComfyUI，
并复用 ComfyUI 当前正在使用的启动参数（从 /system_stats 的 argv 里读取并缓存），
避免在 webui 运行期间 ComfyUI 意外崩溃(crash)导致掉线。

可通过环境变量调整：
    COMFYUI_WATCHDOG_ENABLED      "1" 开启 / "0" 关闭（默认开启）
    COMFYUI_URL                   ComfyUI 地址（默认 http://127.0.0.1:8000）
    COMFYUI_PYTHON                ComfyUI 使用的 python 解释器
    COMFYUI_MAIN                  ComfyUI 的 main.py 绝对路径
    COMFYUI_INSTALL_DIR           ComfyUI 安装目录（含 ComfyUI 子目录）
    COMFYUI_BASE_DIR              ComfyUI base-directory（用户数据目录）
    COMFYUI_PORT                  ComfyUI 监听端口（默认 8000）
    COMFYUI_WATCHDOG_INTERVAL     健康检查间隔（秒，默认 15）
    COMFYUI_WATCHDOG_FAIL_THRESHOLD 连续失败多少次后重启（默认 3）
    COMFYUI_WATCHDOG_COOLDOWN     两次重启的最小间隔（秒，默认 30）
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from config import DATA_DIR

logger = logging.getLogger("comfyui_watchdog")

# -------------------------- 默认值（当前部署） --------------------------
_DEFAULT_PYTHON = r"C:\Users\Administrator\Documents\ComfyUI\.venv\Scripts\python.exe"
_DEFAULT_MAIN = r"C:\Users\Administrator\ComfyUI-Installs\ComfyUI\ComfyUI\main.py"
_DEFAULT_INSTALL_DIR = r"C:\Users\Administrator\ComfyUI-Installs\ComfyUI"
_DEFAULT_BASE_DIR = r"C:\Users\Administrator\Documents\ComfyUI"
_DEFAULT_INSTANCE_PATHS = (
    r"C:\Users\Administrator\AppData\Roaming\Comfy Desktop\instance-model-paths"
    r"\inst-1780742358629.yaml"
)

_ARGV_CACHE = Path(DATA_DIR) / "comfyui_argv.json"
_STATUS_FILE = Path(DATA_DIR) / "comfyui_watchdog.json"
_LOG_FILE = Path(DATA_DIR) / "comfyui_watchdog.log"

# 当前由本守护拉起的 ComfyUI 子进程（关闭 webui 时清理；桌面启动的不动）
_child_proc: subprocess.Popen | None = None
_stderr_handle: Any = None
_stop_event = asyncio.Event()


# -------------------------- 配置 --------------------------
def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def enabled() -> bool:
    return _env("COMFYUI_WATCHDOG_ENABLED", "1").strip() not in ("0", "false", "False", "no")


def comfy_url() -> str:
    return _env("COMFYUI_URL", "http://127.0.0.1:8000").rstrip("/")


def comfy_python() -> str:
    return _env("COMFYUI_PYTHON", _DEFAULT_PYTHON)


def comfy_main() -> str:
    return _env("COMFYUI_MAIN", _DEFAULT_MAIN)


def comfy_install_dir() -> str:
    return _env("COMFYUI_INSTALL_DIR", _DEFAULT_INSTALL_DIR)


def comfy_base_dir() -> str:
    return _env("COMFYUI_BASE_DIR", _DEFAULT_BASE_DIR)


def comfy_port() -> int:
    try:
        return int(_env("COMFYUI_PORT", "8000"))
    except ValueError:
        return 8000


def poll_interval() -> float:
    try:
        return float(_env("COMFYUI_WATCHDOG_INTERVAL", "15"))
    except ValueError:
        return 15.0


def fail_threshold() -> int:
    try:
        return int(_env("COMFYUI_WATCHDOG_FAIL_THRESHOLD", "3"))
    except ValueError:
        return 3


def cooldown() -> float:
    try:
        return float(_env("COMFYUI_WATCHDOG_COOLDOWN", "30"))
    except ValueError:
        return 30.0


def _default_launch_command() -> list[str]:
    """未缓存 argv 时的默认启动参数（与当前实例一致）。"""
    main = comfy_main()
    base = comfy_base_dir()
    port = comfy_port()
    instance_paths = _env("COMFYUI_INSTANCE_MODEL_PATHS", _DEFAULT_INSTANCE_PATHS)
    user_dir = os.path.join(base, "user")
    cmd = [
        main,
        "--feature-flag", "show_signin_button=true",
        "--base-directory", base,
        "--user-directory", user_dir,
        "--database-url", f"sqlite:///{os.path.join(user_dir, 'comfyui.db')}",
        "--port", str(port),
        "--enable-manager",
        "--input-directory", os.path.join(base, "input"),
        "--output-directory", os.path.join(base, "output"),
    ]
    if instance_paths and os.path.isfile(instance_paths):
        cmd += ["--extra-model-paths-config", instance_paths]
    return cmd


def _build_launch_command() -> list[str]:
    """拼接实际拉起 ComfyUI 的命令：优先用缓存的 argv（最贴合当前实例）。"""
    python = comfy_python()
    main = comfy_main()
    cached = _load_cached_argv()
    if cached:
        # cached[0] 是相对路径 "ComfyUI\main.py"，替换为绝对路径
        cmd = [python, main] + list(cached[1:])
    else:
        cmd = [python] + _default_launch_command()
    return cmd


# -------------------------- argv / status 缓存 --------------------------
def _load_cached_argv() -> list[str] | None:
    try:
        if _ARGV_CACHE.exists():
            data = json.loads(_ARGV_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    return None


def _save_cached_argv(argv: Any) -> None:
    try:
        if isinstance(argv, list) and argv:
            _ARGV_CACHE.write_text(json.dumps(argv, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _write_status(**updates: Any) -> None:
    data: dict[str, Any] = {}
    try:
        if _STATUS_FILE.exists():
            data = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.update(updates)
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        _STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# -------------------------- 健康检查 --------------------------
def _check_health(timeout: float = 5.0) -> tuple[bool, dict[str, Any] | None]:
    base = comfy_url()
    url = f"{base}/system_stats"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False, None
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            return True, data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return False, None


# -------------------------- 端口 / 进程处理 --------------------------
def _find_pid_on_port(port: int) -> int | None:
    """通过 netstat -ano 找监听指定端口的 PID。"""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return None
    pattern = re.compile(rf":{port}\s+\S+\s+LISTENING\s+(\d+)")
    for line in out.splitlines():
        m = pattern.search(line)
        if m:
            pid = int(m.group(1))
            if pid != os.getpid():
                return pid
    return None


def _kill_pid(pid: int) -> bool:
    """强制结束进程（Windows）。"""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, text=True, timeout=10,
        )
        return True
    except Exception:
        return False


def _terminate_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


# -------------------------- 启停 / 重启 --------------------------
def _spawn_comfyui() -> subprocess.Popen | None:
    global _child_proc, _stderr_handle
    cmd = _build_launch_command()
    cwd = comfy_install_dir()
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 关闭上一次打开的句柄，免得反复重启泄漏文件句柄
    if _stderr_handle is not None:
        try:
            _stderr_handle.close()
        except Exception:
            pass
        _stderr_handle = None
    # 保持句柄存活（父进程不关闭，避免子进程写入日志句柄失效）
    _stderr_handle = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)
    logger.info("Starting ComfyUI: %s", " ".join(cmd))
    try:
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=_stderr_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
        _child_proc = proc
        return proc
    except Exception as exc:
        logger.error("Failed to start ComfyUI: %s", exc)
        try:
            _stderr_handle.close()
        except Exception:
            pass
        _stderr_handle = None
        return None


def _restart_comfyui() -> bool:
    """杀掉当前端口上的 ComfyUI（若还挂着）并用缓存/默认命令重启。"""
    global _child_proc
    logger.warning("ComfyUI health check failed, attempting restart")
    # 1) 结束自己拉起的子进程
    _terminate_proc(_child_proc)
    _child_proc = None
    # 2) 若有残留监听（外部实例/僵尸），强制清掉端口
    pid = _find_pid_on_port(comfy_port())
    if pid is not None:
        logger.warning("Killing stale ComfyUI on port %s (pid %s)", comfy_port(), pid)
        _kill_pid(pid)
        time.sleep(2)
    # 3) 重新拉起
    proc = _spawn_comfyui()
    if proc is not None:
        _write_status(status="restarted", pid=proc.pid)
        return True
    _write_status(status="restart_failed")
    return False


# -------------------------- 主循环 --------------------------
async def start_comfyui_watchdog() -> None:
    """在 webui 内运行的后台守护任务。"""
    global _child_proc
    if not enabled():
        logger.info("ComfyUI watchdog disabled (COMFYUI_WATCHDOG_ENABLED=%s)", os.getenv("COMFYUI_WATCHDOG_ENABLED"))
        return

    _stop_event.clear()
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger.info("ComfyUI watchdog started -> %s (poll every %.0fs, restart after %d failures)",
                comfy_url(), poll_interval(), fail_threshold())
    _write_status(status="monitoring", comfy_url=comfy_url())

    last_restart = 0.0
    fail_count = 0
    was_down = False

    try:
        while not _stop_event.is_set():
            ok, data = await asyncio.to_thread(_check_health)
            if not ok:
                fail_count += 1
                logger.warning("ComfyUI health check failed (%d/%d)", fail_count, fail_threshold())
                if not was_down:
                    was_down = True
                    _write_status(status="down")
                if fail_count >= fail_threshold():
                    if (time.time() - last_restart) >= cooldown():
                        await asyncio.to_thread(_restart_comfyui)
                        last_restart = time.time()
                        fail_count = 0
                    else:
                        logger.info("Restart cooldown not elapsed, waiting")
            else:
                if was_down:
                    logger.info("ComfyUI is back online")
                    _write_status(status="online", last_reconnect=time.strftime("%Y-%m-%d %H:%M:%S"))
                    was_down = False
                fail_count = 0
                # 刷新缓存参数，确保重启时用的是当前实例参数
                if isinstance(data, dict) and isinstance(data.get("system"), dict):
                    argv = data["system"].get("argv")
                    if argv:
                        _save_cached_argv(argv)
                        # 外部（桌面）实例已在线，不认领为子进程
                        if _child_proc is not None and _child_proc.poll() is not None:
                            _child_proc = None
                _write_status(status="online")

            await asyncio.sleep(poll_interval())
    except asyncio.CancelledError:
        logger.info("ComfyUI watchdog task cancelled")
    finally:
        _stop_event.set()
        # 默认保留 ComfyUI 运行；如需随 webui 一起停止，设 COMFYUI_WATCHDOG_KEEP_ON_STOP=0
        keep_on_stop = _env("COMFYUI_WATCHDOG_KEEP_ON_STOP", "1").strip() not in ("0", "false", "no")
        if not keep_on_stop:
            await asyncio.to_thread(_terminate_proc, _child_proc)
        _child_proc = None
        logger.info("ComfyUI watchdog stopped")


async def stop_comfyui_watchdog() -> None:
    _stop_event.set()


def get_status() -> dict[str, Any]:
    try:
        if _STATUS_FILE.exists():
            return json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}
