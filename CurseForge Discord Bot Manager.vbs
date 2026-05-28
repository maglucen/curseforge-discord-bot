Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = root & "\tools\bot-manager.bat"

shell.CurrentDirectory = root
shell.Run """" & launcher & """", 0, False
