/**
 * R14 targeted local validation (frozen recipe): chat model baseURL egress
 * policy.
 *
 * Recipe (validation_recipes.json): inject a mocked checkDenyList/HTTP
 * client and verify the vulnerable init path assigns baseURL without
 * calling the policy; no DNS or network.  The assertions record the
 * vulnerable 3.1.3 runtime semantics: a user-configured basePath flows
 * straight into the credential-bearing OpenAI-compatible client
 * configuration while the shared deny-list policy (present in the frozen
 * codebase and used by other paths) is never invoked on this init path.
 * The LangChain client is lazy, so construction performs no network I/O.
 * Evaluator-side evidence strengthening only; not a TP prerequisite
 * (required_for_tp=false).
 */
import ChatLocalAINode from 'TARGET_CHAT_LOCALAI'
import * as httpSecurity from 'TARGET_HTTP_SECURITY'

const { nodeClass: ChatLocalAI } = ChatLocalAINode as any

describe('R14 ChatLocalAI baseURL egress policy (flowise 3.1.3)', () => {
    it('assigns a user-configured basePath as client baseURL without invoking the deny-list policy', async () => {
        const checkDenyListSpy = jest.spyOn(httpSecurity, 'checkDenyList')
        const attackerBasePath = 'http://169.254.169.254/latest/meta-data/'
        const model = await new ChatLocalAI().init(
            {
                inputs: {
                    basePath: attackerBasePath,
                    modelName: 'mock-model',
                    temperature: '0.1',
                    streaming: false
                }
            } as any,
            '',
            {} as any
        )
        // This @langchain/openai version normalizes the `configuration` field
        // into the OpenAI client's `clientConfig`, which is what the lazy
        // client will use as its baseURL on the first request.
        expect(model.clientConfig?.baseURL).toBe(attackerBasePath)
        expect(checkDenyListSpy).not.toHaveBeenCalled()
        checkDenyListSpy.mockRestore()
    })

    it('control: without basePath no baseURL configuration is injected', async () => {
        const model = await new ChatLocalAI().init(
            { inputs: { modelName: 'mock-model', temperature: '0.1', streaming: false } } as any,
            '',
            {} as any
        )
        expect(model.clientConfig?.baseURL).toBeUndefined()
    })
})
