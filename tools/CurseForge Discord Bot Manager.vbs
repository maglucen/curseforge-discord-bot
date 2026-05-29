Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

tools = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(tools)
launcher = root & "\tools\bot-manager.bat"

shell.CurrentDirectory = root
shell.Run """" & launcher & """", 0, False
