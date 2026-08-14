@echo off
set REPO=C:\Coding projects\myGithub\Personal_use\multi_agent_research_tool
cd /d "%REPO%"
if not exist logs mkdir logs
python pipeline.py >> logs\pipeline.log 2>&1
