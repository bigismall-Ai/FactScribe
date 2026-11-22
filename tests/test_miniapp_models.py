# -*- coding: utf-8 -*-
"""tests/test_miniapp_models.py —— v4 前端契约：宿主模型＋思考等级＋自定义模型。

面板是浏览器里的原生 JS、薄壳是 Node 脚本，仓里都没有它们的测试框架，
所以按仓里既有的做法（tests/test_workbench_proposal_ui.py、
tests/test_miniapp_setup_page.py）：用字符串断言把契约钉住。

钉的六组：

1. **宿主模型目录**：薄壳接 `agent.models()`，把目录条目映射成面板条目
   （id／标签／这个模型支持哪些思考等级）；
2. **按所选模型跑**：面板选的（模型＋等级）要真的进 `agent.run({model})`，
   形状是 `{providerId, modelId, variant?, thinking:{effort}}`；
3. **失效不偷换**：模型／等级宿主不认时明确报 MODEL_UNAVAILABLE，
   不许悄悄换个模型答；
4. **自定义模型**：凭据只落插件私有 dataDir（0600），不进论文目录、
   不进页面（回包只有 hasKey）；
5. **面板接线**：思考等级下拉、添加／删除自定义模型的入口与表单都在，
   发送时带上 modelSelection；
6. **中英文案**：新词条 zh/en 都有（界面切英文不能留中文）。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "miniapp" / "miniapp" / "node" / "server.mjs").read_text(encoding="utf-8")
STATIC = ROOT / "factscribe" / "workbench" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")

# i18n 词典的两段：zh 在前，en 在后。
ZH = JS[JS.index("zh: {"):JS.index("en: {")]
EN = JS[JS.index("en: {"):]


class HostModelCatalogTests(unittest.TestCase):
    """① 宿主模型目录接进来了。"""

    def test_reads_host_catalog(self):
        self.assertIn("typeof agent.models !== 'function'", SHELL)
        self.assertIn("await agent.models()", SHELL)

    def test_catalog_entry_maps_id_label_and_efforts(self):
        self.assertIn("entry?.thinking?.efforts", SHELL)
        self.assertIn("HOST_MODEL_PREFIX + providerId + '/' + modelId", SHELL)
        self.assertIn("entry?.displayName || modelId", SHELL)

    def test_off_is_an_effort_option_when_model_allows(self):
        """variants 里有 '' 表示「能关掉思考」——那也是一个可选档。"""
        self.assertIn("variants.includes('')", SHELL)
        self.assertIn("'off'", SHELL)

    def test_default_entry_means_host_current_model(self):
        """「宿主默认」＝不指定模型，用 MCode 当前这个模型。"""
        self.assertIn("const HOST_DEFAULT_ID = 'host:default'", SHELL)
        self.assertIn("models.push({ id: HOST_DEFAULT_ID", SHELL)


class ModelSelectionTests(unittest.TestCase):
    """②③ 按所选模型与等级跑；失效就明说，不偷换。"""

    def test_run_receives_the_selection(self):
        self.assertIn("input.model = model", SHELL)
        self.assertIn("out.thinking = { effort: level }", SHELL)
        self.assertIn("variant: ''", SHELL)

    def test_selection_is_validated_against_catalog(self):
        self.assertIn("hostSelection(entry, selection.effort)", SHELL)
        self.assertIn("if (!model) {", SHELL)

    def test_unknown_model_is_reported_not_swapped(self):
        self.assertIn("MODEL_UNAVAILABLE", SHELL)
        self.assertIn("宿主不接受这个模型／思考等级了", SHELL)

    def test_failure_with_explicit_model_does_not_fall_back(self):
        """用户点了模型：这轮失败就报失败，不拿别的模型顶上。"""
        block = SHELL[SHELL.index("} catch (error) {\n      const code = String(error?.code"):]
        self.assertIn("if (model) {", block[:1200])


class CustomModelStoreTests(unittest.TestCase):
    """④ 自定义模型的凭据只落插件私有目录，不外泄。"""

    def test_store_is_plugin_data_dir(self):
        self.assertIn("const CUSTOM_MODELS_FILE = 'custom-models.json'", SHELL)
        self.assertIn("join(dataDir, CUSTOM_MODELS_FILE)", SHELL)

    def test_store_mode_is_0600(self):
        self.assertIn("mode: 0o600", SHELL)

    def test_all_write_calls_target_data_dir(self):
        calls = re.findall(r"writeCustomModels\(([^,]+),", SHELL)
        self.assertTrue(calls)
        for arg in calls:
            self.assertIn("dataDir", arg)

    def test_public_payload_has_no_api_key(self):
        block = SHELL[SHELL.index("function publicCustomModel("):SHELL.index("async function readCustomModels(")]
        self.assertIn("hasKey: Boolean(entry?.apiKey)", block)
        self.assertNotIn("apiKey: entry.apiKey", block)

    def test_custom_model_talks_openai_compatible_channel(self):
        self.assertIn("await openAiChat(entry.baseUrl, entry.model, prompt, entry.apiKey)", SHELL)
        self.assertIn("'custom-model'", SHELL)
        self.assertIn("'Bearer '", SHELL)

    def test_base_url_must_be_http(self):
        self.assertIn("url.protocol !== 'http:' && url.protocol !== 'https:'", SHELL)


class PanelModelUiTests(unittest.TestCase):
    """⑤ 面板接线：思考等级下拉、自定义模型表单、发送口径。"""

    def test_effort_select_exists(self):
        self.assertIn('id="aiEffort"', HTML)
        self.assertIn('id="aiEffortLabel"', HTML)

    def test_effort_select_wired(self):
        self.assertIn("$('#aiEffort').addEventListener('change'", JS)

    def test_effort_only_for_host_models(self):
        self.assertIn("entry.kind === 'host'", JS)

    def test_custom_model_form_exists(self):
        for mark in ('id="modalCustomModel"', 'id="cmLabel"', 'id="cmBaseUrl"',
                     'id="cmModel"', 'id="cmKey"', 'id="cmSave"'):
            self.assertIn(mark, HTML)

    def test_add_and_delete_entry_points(self):
        self.assertIn('id="aiAddModel"', HTML)
        self.assertIn('id="aiDelModel"', HTML)
        self.assertIn("$('#aiAddModel').addEventListener('click'", JS)
        self.assertIn("$('#aiDelModel').addEventListener('click'", JS)

    def test_custom_models_are_probed_not_assumed(self):
        """浏览器直连引擎时没有存凭据的地方——入口要藏起来。"""
        self.assertIn("/api/ai/custom-models", JS)
        self.assertIn("state.ai.custom = false", JS)

    def test_payload_carries_selection(self):
        self.assertIn("payload.modelSelection = { id: entry.id, effort: state.ai.effort || '' }", JS)

    def test_badge_shows_the_model_actually_used(self):
        self.assertIn("setAiSource(isAgent ? 'agent' : (isCustom ? 'custom' : 'engine'), usedLabel)", JS)
        self.assertIn("const usedModel = String((data && data.model) || '')", JS)

    def test_styles_exist(self):
        self.assertIn("#aiEffort", CSS)
        self.assertIn(".cm-field", CSS)


class I18nTests(unittest.TestCase):
    """⑥ 新词条中英各一份。"""

    KEYS = (
        "ai.modelHostDefault",
        "ai.effort", "ai.effortDefault", "ai.effortDefaultPlain", "ai.effortLevelDefault",
        "ai.effortOff",
        "ai.effortHigh", "ai.kindHost", "ai.kindCustom", "ai.kindEngine",
        "ai.addModel", "ai.delModel", "ai.delModelT", "ai.cmTitle", "ai.cmLabel", "ai.cmBaseUrl",
        "ai.cmModel", "ai.cmKey", "ai.cmSave", "ai.cmHint", "ai.cmSaved",
        "ai.cmDeleted", "ai.srcCustom",
    )

    def test_zh_has_all_keys(self):
        for key in self.KEYS:
            self.assertIn("'%s'" % key, ZH)

    def test_en_has_all_keys(self):
        for key in self.KEYS:
            self.assertIn("'%s'" % key, EN)

    def test_both_dictionaries_cover_same_keys(self):
        zh_keys = set(re.findall(r"'([a-zA-Z][\w.]*)':", ZH))
        en_keys = set(re.findall(r"'([a-zA-Z][\w.]*)':", EN))
        missing = sorted(k for k in self.KEYS if k not in zh_keys or k not in en_keys)
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
