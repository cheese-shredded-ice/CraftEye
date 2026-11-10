@echo off
cd /d "%~dp0"
call npx remotion studio src/index.ts --port=3000
