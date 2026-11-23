import unittest

from citizen_knowledge import DOCUMENTS, knowledge_status, retrieve_knowledge


class CitizenKnowledgeTests(unittest.TestCase):
    def test_expected_documents_are_registered(self):
        self.assertEqual(knowledge_status()["documents"], 9)
        self.assertEqual(len(DOCUMENTS), 9)

    def test_waste_question_finds_waste_guidance(self):
        result = retrieve_knowledge("زباله خشک و تفکیک پسماند")
        self.assertIn("تفکیک و دفع پسماند", result)

    def test_construction_question_does_not_invent_local_rules(self):
        result = retrieve_knowledge("برای پروانه ساخت چه مدارکی لازم است؟")
        self.assertIn("متن مصوب و به‌روز", result)
        self.assertIn("حدس", result)

    def test_fee_question_returns_official_source_warning(self):
        result = retrieve_knowledge("مبلغ عوارض نوسازی چقدر است؟")
        self.assertIn("تعرفه مصوب سال جاری", result)
        self.assertIn("حدس", result)

    def test_empty_question_returns_empty_result(self):
        self.assertEqual(retrieve_knowledge("   "), "")


if __name__ == "__main__":
    unittest.main()
