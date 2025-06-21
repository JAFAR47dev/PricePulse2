@echo off
setlocal enabledelayedexpansion

:: CONFIGURATION
set REPO_URL=https://github.com/JAFAR47dev/PricePulse2.git
set NEW_SOURCE=C:\Users\user-pc\Music\folder1
set BRANCH=main

:: CLONE REPO
echo 📥 Cloning repo...
git clone %REPO_URL%
cd PricePulse2

:: CLEAN EXISTING FILES (but preserve .git folder)
echo 🧹 Cleaning up old files...
for /f %%F in ('dir /b /a-d') do (
    if /I "%%F" neq ".gitignore" del "%%F"
)
for /d %%D in (*) do (
    if /I "%%D" neq ".git" rd /s /q "%%D"
)

:: COPY NEW FILES IN
echo 📦 Copying new version from: %NEW_SOURCE%
xcopy "%NEW_SOURCE%\*" . /E /H /Y

:: COMMIT AND PUSH
echo 💾 Committing and pushing...
git add .
git commit -m "🔄 Full project replaced with new version"
git push origin %BRANCH%

echo ✅ DONE! Your GitHub repo is now up to date.
pause