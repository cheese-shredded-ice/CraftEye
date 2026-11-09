import unittest
from unittest.mock import Mock, patch

from PIL import Image
from ai_analysis import AIConfig
from ai_ui import submit_analysis


class AnalysisSubmissionTest(unittest.TestCase):
    def test_missing_key_does_not_send_and_inflight_job_prevents_duplicates(self):
        state, executor = {}, Mock()
        image = Image.new('RGB', (50, 50))
        args = ('image', 'source', image, image, [], [])
        with patch('ai_ui.st.session_state', state), patch('ai_ui.get_executor', return_value=executor), patch('ai_ui.current_config', return_value=AIConfig('')):
            self.assertFalse(submit_analysis(*args))
        executor.submit.assert_not_called()
        with patch('ai_ui.st.session_state', state), patch('ai_ui.get_executor', return_value=executor), patch('ai_ui.current_config', return_value=AIConfig('test')):
            self.assertTrue(submit_analysis(*args))
            self.assertFalse(submit_analysis(*args))
            executor.submit.assert_called_once()
            state.pop('_ai_job_image')
            state['_ai_result_image'] = {'previous': True}
            self.assertTrue(submit_analysis(*args))
            self.assertNotIn('_ai_result_image', state)
            self.assertEqual(executor.submit.call_count, 2)
            self.assertNotEqual(executor.submit.call_args_list[0].args[1], executor.submit.call_args_list[1].args[1])


if __name__ == '__main__':
    unittest.main()
