' XianXing ZhiCe - one-click launcher
' Starts the server in background (no console window) and opens the browser.
'
' Usage: double-click this file
'        cscript //nologo start.vbs nobrowser   (server only, no browser)

Option Explicit

Dim sh, fso, base, py, url
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base

py = base & "\.venv\Scripts\python.exe"
url = "http://127.0.0.1:8000"

If Not fso.FileExists(py) Then
  MsgBox "Python venv not found:" & vbCrLf & py & vbCrLf & vbCrLf & _
         "Please double-click run.bat first to create it.", 48, "XianXing ZhiCe"
  WScript.Quit 1
End If

If Not fso.FileExists(base & "\.venv\.deps_ok") Then
  If MsgBox("First run needs to install dependencies (1-3 minutes)." & vbCrLf & _
            "Install now?", 4 + 32, "XianXing ZhiCe") = 6 Then
    sh.Run "cmd /c """ & base & "\run.bat""", 1, True
  Else
    WScript.Quit 0
  End If
End If

' 0 = hidden window, False = do not wait
sh.Run """" & py & """ -m uvicorn server.main:app --host 0.0.0.0 --port 8000", 0, False
WScript.Sleep 3000

If WScript.Arguments.Count > 0 Then
  If LCase(WScript.Arguments(0)) = "nobrowser" Then WScript.Quit 0
End If

sh.Run url, 1, False
