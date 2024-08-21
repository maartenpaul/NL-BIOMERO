# Metabase

We add metabase for a dashboard visualization of BIOMERO data, like tracking job status for a user or analyzing workflow performances. 

Initially we mount this predefined database into your Metabase container, but H2 (file-based db) is not recommended for a production environment.

## Default admin user

The default preprogrammed user is 

    - email: admin@biomero.com

    - pw: b1omero

## Migrating Metabase dashboard to production db (postgres)

The best way to use our predefined dashboard (but not H2 db) is to 'migrate' from this H2 database to your postgres database:
https://www.metabase.com/docs/latest/installation-and-operation/migrating-from-h2 

Note that Metabase requires Postgres version >= 12.

After migration, you have to point your metabase to your chosen database with env variables (and you stop mounting the local H2 metabase db):

E.g. connecting to the default database-biomero
```
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: biomero
      MB_DB_PORT: 5432
      MB_DB_USER: biomero
      MB_DB_PASS: biomero
      MB_DB_HOST: database-biomero
```