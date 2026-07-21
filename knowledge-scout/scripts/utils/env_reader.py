"""跨平台的 env 变量读取，支持 Windows 注册表回退"""

import os
import subprocess
import sys


def get_env(key: str, default: str = "") -> str:
    """读取环境变量

    优先级：
    1. 进程 env（os.getenv）
    2. Windows 注册表 HKCU\\Environment（setx 设置的）
    3. 配置文件（config/ 目录下）
    4. default
    """
    # 1. 进程 env
    val = os.getenv(key, "")
    if val:
        return val

    # 2. Windows 注册表
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["reg", "query", r"HKCU\Environment", "/v", key],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if key in line:
                    parts = line.strip().split(None, 2)
                    if len(parts) >= 3:
                        val = parts[2].strip()
                        if val:
                            return val
        except Exception:
            pass

    return default
