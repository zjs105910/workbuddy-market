# planning-with-files: Error hook for GitHub Copilot (Windows PowerShell)
# Logs errors to task_plan.md when the agent encounters an error.

if ($env:PLANNING_DISABLED -eq '1') {
    Write-Output '{}'
    exit 0
}

$planFile = "task_plan.md"

if (-not (Test-Path $planFile)) {
    Write-Output '{}'
    exit 0
}

# Read stdin. Do not name this $input: that is PowerShell's automatic pipeline
# variable, and under `-File` the assignment does not stick, so the hook read an
# empty string and never logged an error on Windows.
$InputData = [Console]::In.ReadToEnd()

try {
    $data = $InputData | ConvertFrom-Json
    $errorMsg = ""
    if ($data.error -is [PSCustomObject]) {
        $errorMsg = $data.error.message
    } elseif ($data.error) {
        $errorMsg = [string]$data.error
    }

    if ($errorMsg) {
        $truncated = $errorMsg.Substring(0, [Math]::Min(200, $errorMsg.Length))
        $context = "[planning-with-files] Error detected: $truncated. Log this error in task_plan.md under Errors Encountered with the attempt number and resolution."
        $escaped = $context | ConvertTo-Json
        Write-Output "{`"hookSpecificOutput`":{`"hookEventName`":`"ErrorOccurred`",`"additionalContext`":$escaped}}"
    } else {
        Write-Output '{}'
    }
} catch {
    Write-Output '{}'
}

exit 0
