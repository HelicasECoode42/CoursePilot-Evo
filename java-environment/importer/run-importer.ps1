param(
  [string]$Workbook,

  [Parameter(Mandatory = $true)]
  [ValidateSet(
    'cs-direct', 'cs-general',
    'ai-science-direct', 'ai-science',
    'cybersecurity-direct', 'cybersecurity',
    'ai-engineering-direct', 'ai-engineering'
  )]
  [string]$TrackId
)

$ErrorActionPreference = 'Stop'

$jarPath = Join-Path $PSScriptRoot 'target\curriculum-importer-0.1.0.jar'

if ([string]::IsNullOrWhiteSpace($Workbook)) {
  Add-Type -AssemblyName System.Windows.Forms
  $picker = New-Object System.Windows.Forms.OpenFileDialog
  $picker.Title = '选择 A1 标准化课程清单 (.xlsx)'
  $picker.Filter = 'Excel 工作簿 (*.xlsx)|*.xlsx'
  $picker.Multiselect = $false
  $javaEnvironmentRoot = Split-Path -Parent $PSScriptRoot
  $repoRoot = Split-Path -Parent $javaEnvironmentRoot
  $curriculaDirectory = Join-Path $repoRoot 'data\raw'
  if (Test-Path -LiteralPath $curriculaDirectory -PathType Container) {
    $picker.InitialDirectory = $curriculaDirectory
    $localA1Workbook = Join-Path $curriculaDirectory '2024-computer-college-curricula.xlsx'
    if (Test-Path -LiteralPath $localA1Workbook -PathType Leaf) {
      $picker.FileName = $localA1Workbook
    }
  }
  if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    Write-Host '已取消：没有选择工作簿。'
    exit 2
  }
  $Workbook = $picker.FileName
}

$resolvedWorkbook = (Resolve-Path -LiteralPath $Workbook).Path

Push-Location $PSScriptRoot
try {
  & .\mvnw.cmd -B clean verify
  $buildExitCode = $LASTEXITCODE
}
finally {
  Pop-Location
}

if ($buildExitCode -ne 0) {
  Write-Error "Maven 构建失败，退出码：$buildExitCode"
  exit $buildExitCode
}

& java -jar $jarPath $resolvedWorkbook $TrackId
exit $LASTEXITCODE
