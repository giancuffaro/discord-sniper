import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import departments

class DepartmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.p=patch.object(departments,'OUT',Path(self.tmp.name));self.p.start();self.addCleanup(self.p.stop)
 def test_duplicate_reservation_and_role_limit(self):
  self.assertTrue(departments.reserve('daily','first','2026-09-14'))
  self.assertFalse(departments.reserve('daily','first','2026-09-14'))
  self.assertFalse(departments.reserve('daily','second','2026-09-14'))
 def test_disabled_does_not_call_api(self):
  with patch.object(departments,'config',return_value={}),patch.object(departments.observer_providers,'request') as call:
   self.assertEqual(departments.run('health',{})['status'],'disabled')
  call.assert_not_called()
 def test_reports_have_no_credentials_and_do_not_repeat(self):
  cfg={'departments':{'enabled':True},'ai_provider_keys':{'openai':'private-placeholder'}}
  with patch.object(departments,'config',return_value=cfg),patch.object(departments.observer_providers,'request',return_value={'summary':'Observed issue','findings':[],'limitations':['No broker checks']}) as call:
   result=departments.run('health',{'issues':['reader heartbeat missing']})
   self.assertEqual(result['status'],'completed')
   self.assertEqual(departments.run('health',{'issues':['reader heartbeat missing']})['status'],'duplicate_or_daily_limit')
   self.assertEqual(call.call_count,1)
  self.assertNotIn('private-placeholder',Path(result['report']).read_text())
 def test_invalid_lane_rejected(self):
  self.assertFalse(departments.save_extension_health({'lane':'../../outside'}))

if __name__=='__main__':unittest.main()
