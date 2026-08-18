' Runs AUTO PUSH.bat with no window - the scheduled task points here so a
' console never flashes over his charts every 30 minutes.
Set sh = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.Run """" & folder & "AUTO PUSH.bat""", 0, False
