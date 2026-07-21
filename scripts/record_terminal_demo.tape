# Reproduces the complete trust-lifecycle recording embedded in README.md.
# Requires VHS only for asset generation; the recorded ForgeAgent process uses
# no package or API key.
Output "docs/forgeagent-terminal-demo.gif"

Set Width 1260
Set Height 760
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

Type "python3 scripts/run_video_demo.py --pause 1.1"
Enter
Sleep 10s
