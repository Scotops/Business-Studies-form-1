param(
    [string]$Voice = "Microsoft Zira Desktop"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$textPath = Join-Path $projectRoot "content\i18n\en\texts.json"
$audioMapPath = Join-Path $projectRoot "content\i18n\en\audios.json"
$audioDirectory = Join-Path $projectRoot "content\i18n\en\audio"
$textObject = Get-Content -Raw -LiteralPath $textPath | ConvertFrom-Json
$audioObject = Get-Content -Raw -LiteralPath $audioMapPath | ConvertFrom-Json
$texts = @{}
$audioMap = @{}
$textObject.PSObject.Properties | ForEach-Object { $texts[$_.Name] = $_.Value }
$audioObject.PSObject.Properties | ForEach-Object { $audioMap[$_.Name] = $_.Value }

Add-Type -AssemblyName System.Speech
$synthesizer = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$synthesizer.SelectVoice($Voice)
$synthesizer.Rate = -1
$synthesizer.Volume = 100
$format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
    22050,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)

try {
    $ids = @($texts.Keys | Where-Object {
        $_ -like "pg*_page_number" -or
        $_ -in @("pg017_im030", "pg018_im009", "pg031_n0001")
    })
    foreach ($id in $ids) {
        if (-not $audioMap.ContainsKey($id)) {
            throw "No audio mapping exists for $id"
        }
        $outputPath = Join-Path $audioDirectory $audioMap[$id]
        $synthesizer.SetOutputToWaveFile($outputPath, $format)
        $synthesizer.Speak([string]$texts[$id])
        $synthesizer.SetOutputToNull()
    }
}
finally {
    $synthesizer.Dispose()
}
