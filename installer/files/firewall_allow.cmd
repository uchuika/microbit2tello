@echo off
rem Allow Tello replies (UDP 8889) through Windows Firewall. Needs admin (UAC prompt).
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%1 .' -Verb RunAs"
  exit /b
)
netsh advfirewall firewall delete rule name="TelloBlocks" >nul 2>&1
netsh advfirewall firewall add rule name="TelloBlocks" dir=in action=allow program="%~dp0TelloBlocks.exe" protocol=UDP localport=8889 profile=any
if /i not "%1"=="/q" pause
