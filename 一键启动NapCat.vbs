' Double-click to start NapCat with administrator rights.
'
' WHY THIS USES Shell.Application AND NOT WScript.Shell:
'   Shell.Application  -> has ShellExecute(File, Args, Dir, Operation, Show)
'   WScript.Shell      -> has NO ShellExecute. Its Run() takes only
'                         (strCommand, intWindowStyle, bWaitOnReturn) and
'                         has no verb argument. Passing "runas" as a 4th
'                         argument fails with error 1C2
'                         ("wrong number of arguments or invalid property").
' Also do not build this file with Python str.format(): the four quotes in
' a VBS string literal get eaten and produce syntax error 800A03EA.
' ASCII-only on purpose: VBS comments with Chinese break on some code pages.
Option Explicit
Dim fso, sh, here, target, logPath, f
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("Shell.Application")
here   = fso.GetParentFolderName(WScript.ScriptFullName)
target = fso.BuildPath(here, "启动NapCat-管理员.bat")
logPath = fso.BuildPath(here, "logs\vbs-launch.log")
If Not fso.FileExists(target) Then
    MsgBox "Script not found:" & vbCrLf & target, 16, "NapCat"
    WScript.Quit 1
End If
On Error Resume Next
sh.ShellExecute target, "", here, "runas", 1
If Err.Number <> 0 Then
    MsgBox "Failed to launch:" & vbCrLf & target & vbCrLf & vbCrLf & _
           "Error " & Hex(Err.Number) & ": " & Err.Description, 16, "NapCat"
    WScript.Quit 1
End If
On Error GoTo 0
On Error Resume Next
Set f = fso.OpenTextFile(logPath, 8, True)
f.WriteLine Now & "  ShellExecute runas -> " & target
f.Close
On Error GoTo 0
