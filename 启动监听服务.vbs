' Start the watcher listener and watchdog silently in the background.
' Safe to double-click repeatedly: it refuses to start duplicates.
' The listener itself is fully functional without this script; this only
' exists so the two background services can be launched with zero windows.
Option Explicit
Dim fso, sh, py, base_, i, cmd, running
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
base_ = fso.GetParentFolderName(WScript.ScriptFullName)
py = "C:\Users\wxzhe\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

If Not fso.FileExists(py) Then
    MsgBox "Python not found:" & vbCrLf & py, 16, "Watcher"
    WScript.Quit 1
End If

' The listener opens 127.0.0.1:18080. Querying the health endpoint is the
' most reliable duplicate check - name matching on python.exe is not.
running = False
On Error Resume Next
Dim http
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.setTimeouts 1000, 1000, 1000, 1500
http.open "GET", "http://127.0.0.1:18080/health", False
http.send
If Err.Number = 0 And http.Status = 200 Then running = True
Err.Clear
On Error GoTo 0

If running Then
    MsgBox "Watcher is already running." & vbCrLf & vbCrLf & _
           "Listening on 127.0.0.1:18080", 64, "Watcher"
    WScript.Quit 0
End If

sh.CurrentDirectory = base_
cmd = """" & py & """ -u """ & base_ & "\app\main.py"""
sh.Run cmd, 0, False
WScript.Sleep 4000
cmd = """" & py & """ -u """ & base_ & "\tools\watchdog.py"" --interval 120 --quiet"
sh.Run cmd, 0, False

MsgBox "Watcher services started (hidden):" & vbCrLf & _
       "  - listener  (127.0.0.1:18080)" & vbCrLf & _
       "  - watchdog  (alerts on failure)", 64, "Watcher"