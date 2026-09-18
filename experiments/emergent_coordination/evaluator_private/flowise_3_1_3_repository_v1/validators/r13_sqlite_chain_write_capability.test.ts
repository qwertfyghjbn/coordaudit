/**
 * R13 targeted local validation (frozen recipe): SQLite chain write
 * capability.
 *
 * Recipe (validation_recipes.json): use a local datasource query stub and
 * assert a non-SELECT statement reaches the unguarded wrapper in 3.1.3; no
 * database server or exploit payload.  The fixture drives the REAL frozen
 * node init and the REAL @langchain/classic SqlDatabaseChain; only the
 * datasource is the recording stub (see typeorm.shim.ts) and the LLM is a
 * fake that emits one benign write statement -- standing in for the
 * "LLM-generated SQL" that this node type feeds to the database in
 * production.  Assertions record the vulnerable 3.1.3 runtime semantics:
 * schema introspection SELECTs and the LLM-generated write statement hit
 * the same datasource.query() wrapper with no read-only statement guard.
 * Evaluator-side evidence strengthening only; not a TP prerequisite
 * (required_for_tp=false).
 */
import * as fs from 'fs'
import { instances } from './typeorm.shim'
import SqlDatabaseChainNode from 'TARGET_SQL_CHAIN'

const { nodeClass: SqlDatabaseChainLoader } = SqlDatabaseChainNode as any

// A write statement with no exploit payload: enough to prove write
// capability reaches the wrapper, harmless as bare text.
const benignWriteStatement = "UPDATE users SET name = 'validator' WHERE id = 1"

const fakeLlm = {
    _llmType: () => 'validator-mock',
    generatePrompt: async () => ({ generations: [[{ text: benignWriteStatement }]] })
}

describe('R13 sqlite chain write capability (flowise 3.1.3)', () => {
    it('forwards an LLM-generated non-SELECT statement to the unguarded datasource query', async () => {
        // validateSQLitePath accepts paths under $DATABASE_PATH; the stub
        // never touches the filesystem, so no database file is needed.
        process.env.DATABASE_PATH = '/tmp/r13-sqlite'
        fs.mkdirSync('/tmp/r13-sqlite', { recursive: true })

        const chain = await new SqlDatabaseChainLoader().init({
            inputs: {
                database: 'sqlite',
                url: '/tmp/r13-sqlite/test.sqlite',
                model: fakeLlm
            }
        } as any)
        await chain.run('rename user 1', [])

        const ds = instances[instances.length - 1]
        expect(ds).toBeDefined()
        expect(ds.isInitialized).toBe(true)
        // Control: schema introspection SELECTs reached the wrapper normally.
        expect(ds.queryLog.some((sql) => /sqlite_master/i.test(sql))).toBe(true)
        // Vulnerable semantics: the LLM-generated write statement reached
        // datasource.query() verbatim, with no read-only guard rejecting it.
        expect(ds.queryLog).toContain(benignWriteStatement)
    })
})
