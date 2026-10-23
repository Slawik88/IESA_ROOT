$ErrorActionPreference = 'Stop'
$promoLines = @(
    'Двенадцать сообщений за неделю. Кикаем?',
    'Стоп. Человек просто на смене.',
    'В Предвестнике бот собирает список.',
    'А админ решает по каждому.',
    'Лену — пропустить.',
    'Всё. Лена остаётся.',
    'Меньше рутины. Решение за тобой.'
)
$promoVoice = New-Object -ComObject SAPI.SpVoice
$promoToken = New-Object -ComObject SAPI.SpObjectToken
$promoToken.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_ruRU_PavelM')
$promoVoice.Voice = $promoToken
$promoVoice.Rate = 3
for ($promoIndex = 0; $promoIndex -lt $promoLines.Count; $promoIndex++) {
    $promoStream = New-Object -ComObject SAPI.SpFileStream
    $promoPath = Join-Path $PSScriptRoot ('assets\voice_{0:00}.wav' -f $promoIndex)
    $promoStream.Open($promoPath, 3)
    $promoVoice.AudioOutputStream = $promoStream
    [void]$promoVoice.Speak($promoLines[$promoIndex])
    $promoStream.Close()
}
Write-Output 'Seven Russian narration clips created locally.'
