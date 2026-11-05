# Resumen de hardware y herramientas para elegir modelos locales.
# No imprime nombre de usuario ni rutas, asi que se puede pegar en un chat.
# Uso (PowerShell):  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hardware.ps1
$ErrorActionPreference = "SilentlyContinue"

"=== Equipo ==="
$cs = Get-CimInstance Win32_ComputerSystem
"RAM total: {0:N1} GB" -f ($cs.TotalPhysicalMemory / 1GB)
$os = Get-CimInstance Win32_OperatingSystem
"RAM libre ahora: {0:N1} GB" -f ($os.FreePhysicalMemory / 1MB)
"Sistema: $($os.Caption) $($os.Version)"
foreach ($c in Get-CimInstance Win32_Processor) {
  "CPU: {0} | nucleos {1} | hilos {2} | virtualizacion activa en BIOS: {3}" -f $c.Name.Trim(), $c.NumberOfCores, $c.NumberOfLogicalProcessors, $c.VirtualizationFirmwareEnabled
}
foreach ($g in Get-CimInstance Win32_VideoController) {
  "GPU: {0} (el dato de VRAM de Windows se corta en 4 GB en tarjetas grandes)" -f $g.Name
}
foreach ($d in Get-PSDrive -PSProvider FileSystem) {
  if (($d.Used + $d.Free) -gt 0) { "Disco {0}: libre {1:N0} GB de {2:N0} GB" -f $d.Name, ($d.Free / 1GB), (($d.Used + $d.Free) / 1GB) }
}
$nv = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
if ($nv) { "NVIDIA (nvidia-smi): $nv" } else { "NVIDIA (nvidia-smi): no hay" }

"`n=== Herramientas (version o 'no encontrado') ==="
function Version($nombre, $argumentos) {
  $cmd = Get-Command $nombre -ErrorAction SilentlyContinue
  if ($cmd -and $nombre -eq "python" -and $cmd.Source -like "*\WindowsApps\*") {
    "{0,-8} no instalado (solo el acceso directo de la Microsoft Store)" -f $nombre
  } elseif ($cmd) {
    $v = (& $nombre $argumentos 2>$null | Select-Object -First 1)
    "{0,-8} {1}" -f $nombre, $v
  } else { "{0,-8} no encontrado" -f $nombre }
}
Version "git" "--version"
Version "python" "--version"
Version "docker" "--version"
Version "node" "--version"
Version "ollama" "--version"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  "`nModelos de ollama ya descargados:"
  & ollama list 2>$null
}
"`n=== Docker ==="
$v = (& docker info --format "{{.ServerVersion}}" 2>$null)
if ($v) { "servicio de Docker activo, version $v" } else { "servicio de Docker apagado o no instalado" }
