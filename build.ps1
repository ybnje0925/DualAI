$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 이상을 설치해 주세요.' }
}
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
& .venv/Scripts/python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw '검증 실패: 배포 중단' }
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name DualAI --collect-all playwright run.py
if ($LASTEXITCODE -ne 0) { throw '빌드 실패' }
Write-Host '완료: dist/DualAI.exe 를 더블클릭하세요.'
