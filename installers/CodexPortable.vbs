' CodexPortable.vbs — Windows launcher
' Opens CodexPortable.bat in a cmd window without showing the VBS host
' Handles both system/ and root directory layouts

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Resolve portable root
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
If LCase(fso.GetFolder(scriptDir).Name) = "system" Then
    portableDir = fso.GetParentFolderName(scriptDir)
Else
    portableDir = scriptDir
End If

batFile = portableDir & "\CodexPortable.bat"
If Not fso.FileExists(batFile) Then
    ' Try system/ subdirectory
    batFile = portableDir & "\system\CodexPortable.bat"
End If

If fso.FileExists(batFile) Then
    ' Use /D to ignore AutoRun registry, /K to keep window open
    shell.Run "cmd.exe /D /K """ & batFile & """", 1, False
Else
    MsgBox "找不到 CodexPortable.bat" & vbCrLf & _
           "路径: " & portableDir, vbCritical, "Codex Portable"
End If
