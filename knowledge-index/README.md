# Personal Knowledge Index

这是一个完全本地运行的个人知识检索工具。首版支持：

- 递归导入聊天软件导出的 `HistoryRecord/**/*.txt`
- 导入会议字幕 `.srt`，按时间窗口自动合并
- 同名 `.srt` 解析成功时，不重复导入普通转写 `.txt`
- SQLite FTS5 全文检索
- jieba 中文分词、汉字二元组、全拼和拼音首字母召回
- 搜索结果定位到聊天文件、发送人、消息时间或音频时间点
- 群名、联系人姓名和工号自动进入索引，无需人工标注

所有数据和索引均保存在本机，不调用在线模型或 API。

## 安装

需要 Python 3.10 或更高版本。

### Windows

```powershell
cd knowledge-index
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\Activate.ps1
```

### Linux/macOS

```bash
cd knowledge-index
python3 -m venv .venv
.venv/bin/python -m pip install -e .
source .venv/bin/activate
```

## 建立索引

可以一次传入一个或多个文件夹：

```powershell
knowledge-search build "D:\资料\HistoryRecord" "D:\资料\会议转写" --db "D:\资料\knowledge.db"
```

每次 `build` 都会在临时数据库中完整重建索引，成功后再替换旧数据库，因此中途失败不会破坏已有索引。

支持的聊天消息格式：

```text
郭仕华(g30076000)  2026-05-08 14:17:46
[图片]军哥，IR20260414000522这个我看RR清单是迭代二……
邓文军(dwx1476503)  2026-05-08 14:18:26
这个是不是慧婷写错了 是迭代二的
```

发送人标题中的分隔符可以是 Tab 或连续空格，消息正文可以有多行。

## 搜索

```powershell
knowledge-search search "IR20260414000522 迭代" --db "D:\资料\knowledge.db"
knowledge-search search "带宽审批" --db "D:\资料\knowledge.db" --limit 20
```

第二个例子会同时搜索原汉字与拼音，因此可能召回包含“贷款审批”等同音内容。汉字命中的权重高于拼音命中，减少常见同音字造成的噪声。

默认会显示命中聊天消息前后各一条消息。可以调整或关闭：

```powershell
knowledge-search search "PE规则" --db knowledge.db --context 2
knowledge-search search "PE规则" --db knowledge.db --context 0
```

输出 JSON，便于以后接 Web 页面或 RAG：

```powershell
knowledge-search search "PE规则" --db knowledge.db --json
```

查看索引统计：

```powershell
knowledge-search stats --db knowledge.db
```

## 当前边界

- 拼音用于扩大召回范围，不表示两个同音词语义相同。
- 不做 ASR 纠错，也不调用大模型生成答案。
- 图片、文件等占位消息会保留，但不会识别附件内容。
- 首版以本地单用户检索为目标；后续需要语义检索时，可以用文档 ID 将结果与 Qdrant 向量索引合并。
