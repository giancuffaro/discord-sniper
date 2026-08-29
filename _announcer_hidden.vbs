' _announcer_hidden.vbs — starts the Fill Announcer with no window at all.
' Same trick as _run_hidden.vbs: launch the keep-alive loop hidden, prints
' land in announcer.log. Not meant to be double-clicked — ANNOUNCER.bat,
' the Startup shortcut, and the 30-min revive task all point here.

Dim shell, fso, here, logf, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

' Rotate the log before launch (over 1 MB: .log -> .log.1 -> .log.2).
logf = here & "\announcer.log"
If fso.FileExists(logf) Then
    If fso.GetFile(logf).Size > 1048576 Then
        If fso.FileExists(logf & ".2") Then fso.DeleteFile logf & ".2"
        If fso.FileExists(logf & ".1") Then fso.MoveFile logf & ".1", logf & ".2"
        fso.MoveFile logf, logf & ".1"
    End If
End If

shell.CurrentDirectory = here
cmd = "cmd /c """ & here & "\_announcer_loop.bat"""
' 0 = hidden window. False = don't wait.
shell.Run cmd, 0, False
