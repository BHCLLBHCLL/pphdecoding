# pphdecoding

decode cradle scflow project format pph file

解析 Cradle scFLOW 项目文件 `.pph`（ZIP 容器 + CRDL-FLD 二进制 +
CADThru 快照记录流），完整格式说明见 [PPH_FORMAT_SPEC.md](PPH_FORMAT_SPEC.md)。

## 用法

```bash
python pph_parser.py tests\laptop_thermal_steady_scaled_v3_fanonly_simple.pph
python pph_parser.py 项目.pph --extract out_dir   # 解包
python pph_parser.py 项目.pph --snapshot          # sctsnapshot 完整记录树
python pph_parser.py 项目.pph --octree            # 八叉树叶子深度统计
python tests/test_pph_parser.py                   # 健全性测试（18 项）
```

## 模块

| 模块 | 职责 |
|------|------|
| `pph_parser.py` | CLI + ZIP 容器 + 成员分类 + 摘要报告 |
| `crdlfld.py` | CRDL-FLD 公共二进制层（gph/oct/mdl 共享） |
| `mdl.py` | `*_part.mdl` / `*_ridge.mdl` 面片几何 |
| `oct.py` | `*.oct` 八叉树（前序位图 → 叶子包围盒重建） |
| `sctsnapshot.py` | `main.sctsnapshot` 快照记录流 |
| `pphxml.py` | `main.xml`（索引标签方言）/ `main.prp` / `main.xenv` / `main.js` |

依赖：仅 `numpy`（Python 3.10+）。体网格 `.gph` 的深度统计在检测到
[gphdecoding](https://github.com/) 仓（同级目录）时自动调用其 `gph_model`。
