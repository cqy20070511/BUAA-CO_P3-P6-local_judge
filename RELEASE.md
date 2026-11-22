# 发布说明 · v1.0.0

日期：2026-11-22

## 这是什么

北航计组 P3—P6 本地网页评测器的首个整理版本：

- P3：BASE + E01—E25，26 个题组、283 点，Logisim 2.7.1 `.circ`；
- P4：14 道加指令练习 + 2025 真题，18 个题组、60 点；
- P5：40 题、960 点；
- P6：39 题、936 点；
- 合计 123 个题组、2239 个测试点。

## 发布资产

| 文件 | 用途 |
|---|---|
| `BUAA-CO-P3-P6-Local-Judge.zip` | **源码仓库包**：README、服务端、前端、P3/P4 测试、生成器、文档、截图；P5/P6 派生测试需运行 `prepare_data.py` 生成 |
| `P3_P4_P5_P6_网页改版_完整包.zip` | **完整运行包**：包含 P3/P4/P5/P6 全部测试点，解压即可启动，适合作为 Release 附件 |

校验值见 `CHECKSUMS.txt`。

## 快速验证

```powershell
# 源码仓库
python prepare_data.py
python server.py
# 打开 http://127.0.0.1:8766

# 完整包：解压后
.\P3_P4_P5_P6上机练习与评测\启动评测机.cmd
```

已验证：

- P3 BASE 4 / 4 AC（约 1.8 s）；
- P4-Q01 3 / 3 AC，P4-SPE 7 / 7，CABC 5 / 5，LHBOC 5 / 5，MIXED 1 / 1；
- P5-Q01 24 / 24 AC；
- P6-Q11 原平台编码 24 / 24 AC；
- 题库 123 题，页面无控制台异常。

## 上传到 GitHub

### 1. 源码仓库

```powershell
# 解压 BUAA-CO-P3-P6-Local-Judge.zip
cd BUAA-CO-P3-P6-Local-Judge
git init
git add .
git commit -m "P3-P6 local judge: Logisim + Verilog web UI"

# 在 GitHub 新建空仓库后
git branch -M main
git remote add origin https://github.com/<user>/BUAA-CO-P3-P6-Local-Judge.git
git push -u origin main
```

注意：`/tests/`、`/p5/tests/` 已被 `.gitignore` 忽略，克隆后需要运行一次 `python prepare_data.py`。

### 2. Release

1. 在仓库页面点 **Releases → Draft a new release**；
2. Tag 填 `v1.0.0`，标题填 `P3-P6 本地评测器 v1.0.0`；
3. 上传 `P3_P4_P5_P6_网页改版_完整包.zip` 作为附件；
4. 把本文件的“这是什么 / 快速验证”两节粘到说明里，发布。

## 已知限制

- P3 评测器只支持单一 32 位 RAM（4096 字，有效 3072 字）和课程 8 输出接口；四块 8 位 RAM 分银行的电路会报“存储器尺寸不匹配”，需要改电路或适配判题器。
- P3 的 E01—E25 和 P4 的 14 道练习是练习编码，不是官方原题编码。
- P5/P6 测试由 `prepare_data.py` 生成，约 87 MB，不提交 Git。
- 结果只代表本包练习标准，不代表官方隐藏测试。
