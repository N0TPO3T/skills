param([string]$In, [string]$Out)
# invert.ps1 <in.png> <out.png> : grayscale + invert to make white-on-color text readable
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Bitmap]::FromFile($In)
$bmp = New-Object System.Drawing.Bitmap($src.Width, $src.Height)
for ($y = 0; $y -lt $src.Height; $y++) {
    for ($x = 0; $x -lt $src.Width; $x++) {
        $c = $src.GetPixel($x, $y)
        $g = [int](0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B)
        $bmp.SetPixel($x, $y, [System.Drawing.Color]::FromArgb(255 - $g, 255 - $g, 255 - $g))
    }
}
$src.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "inverted $Out"
