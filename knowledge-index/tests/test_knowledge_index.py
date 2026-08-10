from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knowledge_index.database import build_database, database_stats, search_database
from knowledge_index.parsers import parse_chat, parse_srt

CHAT_SAMPLE = """\
余梓聪(ywx1354265)\t2025-06-04 09:01:07
@陈丽莉 @王贺 这个群是7月迭代二PE解决方案国家层适配新建需求哈
郭仕华(g30076000)\t2025-06-04 14:05:56
@王贺 发下昨天的那个doc？
这条消息还有第二行
王贺(w00855222)\t2025-06-04 14:08:07
ok
"""

CONTACT_SAMPLE = """\
郭仕华(g30076000)  2026-05-08 14:17:46
[图片]军哥，IR20260414000522这个我看RR清单是迭代二，但是需求交接又写的迭代一
邓文军(dwx1476503)  2026-05-08 14:18:26
这个是不是慧婷写错了 是迭代二的
"""

SRT_SAMPLE = """\
1
00:00:01,000 --> 00:00:05,000
这次讨论贷款审批流程

2
00:00:06,000 --> 00:00:09,000
以及后续规则修改

3
00:01:20,000 --> 00:01:24,000
这是另一个时间段
"""

VARIABLE_PRECISION_SRT_SAMPLE = """\
1
0:00:00 --> 0:00:11,957334
.

2
0:00:11,957334 --> 0:00:23,914667
呃，这边这边。

3
0:00:23,914667 --> 0:00:35,872001
。

4
0:00:35,872001 --> 0:00:47,829334
昨天迭代测试还有问题
"""


class KnowledgeIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_parse_multiline_chat(self) -> None:
        path = self.root / "固定群" / "测试群(123).txt"
        path.parent.mkdir()
        path.write_text(CHAT_SAMPLE, encoding="utf-8")
        recognized, iterator = parse_chat(path, self.root)
        documents = list(iterator)
        self.assertTrue(recognized)
        self.assertEqual(3, len(documents))
        self.assertEqual("郭仕华", documents[1].sender_name)
        self.assertEqual("g30076000", documents[1].sender_id)
        self.assertIn("第二行", documents[1].text)
        self.assertEqual("固定群", documents[1].category)

    def test_srt_grouping_uses_time_gap(self) -> None:
        path = self.root / "meeting.srt"
        path.write_text(SRT_SAMPLE, encoding="utf-8")
        documents = list(parse_srt(path, self.root))
        self.assertEqual(2, len(documents))
        self.assertEqual(1.0, documents[0].audio_start)
        self.assertEqual(9.0, documents[0].audio_end)
        self.assertIn("规则修改", documents[0].text)

    def test_srt_accepts_variable_precision_and_ignores_punctuation(self) -> None:
        path = self.root / "2025-10-29 08-55-37.srt"
        path.write_text(VARIABLE_PRECISION_SRT_SAMPLE, encoding="utf-8")
        documents = list(parse_srt(path, self.root))
        self.assertEqual(1, len(documents))
        self.assertAlmostEqual(11.957334, documents[0].audio_start)
        self.assertAlmostEqual(47.829334, documents[0].audio_end)
        self.assertEqual("呃，这边这边。 昨天迭代测试还有问题", documents[0].text)

    def test_build_and_search_homophone(self) -> None:
        history = self.root / "HistoryRecord" / "联系人"
        history.mkdir(parents=True)
        (history / "邓文军(dwx1476503).txt").write_text(
            CONTACT_SAMPLE, encoding="utf-8"
        )
        meetings = self.root / "meetings"
        meetings.mkdir()
        (meetings / "审批.srt").write_text(SRT_SAMPLE, encoding="utf-8")
        (meetings / "审批.txt").write_text("这份同名文本不应重复导入", encoding="utf-8")
        database = self.root / "knowledge.db"

        counts = build_database([self.root / "HistoryRecord", meetings], database)
        self.assertEqual(4, counts["total"])
        self.assertEqual({"chat": 2, "meeting": 2}, database_stats(database)["by_type"])

        results = search_database(database, "带宽审批", limit=5, context=0)
        self.assertTrue(results)
        self.assertIn("贷款审批", results[0]["text"])
        self.assertIn("pinyin", results[0]["matched_by"])

        literal_pinyin = search_database(database, "dai kuan shen pi", context=0)
        self.assertIn("贷款审批", literal_pinyin[0]["text"])

        initials = search_database(database, "dksp", context=0)
        self.assertIn("贷款审批", initials[0]["text"])
        self.assertIn("initials", initials[0]["matched_by"])

        code_results = search_database(database, "IR20260414000522", context=1)
        self.assertEqual("郭仕华", code_results[0]["sender_name"])
        self.assertEqual(1, len(code_results[0]["context_after"]))

        sender_results = search_database(database, "g30076000", context=0)
        self.assertEqual("郭仕华", sender_results[0]["sender_name"])

        meeting_results = search_database(
            database, "审批", source_type="meeting", context=0
        )
        self.assertTrue(meeting_results)
        self.assertTrue(
            all(item["source_type"] == "meeting" for item in meeting_results)
        )

        chat_results = search_database(database, "迭代", source_type="chat", context=0)
        self.assertTrue(chat_results)
        self.assertTrue(all(item["source_type"] == "chat" for item in chat_results))


if __name__ == "__main__":
    unittest.main()
