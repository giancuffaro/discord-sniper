import unittest
from unittest.mock import patch
import observer_providers as p

class FailoverTests(unittest.TestCase):
 def setUp(self):
  p._cooldown.clear()
  self.cfg={'context_observer':{'enabled':True},'ai_provider_keys':{'openai':'dummy','gemini':'dummy'}}
 def test_success_does_not_call_backup(self):
  with patch.object(p,'request',return_value={'action':'NONE'}) as call:
   raw,_=p.read('sys','same context',self.cfg)
  self.assertEqual(call.call_count,1)
  self.assertEqual(raw['action'],'NONE')
 def test_failure_passes_identical_context_and_cools_down(self):
  with patch.object(p,'request',side_effect=[{'_error':'HTTP_429'},{'action':'NONE'},{'action':'NONE'}]) as call:
   raw,_=p.read('sys','same context',self.cfg)
   p.read('sys','next context',self.cfg)
  self.assertEqual(call.call_args_list[0].args[3:],call.call_args_list[1].args[3:])
  self.assertEqual(call.call_args_list[2].args[0],'gemini')
  self.assertEqual(len(raw['_attempts']),2)
 def test_both_fail_report_error(self):
  with patch.object(p,'request',return_value={'_error':'timeout'}):
   raw,_=p.read('sys','ctx',self.cfg)
  self.assertEqual(raw['_error'],'all_providers_unavailable')
 def test_disabled_never_calls(self):
  self.cfg['context_observer']['enabled']=False
  with patch.object(p,'request') as call:p.read('sys','ctx',self.cfg)
  call.assert_not_called()
 def test_configured_backup_becomes_primary(self):
  self.cfg['context_observer']['provider_order']=['gemini','openai']
  with patch.object(p,'request',return_value={'action':'NONE'}) as call:
   raw,_=p.read('sys','same context',self.cfg)
  self.assertEqual(call.call_args.args[0],'gemini')
  self.assertEqual(raw['_attempts'][0]['provider'],'gemini')
 def test_invalid_order_uses_known_default(self):
  self.cfg['context_observer']['provider_order']=['perplexity','gemini']
  with patch.object(p,'request',return_value={'action':'NONE'}) as call:
   p.read('sys','same context',self.cfg)
  self.assertEqual(call.call_args.args[0],'openai')

if __name__=='__main__':unittest.main()
