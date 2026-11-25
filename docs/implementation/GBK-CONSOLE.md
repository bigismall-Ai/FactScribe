# 控制台编码降级（非 UTF-8 控制台上人读输出不许把命令自己搞崩）

## 一、缺口：中文 Windows 上人读命令直接 exit 4

Windows 真机（10.0.1.9，ACP=936 / gb2312，区域 zh-CN）实测：

    > python -m factscribe doctor examples/minimal
    factscribe: 工具内部错误：UnicodeEncodeError: 'gbk' codec can't encode
    character '\\u2713' in position 113: illegal multibyte sequence
    （退出码 4）

原因：中文 Windows 的本地编码是 gbk/cp936，**编不出**人读输出里的装饰
字符（`✓` / `✗` / `↔`）。`print()` 撞上就抛
`UnicodeEncodeError`，命令层把它当成「工具内部错误」→ 退成 **exit 4**，
而不是这条命令本来的判定码与退出码。真机上全量 1798 例里 12 条红由它引起
（doctor / review / mirror / tide / fonts 这几条人读命令）。

## 二、修法：降级的是字符，不是命令的判定

新模块 `factscribe/console.py`，CLI 入口（`factscribe/cli.py::main`）统一调用
`safe_stdio()`：给 stdout/stderr 装一个自定义的**编码错误处理器**。

* 编不出来的字符换**同义 ASCII**（不是问号——问号分不清「通过」与「失败」）：
  `✓`→`v`、`✗`→`x`、`↔`→`<->`、`⇒`→`=>`、`⊆`→`<=`、`«`→`<<`、`»`→`>>`、`²`→`^2`；
  表外的字符换 `?`（不炸就行）。
* **编码不动**：流仍用它自己的编码（中文 Windows 上就是 cp936），所以重定向
  到文件的中文还是那个编码，外部读它的工具不用改。
* 结构化输出（`--json`）**内容不许因此改变**：载荷里没有编不出来的
  字符时，`--json` 在两种编码下**逐字相同**（用例锁住，见第四节）。
* macOS / Linux 的流本来就是 UTF-8，装上这套处理器**不改变任何一个字节**
  （UTF-8 能编下所有字符，处理器根本不会被叫醒）。

## 三、为什么不直接改成 ASCII 装饰字符

把 `✓` 换成 `OK` 也能不崩，但那是**所有平台**都换——macOS / Linux
现在看着好好的输出会变样，属既有行为回退。这里改成「按需降级」：UTF-8 的
控制台一个字不动，非 UTF-8 的控制台才降级。

## 四、测试（`tests/test_console_encoding.py`，7 例）

做法是平台无关的：把子进程的 stdout/stderr 编码设成 `gbk`（与中文 Windows
的 cp936 同一个编解码器，Python 自带，本机 macOS／Linux 也有）。

* `doctor` 在 gbk 控制台下 **exit 0**（真机修前是 exit 4）；装饰字符变 `v`，
  中文一字不动；
* `doctor` / `fonts` / `review` / `tide` / `mirror-check` 一律**不许 exit 4**，
  stderr 里不许有 `UnicodeEncodeError` / `Traceback`；
* `audit --json` 在 gbk 与 utf-8 两种编码下**文本逐字相同**、解析结果相同、
  退出码相同；
* UTF-8 控制台下的输出**一字不改**（`✓ Python` 还在，`v Python` 不在）；
* 降级表本身：装饰字符映射到同义 ASCII，表外字符换问号，UTF-8 文本不受影响。

**见红再改绿**：同一份新用例指向修前基点（`88d757d`）跑 → 6 红（1 error ＋ 5 failures，
报错正是 `UnicodeEncodeError: 'gbk' codec can't encode character '\\u2713'` 与 `'\\u2194'`）；
修后全绿。Windows 真机复验读数见同批的《FactScribe Windows 真机验证报告》。

## 五、边界

* 本条只管**人读输出**。`--json` 的载荷按现有口径打印（`ensure_ascii=False`），
  流的编码是环境的事，本条不替用户改。
* MCP 服务（`factscribe mcp`）的 stdout 是 JSON-RPC 协议通道（协议要求 UTF-8），
  **不在本条范围内**：中文 Windows 上那条通道的编码问题另议。
* 未推远端、未建 PR、未动 origin/main 与其它工作树。
