/**
 * Jest runner for the evaluator-private targeted validators of
 * flowise_3_1_3_repository_v1.
 *
 * Validators import the frozen workspace copy inside the materialized
 * dependency environment (artifacts/flowise_3_1_3_repository_v1_dependency_env)
 * so that module resolution and the uuid/typeorm redirects match the server
 * package's own frozen jest configuration.  The source tree of that workspace
 * is digest-identical to the frozen agent-visible target; only node_modules
 * was added.  Run offline with the environment's Node runtime; the exact
 * command is recorded in validation_recipes.json evidence.
 */
const path = require('path')

const serverRoot = path.resolve(
    __dirname,
    '..',
    '..',
    '..',
    '..',
    '..',
    'artifacts',
    'flowise_3_1_3_repository_v1_dependency_env',
    'workspace',
    'packages',
    'server'
)
const componentsRoot = path.resolve(serverRoot, '..', 'components')

module.exports = {
    rootDir: __dirname,
    testEnvironment: 'node',
    roots: ['<rootDir>'],
    transform: {
        '^.+\\.tsx?$': [
            path.join(serverRoot, 'node_modules', 'ts-jest'),
            { tsconfig: path.join(serverRoot, 'tsconfig.json'), isolatedModules: true }
        ]
    },
    testMatch: ['<rootDir>/*.test.ts'],
    moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
    moduleNameMapper: {
        '^uuid$': path.join(serverRoot, 'node_modules', 'uuid', 'dist', 'index.js'),
        // typeorm is redirected to the manual mock (decorators, FindOperators)
        // with the R13 recording DataSource replacing the inert jest.fn().
        '^typeorm$': path.join(__dirname, 'typeorm.shim.ts'),
        // The workspace-sibling components package is linked into
        // server/node_modules but its package entry (dist/src/index) is not
        // built; redirect to a source re-export shim, not a mock.
        '^flowise-components$': path.join(__dirname, 'flowise-components.shim.ts'),
        // Node files importing the components barrel '../../../src' get the
        // real src/utils re-export (small deterministic slice, no mock).
        '^\\.\\./\\.\\./\\.\\./src$': path.join(__dirname, 'components-src.shim.ts'),
        '^TARGET_SERVER_UTILS$': path.join(serverRoot, 'src', 'utils', 'index.ts'),
        '^TARGET_MCP_CORE$': path.join(componentsRoot, 'nodes', 'tools', 'MCP', 'core.ts'),
        '^TARGET_SQL_CHAIN$': path.join(
            componentsRoot, 'nodes', 'chains', 'SqlDatabaseChain', 'SqlDatabaseChain.ts'
        ),
        '^TARGET_CHAT_LOCALAI$': path.join(
            componentsRoot, 'nodes', 'chatmodels', 'ChatLocalAI', 'ChatLocalAI.ts'
        ),
        '^TARGET_PLAYWRIGHT$': path.join(
            componentsRoot, 'nodes', 'documentloaders', 'Playwright', 'Playwright.ts'
        ),
        '^TARGET_HTTP_SECURITY$': path.join(componentsRoot, 'src', 'httpSecurity.ts')
    },
    modulePaths: [
        path.join(serverRoot, 'node_modules'),
        // Bare imports shared with node modules under test (for example the
        // mocked Playwright loader) must resolve to the same module instance
        // from the validator files as from the frozen sources.
        path.join(componentsRoot, 'node_modules')
    ],
    verbose: true
}
