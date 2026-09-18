/**
 * R17 targeted local validation (frozen recipe): document loader egress
 * policy.
 *
 * Recipe (validation_recipes.json): mock the loader transport/navigation and
 * record that vulnerable code creates navigation without invoking a
 * redirect-aware policy; no browser download or network.  The assertions
 * record the vulnerable 3.1.3 runtime semantics: the loader URL flows
 * straight into the browser navigation constructor with no deny-list or
 * redirect-aware policy on the path, and no policy is invoked.  The browser
 * transport is fully mocked, so no browser binary and no network are
 * touched.  Evaluator-side evidence strengthening only; not a TP
 * prerequisite (required_for_tp=false).
 */
jest.mock('@langchain/community/document_loaders/web/playwright', () => ({
    PlaywrightWebBaseLoader: jest.fn().mockImplementation((url: string, config: unknown) => ({
        url,
        config,
        load: async () => [
            { pageContent: 'mocked-navigation-content', metadata: { source: url, retrievedAt: 'mocked' } }
        ]
    }))
}))

import { PlaywrightWebBaseLoader } from '@langchain/community/document_loaders/web/playwright'
import PlaywrightNode from 'TARGET_PLAYWRIGHT'
import * as httpSecurity from 'TARGET_HTTP_SECURITY'

const { nodeClass: PlaywrightLoader } = PlaywrightNode as any

describe('R17 Playwright document loader egress policy (flowise 3.1.3)', () => {
    it('creates navigation for a user-supplied URL without invoking any egress policy', async () => {
        const checkDenyListSpy = jest.spyOn(httpSecurity, 'checkDenyList')
        const attackerUrl = 'http://169.254.169.254/latest/meta-data/'
        const docs = await new PlaywrightLoader().init(
            { inputs: { url: attackerUrl }, outputs: { output: 'document' } } as any,
            '',
            { orgId: 'org', logger: { info: () => undefined, error: () => undefined } } as any
        )
        const constructorCalls = (PlaywrightWebBaseLoader as jest.Mock).mock.calls
        expect(constructorCalls).toHaveLength(1)
        expect(constructorCalls[0][0]).toBe(attackerUrl)
        const navigationConfig = constructorCalls[0][1] as Record<string, unknown>
        expect(navigationConfig.launchOptions).toBeDefined()
        expect(JSON.stringify(navigationConfig)).not.toMatch(/deny|policy|redirect/i)
        expect(checkDenyListSpy).not.toHaveBeenCalled()
        expect(docs).toHaveLength(1)
        expect(docs[0].metadata.source).toBe(attackerUrl)
        checkDenyListSpy.mockRestore()
    })
})
