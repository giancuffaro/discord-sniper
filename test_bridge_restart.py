"""The bridge's restart fallback must only exit when its watchdog is present."""
import unittest
from unittest import mock

import bridge


class BridgeRestartTests(unittest.TestCase):
    def test_windows_exec_failure_hands_off_to_running_watchdog(self):
        with mock.patch.object(bridge.os, 'name', 'nt'), \
             mock.patch.object(bridge.os, 'execv', side_effect=OSError(12, 'Not enough space')), \
             mock.patch.object(bridge.subprocess, 'run', return_value=mock.Mock(returncode=0)) as run, \
             mock.patch.object(bridge.os, '_exit', side_effect=SystemExit(0)) as exit_process, \
             mock.patch.object(bridge, 'note'):
            with self.assertRaises(SystemExit):
                bridge._restart_onto_disk()
            self.assertIn('_bridge_loop.bat', run.call_args.args[0][3])
            exit_process.assert_called_once_with(0)

    def test_no_watchdog_keeps_old_bridge_running(self):
        with mock.patch.object(bridge.os, 'name', 'nt'), \
             mock.patch.object(bridge.os, 'execv', side_effect=OSError(12, 'Not enough space')), \
             mock.patch.object(bridge.subprocess, 'run', return_value=mock.Mock(returncode=1)), \
             mock.patch.object(bridge.os, '_exit') as exit_process:
            with self.assertRaises(OSError):
                bridge._restart_onto_disk()
            exit_process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
