/**
 * Recording typeorm shim for the R13 targeted validator.
 *
 * The frozen server jest configuration maps `typeorm` to a manual mock
 * (decorator no-ops + FindOperator factories) so entity modules load
 * without a database.  This shim re-exports every binding of that manual
 * mock verbatim and replaces its inert `DataSource: jest.fn()` with a
 * recording stub: the frozen SqlDatabaseChain node constructs the
 * DataSource from user configuration, initializes it, introspects the
 * schema through `query()`, and finally forwards the LLM-generated
 * statement to the same unguarded `query()` wrapper.  The stub executes no
 * SQL, touches no database file, and records every statement it receives;
 * `instances` exposes the created stubs to the validator assertions.
 */
import * as manualMock from '../../../../../artifacts/flowise_3_1_3_repository_v1_dependency_env/workspace/packages/server/__mocks__/typeorm'

const mock = manualMock as any

export const Column = mock.Column
export const Entity = mock.Entity
export const PrimaryGeneratedColumn = mock.PrimaryGeneratedColumn
export const PrimaryColumn = mock.PrimaryColumn
export const CreateDateColumn = mock.CreateDateColumn
export const UpdateDateColumn = mock.UpdateDateColumn
export const Index = mock.Index
export const ManyToOne = mock.ManyToOne
export const OneToMany = mock.OneToMany
export const OneToOne = mock.OneToOne
export const JoinColumn = mock.JoinColumn
export const Unique = mock.Unique
export const In = mock.In
export const Between = mock.Between
export const MoreThanOrEqual = mock.MoreThanOrEqual
export const LessThanOrEqual = mock.LessThanOrEqual

export class DataSource {
    options: any
    isInitialized = false
    queryLog: string[] = []

    constructor(options: any) {
        this.options = options
        instances.push(this)
    }

    async initialize(): Promise<DataSource> {
        this.isInitialized = true
        return this
    }

    async query(sql: string): Promise<any> {
        this.queryLog.push(sql)
        if (/sqlite_master/i.test(sql)) {
            // Minimal single-table schema shape expected by
            // formatToSqlTable in @langchain/classic sql_utils.
            return [
                { table_name: 'users', column_name: 'id', data_type: 'INTEGER', is_nullable: 'NO' },
                { table_name: 'users', column_name: 'name', data_type: 'TEXT', is_nullable: 'YES' }
            ]
        }
        return [{ id: 1, name: 'sample' }]
    }
}

export const instances: DataSource[] = []
