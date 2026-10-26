import unittest,threading,time
import test_server as fixtures


class ProgressTests(unittest.TestCase):
    setUp=fixtures.ServiceTests.setUp
    tearDown=fixtures.ServiceTests.tearDown
    request=fixtures.ServiceTests.request
    setup_admin=fixtures.ServiceTests.setup_admin

    def test_stage_progress_and_failure_are_visible_without_losing_job_identity(self):
        self.setup_admin();entered=threading.Event();finish=threading.Event()
        def execute():
            self.app.job_progress('Downloading images','Fetching the app image.')
            entered.set();finish.wait(3)
            self.app.job_progress('Starting containers','Starting the app.')
            return {'app':'test'}
        job=self.app.job('Install test app',execute,kind='app',target='test')
        self.assertTrue(entered.wait(2))
        try:
            current=next(j for j in self.request('/api/jobs')[1] if j['id']==job['id'])
            self.assertEqual(current['state'],'running');self.assertEqual(current['stage'],'Downloading images')
            self.assertEqual(current['kind'],'app');self.assertIn('started',current)
        finally:finish.set()
        self.app.pool.shutdown(wait=True)
        current=next(j for j in self.request('/api/jobs')[1] if j['id']==job['id'])
        self.assertEqual(current['state'],'completed');self.assertIn('finished',current)
        self.assertEqual([step['stage'] for step in current['steps']],['Preparing','Downloading images','Starting containers','Complete'])

    def test_failure_preserves_last_stage_and_reported_error(self):
        self.setup_admin()
        def fail():
            self.app.job_progress('Checking disks','Validating selected disk identities.')
            raise RuntimeError('The selected disk is no longer available.')
        job=self.app.job('Create test storage',fail,kind='storage')
        self.app.pool.shutdown(wait=True)
        result=next(j for j in self.request('/api/jobs')[1] if j['id']==job['id'])
        self.assertEqual(result['state'],'failed');self.assertEqual(result['stage'],'Checking disks')
        self.assertEqual(result['error'],'The selected disk is no longer available.')
        self.assertNotIn('Complete',[step['stage'] for step in result['steps']])
