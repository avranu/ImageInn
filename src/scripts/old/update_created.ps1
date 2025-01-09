param(
    [Parameter(Mandatory=$true)]
    [string]$path,
    [Parameter(Mandatory=$true)]
    [string]$date
)

if (-not (Test-Path -Path $path -PathType Container)) {
    Write-Host "The path provided is not a valid directory."
    exit 1
}

try {
    $new_date = [datetime]::ParseExact($date, "yyyy-MM-dd", $null)
} catch {
    Write-Host "An error occurred while parsing the date: $_"
    exit 1
}

# Get all files in the directory
$files = Get-ChildItem -Path $path -File

# Iterate through files and update the timestamps
foreach ($file in $files) {
    try {
        $new_creation_time = New-Object System.DateTime($new_date.Year, $new_date.Month, $new_date.Day, $file.CreationTime.Hour, $file.CreationTime.Minute, $file.CreationTime.Second)
        $new_last_write_time = New-Object System.DateTime($new_date.Year, $new_date.Month, $new_date.Day, $file.LastWriteTime.Hour, $file.LastWriteTime.Minute, $file.LastWriteTime.Second)
        
        $file.CreationTime = $new_creation_time
        $file.LastWriteTime = $new_last_write_time
        
        Write-Host "Timestamps updated for file: $($file.FullName)"
    } catch {
        Write-Host "An error occurred while processing $($file.FullName): $_"
    }
}

Write-Host "Operation completed."