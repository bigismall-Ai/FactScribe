"""
factscribe_legal —— 给 FactScribe 接上「法律」这一维度的第三方集成。

设计原则（沿用上游 integrations/minifactscribe 的先例）：
  * **不改上游任何代码**：独立包，独立目录，独立退出码契约；
  * 上游管「数字绑定到事实」，本包管「事实的来源是法条、且这个数字真的出自那条法条」。

两层分工：
  FactScribe      正文 \\fact{A1} ⇒ 该句数字必须落在 A1 的值域；source_sha256 现算比对
  factscribe_legal  A1.source 指向法条 ⇒ 该法条必须在参考日生效，且其官方 XML 哈希未变，
                     且 A1 的值确实出现在该法条的官方正文里（含法文数字词：trente-cinq → 35）

用法见 CLI：factscribe-legal fetch / factscribe-legal verify
"""
__version__ = "0.1.0"

from .provisions import Provision, load_corpus, fr_number_to_int  # noqa: F401

__all__ = ["Provision", "load_corpus", "fr_number_to_int", "__version__"]
