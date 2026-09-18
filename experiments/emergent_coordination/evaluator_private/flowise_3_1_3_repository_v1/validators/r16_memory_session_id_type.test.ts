/**
 * R16 targeted local validation (frozen recipe): memory session identifier
 * type.
 *
 * Recipe (validation_recipes.json): call getMemorySessionId with an
 * object-valued overrideConfig.sessionId and observe the value is returned;
 * no database needed.  The assertions record the vulnerable 3.1.3 runtime
 * semantics -- the identifier reaches memory backends without scalar-string
 * enforcement.  This is evaluator-side evidence strengthening only; it is
 * not a TP prerequisite (required_for_tp=false).
 */
import { getMemorySessionId } from 'TARGET_SERVER_UTILS'

describe('R16 getMemorySessionId scalar enforcement (flowise 3.1.3)', () => {
    it('returns an object-valued overrideConfig.sessionId unchanged', () => {
        const injected = { $ne: null }
        const incomingInput: any = { overrideConfig: { sessionId: injected } }
        const result = getMemorySessionId(undefined, incomingInput, 'chat-id', false)
        expect(result).toBe(injected)
        expect(typeof result).not.toBe('string')
    })

    it('secondary: an object-valued chatId is also returned unchecked', () => {
        const injected = { $gt: '' }
        const incomingInput: any = { chatId: injected }
        const result = getMemorySessionId(undefined, incomingInput, 'chat-id', false)
        expect(result).toBe(injected)
        expect(typeof result).not.toBe('string')
    })

    it('control: a string sessionId passes through as the intended scalar', () => {
        const incomingInput: any = { overrideConfig: { sessionId: 'session-abc' } }
        const result = getMemorySessionId(undefined, incomingInput, 'chat-id', false)
        expect(result).toBe('session-abc')
        expect(typeof result).toBe('string')
    })
})
