param(
  [string]$Source = "src\assets\asv-logo.png",
  [string]$Output = "public\favicon.ico"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SourcePath = Resolve-Path (Join-Path $RepoRoot $Source)
$OutputPath = Join-Path $RepoRoot $Output

Add-Type -AssemblyName System.Drawing

$sourceImage = [System.Drawing.Image]::FromFile($SourcePath)
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$pngImages = New-Object System.Collections.Generic.List[byte[]]

try {
  foreach ($size in $sizes) {
    $bitmap = New-Object System.Drawing.Bitmap $size, $size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
      $graphics.Clear([System.Drawing.Color]::Transparent)
      $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
      $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

      $padding = [Math]::Max(1, [Math]::Floor($size * 0.08))
      $maxWidth = $size - ($padding * 2)
      $maxHeight = $size - ($padding * 2)
      $scale = [Math]::Min($maxWidth / $sourceImage.Width, $maxHeight / $sourceImage.Height)
      $drawWidth = [Math]::Max(1, [Math]::Round($sourceImage.Width * $scale))
      $drawHeight = [Math]::Max(1, [Math]::Round($sourceImage.Height * $scale))
      $x = [Math]::Round(($size - $drawWidth) / 2)
      $y = [Math]::Round(($size - $drawHeight) / 2)

      $graphics.DrawImage($sourceImage, $x, $y, $drawWidth, $drawHeight)

      $stream = New-Object System.IO.MemoryStream
      try {
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngImages.Add($stream.ToArray())
      }
      finally {
        $stream.Dispose()
      }
    }
    finally {
      $graphics.Dispose()
      $bitmap.Dispose()
    }
  }
}
finally {
  $sourceImage.Dispose()
}

$OutputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$fileStream = [System.IO.File]::Create($OutputPath)
$writer = New-Object System.IO.BinaryWriter $fileStream
try {
  $writer.Write([UInt16]0)
  $writer.Write([UInt16]1)
  $writer.Write([UInt16]$sizes.Count)

  $offset = 6 + (16 * $sizes.Count)
  for ($i = 0; $i -lt $sizes.Count; $i++) {
    $size = $sizes[$i]
    $image = $pngImages[$i]
    $writer.Write([byte]($(if ($size -eq 256) { 0 } else { $size })))
    $writer.Write([byte]($(if ($size -eq 256) { 0 } else { $size })))
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$image.Length)
    $writer.Write([UInt32]$offset)
    $offset += $image.Length
  }

  foreach ($image in $pngImages) {
    $writer.Write($image)
  }
}
finally {
  $writer.Dispose()
  $fileStream.Dispose()
}

Get-Item $OutputPath
