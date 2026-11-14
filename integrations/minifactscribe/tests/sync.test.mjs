// 一套界面：网页和 MiniApp 必须是同一份文件。
// 源在 factscribe/web/，插件里的是拷贝；这里钉死「不许各自改各自的」。

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const FILES = ['index.html', 'app.js', 'app.css'];

for (const name of FILES) {
  test('界面文件同步：' + name, () => {
    const canonical = readFileSync(new URL('../../../factscribe/web/' + name, import.meta.url), 'utf8');
    const bundled = readFileSync(new URL('../miniapp/client/' + name, import.meta.url), 'utf8');
    assert.equal(bundled, canonical,
      name + ' 两边不一致；改 factscribe/web/ 后要跑 scripts/sync-miniapp-ui.sh');
  });
}

test('界面只有一份：插件里不再有自己的 styles.css', () => {
  assert.throws(() => readFileSync(new URL('../miniapp/client/styles.css', import.meta.url)), /ENOENT/);
});
