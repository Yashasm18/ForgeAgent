# Reproduces the short terminal proof embedded at the top of README.md.
# Requires VHS only for asset generation; the recorded ForgeAgent commands
# themselves use no package or API key.
Output "docs/forgeagent-terminal-demo.gif"

Set Width 1260
Set Height 700
Set FontSize 22
Set TypingSpeed 18ms
Set Padding 26
Set MarginFill "#08111b"
Set Margin 12
Set Theme "Catppuccin Frappe"

Type "cd /tmp/ForgeAgent"
Enter
Type "export PS1='ForgeAgent $ '"
Enter
Type "clear"
Enter
Sleep 500ms

Type "python3 main.py --demo --reset"
Enter
Sleep 5s
