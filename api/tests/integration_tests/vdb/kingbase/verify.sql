-- KES_Vector pre-flight checks for the Dify kingbase vector store.
--
-- Run it against a scratch database, it creates and drops its own probe tables:
--
--   psql "host=<HOST> port=54321 dbname=<DB> user=system password=<PASS>" -f verify.sql
--
-- Every block is independent, a failure in one block does not stop the others.
-- The two blocks that decide the implementation are #2 (cosine semantics) and
-- #4 (table access method).

\set ON_ERROR_STOP off

\echo '=== 0. environment ==='
select version();
select current_database(), current_user;
show server_version;
-- if the database was initialized case insensitively this returns t
select 'ABC' = 'abc' as case_insensitive;

\echo '=== 1. KES_Vector availability ==='
select name, default_version, installed_version
  from pg_available_extensions where name = 'vector';
create extension if not exists vector;
select extname, extversion from pg_extension where extname = 'vector';

\echo '=== 2. cosine distance semantics: expect 1 / 0 / 2 ==='
-- Dify converts the distance to a score with `score = 1 - distance`, which is only
-- correct when `<=>` returns 1 - cosine_similarity (the pgvector behaviour).
-- If this returns 0 / 1 / -1 the operator yields the similarity itself and the
-- score conversion has to be inverted.
select '[1,0,0]'::vector(3) <=> '[0,1,0]'::vector(3) as orthogonal_expect_1,
       '[1,0,0]'::vector(3) <=> '[1,0,0]'::vector(3) as identical_expect_0,
       '[1,0,0]'::vector(3) <=> '[-1,0,0]'::vector(3) as opposite_expect_2;

\echo '=== 3. vector literal and array assignment cast ==='
create table if not exists probe_vec (id uuid primary key, embedding vector(3));
insert into probe_vec values (gen_random_uuid(), '[0.1,0.2,0.3]');
-- the cast is documented as assignment level, so the psycopg2 list style works
insert into probe_vec values (gen_random_uuid(), array[1,0,0]::float4[]);
select count(*) as rows_inserted from probe_vec;

\echo '=== 4. table access method: an error here is a valid result ==='
-- Dify's pgvector implementation ends the DDL with `using heap`. If this fails, the
-- kingbase implementation must not copy that clause (it does not).
create table if not exists probe_heap (id uuid primary key, embedding vector(3)) using heap;

\echo '=== 5. vector indexes ==='
create index if not exists probe_vec_hnsw on probe_vec
  using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64);
create index if not exists probe_vec_ivf on probe_vec
  using ivfflat (embedding vector_cosine_ops) with (lists = 1);

\echo '=== 6. ef_search truncation: insert 100 rows, ask for 100 ==='
insert into probe_vec
select gen_random_uuid(),
       ('[' || (i % 10) || ',' || ((i * 7) % 10) || ',' || ((i * 13) % 10) || ']')::vector(3)
  from generate_series(1, 100) i;
set hnsw.ef_search = 40;
select count(*) as returned_with_ef_search_40 from (
  select * from probe_vec order by embedding <=> '[1,2,3]'::vector(3) limit 100
) t;
set hnsw.ef_search = 100;
select count(*) as returned_with_ef_search_100 from (
  select * from probe_vec order by embedding <=> '[1,2,3]'::vector(3) limit 100
) t;

\echo '=== 7. full text search ==='
select name, default_version, installed_version
  from pg_available_extensions where name in ('sys_jieba', 'zhparser', 'sys_trgm');
show default_text_search_config;
-- `simple` keeps a Chinese sentence as a single token, which is why the Dify
-- implementation always passes the configuration explicitly
select to_tsvector('simple', '人大金仓向量数据库支持全文检索') as simple_cfg;
select to_tsvector('simple', 'test_text') @@ plainto_tsquery('simple', 'test_text') as simple_hit;

\echo '--- zhparser / sys_jieba, expected to fail when not installed ---'
create extension if not exists sys_jieba;
select * from ts_parse('jieba', '人大金仓向量数据库支持全文检索');
select to_tsvector('jiebacfg', '人大金仓向量数据库支持全文检索') as jieba_cfg;
select to_tsvector('jiebacfg', '人大金仓向量数据库支持全文检索')
       @@ plainto_tsquery('jiebacfg', '向量数据库') as jieba_hit;

\echo '=== 8. index usability of to_tsvector ==='
-- provolatile: i = immutable (usable in an expression index), s = stable (not)
select proname, provolatile from pg_proc
 where proname in ('to_tsvector', 'plainto_tsquery') order by 1;

\echo '=== cleanup ==='
drop table if exists probe_vec;
drop table if exists probe_heap;
