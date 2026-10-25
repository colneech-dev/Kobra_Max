# il_dump.ps1 - disassemble methods of a .NET assembly with plain reflection (no extra tools).
#
# Used to read DWIN's own ICL writer (DGUS/DGUS_V7649/TOOL/multiLanguage/net8.0-windows/Excel2ICL.dll) and learn
# the CRC-16 stored at bytes 6-7 of every .icl, and how it pads JPEG headers/blocks. Needs PowerShell 7 (pwsh).
#
#   pwsh tools/re/il_dump.ps1 -Dll <assembly.dll> -TypeName Excel2ICL.Utils.ICL -Methods getICL,getBytes
#
# List a DLL's types/methods first with:  [Reflection.Assembly]::LoadFile($dll).GetTypes()
# Operands are resolved to names/strings; branch targets are IL offsets. Works only for managed (.NET) code:
# the other DWIN tools (DGUS_V7.649.exe, DwinTerminal.dll) are native and need a disassembler.

param([string]$Dll, [string]$TypeName, [string[]]$Methods)
$asm = [System.Reflection.Assembly]::LoadFile($Dll)
$one = @{}; $two = @{}
foreach ($f in [System.Reflection.Emit.OpCodes].GetFields()) {
    $oc = $f.GetValue($null)
    if ($oc -is [System.Reflection.Emit.OpCode]) {
        if ($oc.Size -eq 1) { $one[[int]$oc.Value] = $oc } else { $two[[int]($oc.Value -band 0xFF)] = $oc }
    }
}
function Resolve-Token($module, $tok, $kind) {
    try {
        switch ($kind) {
            'str' { return '"' + $module.ResolveString($tok) + '"' }
            default {
                $mb = $module.ResolveMember($tok)
                return ($mb.DeclaringType.Name + '::' + $mb.Name)
            }
        }
    } catch { return ('token 0x{0:X8}' -f $tok) }
}
function Dump-Method($m) {
    "=== " + $m.DeclaringType.Name + "::" + $m.Name + "(" + (($m.GetParameters() | ForEach-Object { $_.ParameterType.Name + ' ' + $_.Name }) -join ', ') + ")"
    $body = $m.GetMethodBody()
    if (-not $body) { "   (no body)"; return }
    "   locals: " + (($body.LocalVariables | ForEach-Object { $_.LocalType.Name }) -join ', ')
    $il = $body.GetILAsByteArray(); $i = 0; $mod = $m.Module
    while ($i -lt $il.Length) {
        $start = $i
        $b = $il[$i]; $i++
        if ($b -eq 0xFE) { $oc = $two[[int]$il[$i]]; $i++ } else { $oc = $one[[int]$b] }
        if ($null -eq $oc) { ('{0:X4}: ?? 0x{1:X2}' -f $start, $b); continue }
        $operand = ''
        switch ($oc.OperandType.ToString()) {
            'InlineNone' { }
            'ShortInlineBrTarget' { $v = [int]$il[$i]; if ($v -gt 127) { $v -= 256 }; $i += 1; $operand = ('IL_{0:X4}' -f ($i + $v)) }
            'ShortInlineI' { $v = [int]$il[$i]; if ($v -gt 127) { $v -= 256 }; $i += 1; $operand = "$v" }
            'ShortInlineVar' { $operand = "V" + $il[$i]; $i += 1 }
            'InlineVar' { $operand = "V" + [BitConverter]::ToUInt16($il, $i); $i += 2 }
            'InlineI' { $operand = [BitConverter]::ToInt32($il, $i); $i += 4 }
            'InlineI8' { $operand = [BitConverter]::ToInt64($il, $i); $i += 8 }
            'ShortInlineR' { $operand = [BitConverter]::ToSingle($il, $i); $i += 4 }
            'InlineR' { $operand = [BitConverter]::ToDouble($il, $i); $i += 8 }
            'InlineBrTarget' { $v = [BitConverter]::ToInt32($il, $i); $i += 4; $operand = ('IL_{0:X4}' -f ($i + $v)) }
            'InlineString' { $t = [BitConverter]::ToInt32($il, $i); $i += 4; $operand = Resolve-Token $mod $t 'str' }
            'InlineSwitch' { $n = [BitConverter]::ToInt32($il, $i); $i += 4; $tg = @(); for ($k = 0; $k -lt $n; $k++) { $tg += ('IL_{0:X4}' -f ($i + 4 * $n + [BitConverter]::ToInt32($il, $i + 4 * $k))) }; $i += 4 * $n; $operand = ($tg -join ',') }
            default { $t = [BitConverter]::ToInt32($il, $i); $i += 4; $operand = Resolve-Token $mod $t 'mem' }
        }
        ('IL_{0:X4}: {1,-12} {2}' -f $start, $oc.Name, $operand)
    }
}
$t = $asm.GetTypes() | Where-Object { $_.FullName -eq $TypeName }
foreach ($mn in $Methods) {
    foreach ($m in $t.GetMethods([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly')) {
        if ($m.Name -eq $mn) { Dump-Method $m }
    }
}
