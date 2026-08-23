Set-StrictMode -Version Latest

function Invoke-CheckedGit {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $output = @(git @Arguments 2>$null)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$FailureMessage (exit $exitCode)"
    }
    return $output
}

function Get-ExactGitHead {
    $raw = Invoke-CheckedGit -Arguments @('rev-parse', 'HEAD') -FailureMessage 'git HEAD lookup failed'
    $head = ($raw -join '').Trim()
    if ($head -notmatch '^[0-9a-f]{40}$') {
        throw 'git HEAD is not one 40-hex SHA'
    }
    return $head
}

function Invoke-ExactGitCommit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedParent,
        [Parameter(Mandatory = $true)][string[]]$Paths,
        [Parameter(Mandatory = $true)][string]$Message
    )

    if ($ExpectedParent -notmatch '^[0-9a-f]{40}$') {
        throw 'expected parent is not one 40-hex SHA'
    }
    if ([string]::IsNullOrWhiteSpace($Message)) {
        throw 'commit message is required'
    }
    $head = Get-ExactGitHead
    if ($head -cne $ExpectedParent) {
        throw 'expected parent moved before staging'
    }
    $initialIndex = @(Invoke-CheckedGit -Arguments @('diff', '--cached', '--name-only') -FailureMessage 'initial index lookup failed')
    if ($initialIndex.Count -ne 0) {
        throw 'exact commit requires an empty initial index'
    }
    if ($Paths.Count -eq 0) {
        throw 'exact commit requires allowlisted paths'
    }
    $unique = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    foreach ($path in $Paths) {
        if ([string]::IsNullOrWhiteSpace($path) -or [IO.Path]::IsPathRooted($path) -or $path -match '(^|[\\/])\.\.([\\/]|$)' -or -not $unique.Add($path)) {
            throw 'allowlisted paths must be unique repository-relative paths'
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "allowlisted path is missing: $path"
        }
    }
    $null = Invoke-CheckedGit -Arguments (@('add', '--') + $Paths) -FailureMessage 'allowlisted staging failed'
    $staged = @(Invoke-CheckedGit -Arguments @('diff', '--cached', '--name-only') -FailureMessage 'staged scope lookup failed')
    $actual = @($staged | Sort-Object)
    $expected = @($Paths | Sort-Object)
    if ($actual.Count -ne $expected.Count -or (Compare-Object $expected $actual)) {
        throw 'staged scope is not the exact changed allowlist'
    }
    $null = Invoke-CheckedGit -Arguments @('diff', '--cached', '--check') -FailureMessage 'cached diff check failed'
    $branchRef = Invoke-CheckedGit -Arguments @('symbolic-ref', '-q', 'HEAD') -FailureMessage 'HEAD must be attached to a symbolic branch'
    $branchRef = ($branchRef -join '').Trim()
    if ($branchRef -notmatch '^refs/heads/.+') {
        throw 'HEAD is not an attached branch ref'
    }
    $tree = Invoke-CheckedGit -Arguments @('write-tree') -FailureMessage 'tree write failed'
    $tree = ($tree -join '').Trim()
    if ($tree -notmatch '^[0-9a-f]{40}$') {
        throw 'write-tree did not return one 40-hex SHA'
    }
    $created = Invoke-CheckedGit -Arguments @('commit-tree', $tree, '-p', $ExpectedParent, '-m', $Message) -FailureMessage 'commit object creation failed'
    $created = ($created -join '').Trim()
    if ($created -notmatch '^[0-9a-f]{40}$' -or $created -ceq $ExpectedParent) {
        throw 'commit-tree did not return a new 40-hex SHA'
    }
    $null = Invoke-CheckedGit -Arguments @('update-ref', $branchRef, $created, $ExpectedParent) -FailureMessage 'branch compare-and-swap failed'
    $newHead = Get-ExactGitHead
    if ($newHead -cne $created) {
        throw 'branch moved after compare-and-swap'
    }
    $parents = Invoke-CheckedGit -Arguments @('rev-list', '--parents', '-n', '1', $newHead) -FailureMessage 'new commit parent lookup failed'
    $parentParts = (($parents -join ' ').Trim() -split '\s+')
    if ($parentParts.Count -ne 2 -or $parentParts[0] -cne $newHead -or $parentParts[1] -cne $ExpectedParent) {
        throw 'new commit is not a single-parent child of the expected parent'
    }
    return (Get-ExactGitHead)
}
