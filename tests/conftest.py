# -*- coding: utf-8 -*-
"""tests/conftest.py —— 全仓测试的公共闸门。

条目 32：**跑测试不该在测试机上弹访达窗口**。

`factscribe.workbench.actions.open_project_dir` 会调 macOS 的 `open`。
仓里所有测试都设 `FACTSCRIBE_NO_OPEN=1`，那个函数就只回报路径、不真开
（真实使用不受影响——那个环境变量只有测试与端到端脚本会设）。

这里用 `setdefault`：谁想在自己的环境里真开（比如手工验一次 Finder 跳转），
可以先 `export FACTSCRIBE_NO_OPEN=` 覆盖掉。
"""
from __future__ import annotations

import os

os.environ.setdefault("FACTSCRIBE_NO_OPEN", "1")
