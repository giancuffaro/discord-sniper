' _whop_hidden.vbs — starts the Whop keep-alive watchdog with no window at all.
'
' Same trick as _run_hidden.vbs (the bridge's own hidden launcher): a one-line
' script whose only job is to launch something with the window hidden. You'll
' see nothing, which is the point. Everything the loop would have printed
' goes into whop-loop.log in this folder instead.
'
' Not meant to be double-clicked. "START HERE.bat" runs it for you, and the
' Startup-folder entry + revive task (installed the same way as the Fill
' Announcer's) bring it back at logon or if it's ever killed.

Dim shell, cmd
Set shell = CreateObject("WScript.Shell")

Dim here
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

shell.CurrentDirectory = here
' Run the keep-alive loop, not chrome.exe directly, so a Sniper Whop browser
' that crashes or never started gets relaunched instead of Day Trades going
' dark for a month with nobody noticing (found 9/10).
cmd = "cmd /c """ & here & "\_whop_loop.bat"""

' 0 = hidden window. False = don't wait for it to finish.
' The scheduled task repeats every 30 minutes. Its earlier fire-and-forget
' launch let every invocation leave another permanent watchdog behind.
' Check this batch process (not Chrome's shared process) before starting it.
Dim service, process
Set service = GetObject("winmgmts:root\cimv2")
For Each process In service.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='cmd.exe'")
    If Not IsNull(process.CommandLine) Then
        If InStr(1, process.CommandLine, "_whop_loop.bat", vbTextCompare) > 0 Then WScript.Quit 0
    End If
Next
' Keep this task running until the loop exits, so Task Scheduler also knows
' a watchdog is already active rather than spawning another copy.
shell.Run cmd, 0, True
