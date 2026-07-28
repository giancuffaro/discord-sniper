' _run_hidden.vbs — starts the bridge with no window at all.
'
' Windows has no built-in way for a .bat file to run without a black box on
' screen. This is the standard trick: a one-line script whose only job is to
' launch something with the window hidden. You'll see nothing, which is the
' point.
'
' Everything the bridge would have printed goes into bridge.log in this folder
' instead, so if it ever dies at 9:25 there's still a record of why.
'
' Not meant to be double-clicked. "START HERE.bat" runs it for you.

Dim shell, fso, here, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

shell.CurrentDirectory = here
cmd = "cmd /c python """ & here & "\bridge.py"" >> """ & here & "\bridge.log"" 2>&1"

' 0 = hidden window. False = don't wait for it to finish.
shell.Run cmd, 0, False
