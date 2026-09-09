param([string]$In, [string]$Out, [int]$Scale = 3)
# zoom.ps1 <in.png> <out.png> [scale] : nearest-neighbor upscale for easier visual reading
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile($In)
$w = $src.Width * $Scale
$h = $src.Height * $Scale
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$g.DrawImage($src, 0, 0, $w, $h)
$g.Dispose()
$src.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("zoomed {0} -> {1} x{2}" -f $In, $Out, $Scale)
