import unittest
from website.training_trends import training_summary


def records(scores, defects=()):
    return [{'score': score, 'defects': list(defects)} for score in scores]


class TrainingTrendsTest(unittest.TestCase):
    def test_sparse_and_unscorable_records_do_not_invent_progress(self):
        self.assertIn('暂无有效评分', training_summary([])['分数变化'])
        self.assertIn('暂无有效评分', training_summary(records([None]))['分数变化'])
        self.assertIn('1 次评分', training_summary(records([0, None]))['分数变化'])
        self.assertIn('不足以判断', training_summary(records([90, 60]))['分数变化'])
        self.assertIn('范围 0–80', training_summary(records([0, 40, 80]))['分数变化'])

    def test_equal_nonoverlapping_windows_and_missing_scores(self):
        self.assertIn('上升 10.0 分', training_summary(records([50]*3 + [None] + [60]*3))['分数变化'])
        self.assertIn('下降 10.0 分', training_summary(records([80]*3 + [70]*3))['分数变化'])
        self.assertIn('基本持平', training_summary(records([80]*3 + [81]*3))['分数变化'])
        self.assertIn('下降', training_summary(records([0, 0, 90, 90, 90, 80, 80, 80]))['分数变化'])

    def test_defects_count_records_not_mentions_and_ignore_negations(self):
        data = records([50]*7, ['疑似咬边：凹槽，未见裂纹。', '疑似咬边：需复查。', '未见明显气孔：表面较完整。'])
        summary = training_summary(data)
        self.assertEqual(summary['关注缺陷'], '近5次：疑似咬边 5次。')
        self.assertIn('凹槽', summary['下次重点'])
        self.assertNotIn('裂纹', summary['关注缺陷'])

    def test_no_known_defect_does_not_mean_quality_pass(self):
        summary = training_summary(records([80]*6, ['无法判断：不能确认未焊透。']))
        self.assertIn('暂无明确', summary['关注缺陷'])
        self.assertNotIn('合格', ''.join(summary.values()))


if __name__ == '__main__':
    unittest.main()
