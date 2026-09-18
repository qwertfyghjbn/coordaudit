/**
 * Resolution shim for the components package barrel import `'../../../src'`
 * used by node modules such as documentloaders/Playwright.
 *
 * The barrel re-exports every node/tool module; the symbols these node files
 * import at runtime (handleEscapeCharacters, webCrawl, xmlScrape) all live in
 * src/utils.  This shim re-exports that real module so the validator loads a
 * small, deterministic slice of frozen source instead of the whole package
 * barrel.  Resolution only -- nothing is mocked here.
 */
export * from '../../../../../artifacts/flowise_3_1_3_repository_v1_dependency_env/workspace/packages/components/src/utils'
