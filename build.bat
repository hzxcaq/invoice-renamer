@echo off
echo 正在打包发票金额重命名工具...
pyinstaller --onefile --windowed --name "发票金额重命名工具" main.py
echo.
echo 打包完成！可执行文件在 dist\发票金额重命名工具.exe
pause
