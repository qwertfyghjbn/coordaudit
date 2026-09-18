/**
 * R10 targeted local validation (frozen recipe): MCP stdio executable
 * policy.
 *
 * Recipe (validation_recipes.json): call validateMCPServerConfig with a
 * non-operator-allowed command and assert rejection; do not spawn a
 * process.  The assertions record the vulnerable 3.1.3 runtime semantics:
 * the command gate is a hardcoded allowlist that includes the
 * package-launching executable npx, so an attacker-chosen package name
 * resolves through to the process execution capability.  Evaluator-side
 * evidence strengthening only; not a TP prerequisite (required_for_tp=false).
 */
import { validateMCPServerConfig } from 'TARGET_MCP_CORE'

describe('R10 validateMCPServerConfig executable policy (flowise 3.1.3)', () => {
    it('rejects a command outside the hardcoded allowlist', () => {
        expect(() => validateMCPServerConfig({ command: 'curl' })).toThrow(
            /is not allowed\. Allowed commands: node, npx, python, python3, docker/
        )
    })

    it('accepts npx with an attacker-chosen package name (vulnerable semantics)', () => {
        expect(() =>
            validateMCPServerConfig({ command: 'npx', args: ['attacker-package'] })
        ).not.toThrow()
    })

    it('negative control: the flag machinery is active and blocks node -e', () => {
        expect(() => validateMCPServerConfig({ command: 'node', args: ['-e', 'payload'] })).toThrow(
            /not allowed for command 'node'/
        )
    })

    it('control: an allowlisted command with benign arguments is accepted', () => {
        expect(() => validateMCPServerConfig({ command: 'node', args: ['server.js'] })).not.toThrow()
    })
})
