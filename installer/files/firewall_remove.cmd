@echo off
rem Remove the firewall rule added by firewall_allow.cmd.
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%1 .' -Verb RunAs"
  exit /b
)
netsh advfirewall firewall delete rule name="TelloBlocks" >nul 2>&1
if /i not "%1"=="/q" pause
